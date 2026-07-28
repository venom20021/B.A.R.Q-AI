"""
End-to-end integration test for the Deepgram Voice Agent pipeline.

Uses a mock WebSocket server that mimics the Deepgram Voice Agent protocol
(wss://agent.deepgram.com/v1/agent/converse) to test the full lifecycle
of DeepgramVoiceAgent without requiring a real API key.

Lifecycle tested:
  1. Connect → Welcome → Settings → SettingsApplied (handshake)
  2. Greeting audio (binary) → ConversationText (greeting done)
  3. Microphone audio send (binary)
  4. UserTranscript (interim + final)
  5. UserStartedSpeaking → barge-in (ring buffer cleared)
  6. FunctionCallRequest → FunctionCallResponse round trip
  7. Duplicate FunctionCallRequest dedup
  8. Unknown function → error response
  9. Server Error message handling
  10. Clean teardown on stop()
"""

import asyncio
import json
import os
import sys
from typing import Any

import numpy as np
import pytest

# Ensure python directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from voice.deepgram_agent import DeepgramVoiceAgent, AGENT_SETTINGS, AGENT_OUTPUT_SAMPLE_RATE


# ─── Constants ───────────────────────────────────────────────────────────

MOCK_HOST = "127.0.0.1"
MOCK_PORT = 18956  # Different from real sidecar port (8956)
MOCK_WS_URL = f"ws://{MOCK_HOST}:{MOCK_PORT}"
MOCK_API_KEY = "test_api_key_12345"

# Small PCM audio chunk (20ms of 24kHz linear16 = 960 bytes)
SILENT_AUDIO_CHUNK = b"\x00\x00" * 480  # 960 bytes = 480 samples of silence @ int16


# ─── Mock Deepgram Server ────────────────────────────────────────────────

class MockDeepgramServer:
    """A mock WebSocket server that simulates the Deepgram Voice Agent protocol.

    Usage:
        server = MockDeepgramServer()
        await server.start()
        try:
            # Run client tests against server.ws_url
        finally:
            await server.stop()
    """

    def __init__(self):
        self.host = MOCK_HOST
        self.port = MOCK_PORT
        self.ws_url = MOCK_WS_URL
        self._server: Any = None
        self._connections: list[Any] = []
        self._stop_event = asyncio.Event()

        # Protocol tracking
        self.received_settings: dict | None = None
        self.received_binary_chunks: list[bytes] = []
        self.received_text_messages: list[str] = []
        self.function_call_responses: list[dict] = []
        self.welcome_sent = False
        self.settings_applied_sent = False

        # Behavior configuration (tests can override these)
        self.send_welcome = True
        self.send_settings_applied = True
        self.welcome_delay = 0.0
        self.settings_applied_delay = 0.0
        self.greeting_audio_chunks = 3  # Send 3 chunks of silence before ConversationText
        self.send_error_on_settings = False
        self.error_description = ""

        # Websocket reference for the active client connection
        # Set during _handle_connection so inject_message can use it
        self._client_ws: Any = None

        # Queue for test-to-server commands (e.g., inject messages)
        self._command_queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        """Start the mock WebSocket server."""
        import websockets as ws_module

        self._server = await ws_module.serve(
            self._handle_connection,
            self.host,
            self.port,
            max_size=2**20,  # 1MB max message
            reuse_address=True,
        )
        print(f"[MockServer] Listening on {self.host}:{self.port}")

    async def stop(self):
        """Stop the mock WebSocket server and close all connections."""
        self._stop_event.set()
        for ws in self._connections:
            await ws.close()
        self._connections.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        print("[MockServer] Stopped")

    async def inject_message(self, payload: dict):
        """Send a JSON message to the agent (as if from Deepgram server).

        Args:
            payload: The JSON-serializable dict to send to the agent.
                     Must contain a "type" field (e.g. "UserStartedSpeaking",
                     "UserTranscript", "FunctionCallRequest", etc.)
        """
        if self._client_ws:
            await self._client_ws.send(json.dumps(payload))
        else:
            # Queue it for when a connection is established
            await self._command_queue.put(("message", payload))

    async def inject_function_call(self, function_name: str,
                                     function_call_id: str,
                                     arguments: dict):
        """Send a FunctionCallRequest to the agent (as if from Deepgram).

        This simulates Deepgram's Gemini deciding to invoke a local tool.
        """
        payload = {
            "type": "FunctionCallRequest",
            "function_name": function_name,
            "function_call_id": function_call_id,
            "input": arguments,
        }
        await self.inject_message(payload)
        print(f"[MockServer] Injected FunctionCallRequest: {function_name}")

    async def _handle_connection(self, websocket):
        """Handle a single client connection."""
        self._connections.append(websocket)
        self._client_ws = websocket
        peer = websocket.remote_address
        print(f"[MockServer] Client connected from {peer}")

        try:
            await self._handle_protocol(websocket)
        except Exception as e:
            print(f"[MockServer] Connection error: {e}")
        finally:
            self._connections.remove(websocket)
            self._client_ws = None

    async def _handle_protocol(self, websocket):
        """Simulate the Deepgram Voice Agent protocol."""
        # ── Step 1: Send Welcome message ────────────────────────────
        if self.send_welcome:
            if self.welcome_delay > 0:
                await asyncio.sleep(self.welcome_delay)
            await websocket.send(json.dumps({"type": "Welcome"}))
            self.welcome_sent = True
            print("[MockServer] Sent: Welcome")
        else:
            # Don't send Welcome — test timeout handling
            await asyncio.sleep(15)
            return

        # ── Step 2: Receive Settings from client ────────────────────
        try:
            msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
        except asyncio.TimeoutError:
            print("[MockServer] Timeout waiting for Settings")
            return

        if isinstance(msg, str):
            try:
                self.received_settings = json.loads(msg)
                print(f"[MockServer] Received Settings: type={self.received_settings.get('type')}")
            except json.JSONDecodeError:
                print(f"[MockServer] Non-JSON text received: {msg[:100]}")
                return

            # Validate settings structure
            assert self.received_settings.get("type") == "Settings"
            assert "audio" in self.received_settings
            assert "agent" in self.received_settings

            # Check function schemas were injected
            functions = self.received_settings.get("agent", {}).get("think", {}).get("functions", [])
            if functions:
                print(f"[MockServer] Functions injected: {len(functions)} schemas")
                function_names = [f["name"] for f in functions]
                print(f"[MockServer] Function names: {function_names}")

        elif isinstance(msg, bytes):
            print(f"[MockServer] Received binary instead of Settings ({len(msg)} bytes)")
            return

        # ── Step 3: Send SettingsApplied confirmation ───────────────
        if self.send_settings_applied:
            if self.settings_applied_delay > 0:
                await asyncio.sleep(self.settings_applied_delay)

            if self.send_error_on_settings:
                await websocket.send(json.dumps({
                    "type": "Error",
                    "description": self.error_description or "Mock error",
                }))
                print(f"[MockServer] Sent: Error (mock)")
                return

            await websocket.send(json.dumps({"type": "SettingsApplied"}))
            self.settings_applied_sent = True
            print("[MockServer] Sent: SettingsApplied")
        else:
            return

        # ── Step 4: Send greeting audio chunks ──────────────────────
        for i in range(self.greeting_audio_chunks):
            await websocket.send(SILENT_AUDIO_CHUNK)
            print(f"[MockServer] Sent: greeting audio chunk {i+1}/{self.greeting_audio_chunks}")
            await asyncio.sleep(0.02)  # Slight delay between chunks

        # ── Step 5: Send ConversationText (greeting done) ───────────
        await websocket.send(json.dumps({
            "type": "ConversationText",
            "text": "Hello! How may I help you today?",
        }))
        print("[MockServer] Sent: ConversationText (greeting)")

        # ── Step 6: Listen for messages and respond ─────────────────
        # The client will now start sending mic audio (binary) and
        # we can inject control messages
        await self._listen_and_respond(websocket)

    async def _listen_and_respond(self, websocket):
        """Listen for messages and respond based on test scenario.

        Two input sources:
        1. Messages from the agent (websocket.recv) — mic audio, FunctionCallResponse
        2. Commands from the test (self._command_queue) — inject messages to agent

        Key behavior:
        - Binary (mic audio) → store for verification
        - Text FunctionCallResponse → store for verification
        - Commands: relay JSON messages back to the agent (test-driven injection)
        """
        received_audio = False

        while not self._stop_event.is_set():
            # Check both the websocket and the command queue with race
            msg = None
            cmd = None

            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check command queue
                try:
                    cmd = self._command_queue.get_nowait()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.05)
                    continue

            if cmd:
                cmd_type, cmd_payload = cmd
                if cmd_type == "message":
                    # Send this message to the agent (simulates Deepgram server)
                    await websocket.send(json.dumps(cmd_payload))
                    print(f"[MockServer] Sent agent: {cmd_payload.get('type', 'unknown')}")
                continue

            if msg is None:
                continue

            if isinstance(msg, bytes):
                self.received_binary_chunks.append(msg)
                if not received_audio:
                    received_audio = True
                    print(f"[MockServer] Received first mic audio chunk ({len(msg)} bytes)")
            elif isinstance(msg, str):
                self.received_text_messages.append(msg)
                try:
                    data = json.loads(msg)
                    msg_type = data.get("type", "")
                    if msg_type == "FunctionCallResponse":
                        self.function_call_responses.append(data)
                        print(f"[MockServer] Received FunctionCallResponse for '{data.get('function_call_id', '?')}'")
                except json.JSONDecodeError:
                    pass


# ─── Helper: Create a DeepgramVoiceAgent connected to mock ─────────────

async def create_connected_agent(server: MockDeepgramServer) -> DeepgramVoiceAgent:
    """Create a DeepgramVoiceAgent connected to the mock server.

    Patches the WS URL to point to our mock server instead of the real Deepgram endpoint.
    """
    agent = DeepgramVoiceAgent(api_key=MOCK_API_KEY)

    # Monkey-patch the connect method to use our mock URL
    original_connect = agent.connect

    async def patched_connect() -> bool:
        try:
            import websockets as ws_module
            agent._ws = await ws_module.connect(
                MOCK_WS_URL,
                subprotocols=["token", agent.api_key],
            )
            print("[TestAgent] Connected to mock server")

            # Receive Welcome
            welcome = await asyncio.wait_for(agent._ws.recv(), timeout=10.0)
            if isinstance(welcome, str):
                data = json.loads(welcome)
                if data.get("type") != "Welcome":
                    return False

            # Inject function schemas and send Settings
            import copy
            from voice.function_executor import get_function_schemas
            settings_payload = copy.deepcopy(AGENT_SETTINGS)
            function_schemas = get_function_schemas()
            if function_schemas:
                think_cfg = settings_payload.setdefault("agent", {}).setdefault("think", {})
                think_cfg["functions"] = function_schemas

            await agent._ws.send(json.dumps(settings_payload))
            print("[TestAgent] Settings sent")

            # Wait for SettingsApplied
            response = await asyncio.wait_for(agent._ws.recv(), timeout=15.0)
            if isinstance(response, str):
                data = json.loads(response)
                if data.get("type") == "SettingsApplied":
                    agent._settings_applied.set()
                    return True
                elif data.get("type") == "Error":
                    print(f"[TestAgent] Settings rejected: {data.get('description', '')}")
                    return False
            return False

        except Exception as e:
            print(f"[TestAgent] Connect failed: {e}")
            return False

    agent.connect = patched_connect  # type: ignore
    return agent


# ─── Mock SoundDevice (prevent real audio hardware access in tests) ────

class MockAudioStream:
    """Mock for sounddevice InputStream/OutputStream.

    Prevents actual hardware access during tests.
    Records calls for verification if needed.
    """
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def close(self):
        self.running = False


@pytest.fixture(autouse=True)
def mock_sounddevice(monkeypatch):
    """Mock sounddevice to prevent real audio hardware access in tests.

    This is critical because:
    1. Tests don't have actual microphones/speakers available
    2. PortAudio can cause segmentation faults when accessing real hardware
    3. Each test creates a DeepgramVoiceAgent that tries to open audio streams
    """
    import sounddevice as sd
    # Wrap the real InputStream with our mock that records args
    original_input_stream = sd.InputStream
    def mock_input_stream(*args, **kwargs):
        return MockAudioStream(*args, **kwargs)

    original_output_stream = sd.OutputStream
    def mock_output_stream(*args, **kwargs):
        return MockAudioStream(*args, **kwargs)

    monkeypatch.setattr(sd, "InputStream", mock_input_stream)
    monkeypatch.setattr(sd, "OutputStream", mock_output_stream)
    yield


# ─── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
async def mock_server():
    """Start and stop a mock Deepgram server for each test."""
    server = MockDeepgramServer()
    await server.start()
    yield server
    await server.stop()


# ─── Test Cases ──────────────────────────────────────────────────────────

class TestVoicePipelineLifecycle:
    """Test the full Deepgram Voice Agent lifecycle."""

    @pytest.mark.asyncio
    async def test_full_happy_path(self, mock_server: MockDeepgramServer):
        """Test the complete happy path: connect → greet → listen → disconnect.

        Verifies:
        - Welcome received
        - Settings sent with function schemas
        - SettingsApplied received
        - Greeting audio received as binary
        - ConversationText received (greeting done)
        - Mic audio can be sent as binary
        - Agent stops cleanly
        """
        agent = await create_connected_agent(mock_server)

        # Connect
        connected = await agent.connect()
        assert connected, "Agent should connect successfully"
        assert mock_server.welcome_sent, "Server should have sent Welcome"
        assert mock_server.settings_applied_sent, "Server should have sent SettingsApplied"
        assert mock_server.received_settings is not None, "Server should have received Settings"
        assert mock_server.received_settings["type"] == "Settings"

        # Verify function schemas were injected
        functions = mock_server.received_settings.get("agent", {}).get("think", {}).get("functions", [])
        assert len(functions) == 12, f"Expected 12 function schemas, got {len(functions)}"
        function_names = [f["name"] for f in functions]
        assert "minimize_window" in function_names
        assert "open_file" in function_names
        assert "get_system_status" in function_names
        assert "take_screenshot" in function_names
        assert "clipboard" in function_names
        assert "focus_window" in function_names
        assert "set_app_volume" in function_names

        # Start conversation
        await agent.start_conversation()
        assert agent.is_running, "Agent should be running after start_conversation"

        # Wait for greeting audio chunks to arrive
        await asyncio.sleep(0.3)

        # Send simulated mic audio (as if user starts speaking)
        if agent._ws:
            await agent._ws.send(b"\x00\x00" * 480)  # Small silence chunk

        # Let some messages process
        await asyncio.sleep(0.2)

        # Stop cleanly
        await agent.stop()
        assert not agent.is_running, "Agent should not be running after stop"

        # Verify server received mic audio
        assert len(mock_server.received_binary_chunks) >= 1, "Server should have received at least 1 audio chunk"

    @pytest.mark.asyncio
    async def test_function_call_roundtrip(self, mock_server: MockDeepgramServer):
        """Test FunctionCallRequest → FunctionCallResponse round trip.

        Verifies:
        - FunctionCallRequest with minimize_window triggers execution
        - FunctionCallResponse sent back with status
        - function_call_id is propagated correctly
        """
        agent = await create_connected_agent(mock_server)

        # Connect and start conversation
        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Send a FunctionCallRequest via the mock server (simulating Deepgram)
        function_call_id = "call_test_001"
        await mock_server.inject_function_call(
            function_name="get_system_status",
            function_call_id=function_call_id,
            arguments={},
        )

        # Wait for the function to execute and response to be sent
        await asyncio.sleep(1.0)

        # Verify FunctionCallResponse was received by server
        assert len(mock_server.function_call_responses) >= 1, "Server should have received FunctionCallResponse"
        response = mock_server.function_call_responses[0]
        assert response["type"] == "FunctionCallResponse", f"Expected FunctionCallResponse, got {response.get('type')}"
        assert response["function_call_id"] == function_call_id
        assert response["output"]["status"] == "success"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_function_call_with_args(self, mock_server: MockDeepgramServer):
        """Test function call with arguments passes them correctly."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Test list_files with a valid directory
        await mock_server.inject_function_call(
            function_name="list_files",
            function_call_id="call_list_001",
            arguments={"directory": ".", "pattern": "*.py"},
        )

        await asyncio.sleep(1.0)

        assert len(mock_server.function_call_responses) >= 1
        response = mock_server.function_call_responses[0]
        assert response["output"]["status"] == "success"
        assert response["output"]["total"] > 0, "Should have found .py files"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_unknown_function_call(self, mock_server: MockDeepgramServer):
        """Test FunctionCallRequest for an unknown function returns error."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        await mock_server.inject_function_call(
            function_name="nonexistent_function_xyz",
            function_call_id="call_unknown_001",
            arguments={},
        )

        await asyncio.sleep(0.5)

        assert len(mock_server.function_call_responses) >= 1
        response = mock_server.function_call_responses[0]
        assert response["output"]["status"] == "error", f"Expected error status, got {response['output']['status']}"
        assert "Unknown function" in response["output"]["detail"]

        await agent.stop()

    @pytest.mark.asyncio
    async def test_duplicate_function_call_ignored(self, mock_server: MockDeepgramServer):
        """Test that duplicate function_call_id is ignored (dedup)."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        function_call_id = "call_dup_001"

        # Send the same call ID twice
        await mock_server.inject_function_call(
            function_name="get_system_status",
            function_call_id=function_call_id,
            arguments={},
        )
        await asyncio.sleep(0.1)

        await mock_server.inject_function_call(
            function_name="get_system_status",
            function_call_id=function_call_id,
            arguments={},
        )

        await asyncio.sleep(0.5)

        # Should only have one response (duplicate was ignored)
        assert len(mock_server.function_call_responses) == 1, (
            f"Expected 1 response (duplicate ignored), got {len(mock_server.function_call_responses)}"
        )

        await agent.stop()

    @pytest.mark.asyncio
    async def test_barge_in_clears_ring_buffer(self, mock_server: MockDeepgramServer):
        """Test that UserStartedSpeaking clears the ring buffer (barge-in).

        Verifies:
        - Ring buffer has data after receiving audio
        - UserStartedSpeaking clears it
        """
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Send some audio chunks to fill the ring buffer
        agent._output_ring_buffer.extend(np.ones(1000, dtype=np.float32))
        assert len(agent._output_ring_buffer) > 0, "Ring buffer should have data"

        # Send UserStartedSpeaking (from server)
        await mock_server.inject_message({"type": "UserStartedSpeaking"})

        await asyncio.sleep(0.2)

        # Ring buffer should be empty after barge-in
        assert len(agent._output_ring_buffer) == 0, "Ring buffer should be cleared after barge-in"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_barge_in_debounce(self, mock_server: MockDeepgramServer):
        """Test that rapid UserStartedSpeaking events are debounced (echo guard)."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Fill ring buffer
        agent._output_ring_buffer.extend(np.ones(5000, dtype=np.float32))
        initial_len = len(agent._output_ring_buffer)

        # Send rapid UserStartedSpeaking messages (within 200ms debounce window)
        await mock_server.inject_message({"type": "UserStartedSpeaking"})
        await asyncio.sleep(0.05)
        await mock_server.inject_message({"type": "UserStartedSpeaking"})
        await asyncio.sleep(0.05)
        await mock_server.inject_message({"type": "UserStartedSpeaking"})

        await asyncio.sleep(0.2)

        # First event should clear, second and third should be debounced
        # (ring buffer was cleared after first event, subsequent debounced events won't re-clear)
        assert len(agent._output_ring_buffer) == 0, "Ring buffer should be empty"

        # Check that last_user_spoke_at was updated
        # After 200ms debounce window, a new event should NOT be debounced
        await asyncio.sleep(0.3)  # Wait for debounce window to expire
        agent._output_ring_buffer.extend(np.ones(100, dtype=np.float32))
        await mock_server.inject_message({"type": "UserStartedSpeaking"})
        await asyncio.sleep(0.2)
        assert len(agent._output_ring_buffer) == 0, "Ring buffer should be cleared again after debounce window"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_user_transcript_callbacks(self, mock_server: MockDeepgramServer):
        """Test that UserTranscript messages trigger callbacks."""
        agent = await create_connected_agent(mock_server)

        collected_interim: list[str] = []
        collected_final: list[str] = []

        def on_interim(text: str):
            collected_interim.append(text)

        def on_final(text: str):
            collected_final.append(text)

        agent.on_interim_transcript = on_interim
        agent.on_final_transcript = on_final

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Send interim transcript
        await mock_server.inject_message({
            "type": "UserTranscript",
            "transcript": "hello world",
            "is_final": False,
        })

        await asyncio.sleep(0.1)

        # Send final transcript
        await mock_server.inject_message({
            "type": "UserTranscript",
            "transcript": "minimize chrome window please",
            "is_final": True,
        })

        await asyncio.sleep(0.2)

        assert len(collected_interim) == 1, f"Expected 1 interim, got {len(collected_interim)}"
        assert collected_interim[0] == "hello world"
        assert len(collected_final) == 1, f"Expected 1 final, got {len(collected_final)}"
        assert collected_final[0] == "minimize chrome window please"

        # Verify full_transcript property
        assert "minimize chrome window please" in agent.full_transcript

        await agent.stop()

    @pytest.mark.asyncio
    async def test_agent_speaking_callbacks(self, mock_server: MockDeepgramServer):
        """Test AgentStartedSpeaking/AgentAudioDone callbacks."""
        agent = await create_connected_agent(mock_server)

        speaking_events: list[str] = []

        def on_speaking():
            speaking_events.append("started")

        def on_done():
            speaking_events.append("done")

        agent.on_agent_speaking = on_speaking
        agent.on_agent_done_speaking = on_done

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        await mock_server.inject_message({"type": "AgentStartedSpeaking"})
        await asyncio.sleep(0.1)
        await mock_server.inject_message({"type": "AgentAudioDone"})
        await asyncio.sleep(0.1)

        assert len(speaking_events) == 2, f"Expected 2 events, got {speaking_events}"
        assert speaking_events == ["started", "done"]

        await agent.stop()

    @pytest.mark.asyncio
    async def test_audio_chunk_callback(self, mock_server: MockDeepgramServer):
        """Test on_audio_chunk callback fires on binary messages."""
        agent = await create_connected_agent(mock_server)

        audio_chunks_received: list[tuple] = []

        def on_chunk(pcm_array, sample_rate):
            audio_chunks_received.append((pcm_array.shape[0], sample_rate))

        agent.on_audio_chunk = on_chunk

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Send a binary audio chunk via the server protocol
        # The mock server sends greeting audio, so chunks should arrive
        # via the receive loop
        await asyncio.sleep(0.5)

        # At least the greeting audio chunks should have fired callbacks
        assert len(audio_chunks_received) >= mock_server.greeting_audio_chunks, (
            f"Expected at least {mock_server.greeting_audio_chunks} chunks, got {len(audio_chunks_received)}"
        )

        # Verify sample rate is correct (24kHz)
        for chunk_len, sr in audio_chunks_received:
            assert sr == AGENT_OUTPUT_SAMPLE_RATE, f"Expected {AGENT_OUTPUT_SAMPLE_RATE}Hz, got {sr}Hz"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_connect_timeout_no_welcome(self):
        """Test that connect fails gracefully when server doesn't send Welcome."""
        # Create a server that doesn't send Welcome
        server = MockDeepgramServer()
        server.send_welcome = False
        await server.start()

        try:
            agent = await create_connected_agent(server)
            connected = await agent.connect()
            assert not connected, "Connect should fail when server doesn't send Welcome"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_settings_error_handling(self, mock_server: MockDeepgramServer):
        """Test that connect handles Settings rejection gracefully."""
        mock_server.send_error_on_settings = True
        mock_server.error_description = "Invalid audio configuration"

        agent = await create_connected_agent(mock_server)
        connected = await agent.connect()

        assert not connected, "Connect should fail when Settings are rejected"

    @pytest.mark.asyncio
    async def test_server_error_message(self, mock_server: MockDeepgramServer):
        """Test that Error messages from server are handled gracefully (no crash)."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Send an Error message (server-side error)
        await mock_server.inject_message({
            "type": "Error",
            "description": "Internal server error — voice processing failed",
        })

        await asyncio.sleep(0.2)
        # Agent should still be running and not crash
        assert agent.is_running
        await agent.stop()

    @pytest.mark.asyncio
    async def test_clean_stop_during_streaming(self, mock_server: MockDeepgramServer):
        """Test that stop() works cleanly while messages are streaming."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Start streaming lots of messages
        async def stream_messages():
            for _ in range(20):
                if not agent.is_running:
                    break
                await agent._ws.send(SILENT_AUDIO_CHUNK)
                await asyncio.sleep(0.01)

        stream_task = asyncio.create_task(stream_messages())
        await asyncio.sleep(0.05)

        # Stop while streaming is active
        await agent.stop()
        stream_task.cancel()

        assert not agent.is_running
        # No error should be raised — stop is clean

    @pytest.mark.asyncio
    async def test_keepalive_ignored(self, mock_server: MockDeepgramServer):
        """Test that KeepAlive messages are ignored (no response sent).

        Deepgram documentation says not to respond to KeepAlive.
        """
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        text_count_before = len(mock_server.received_text_messages)

        await mock_server.inject_message({"type": "KeepAlive"})

        await asyncio.sleep(0.2)

        # No response should have been sent for KeepAlive
        text_count_after = len(mock_server.received_text_messages)
        assert text_count_after == text_count_before, (
            f"KeepAlive should not trigger any response (text msgs: {text_count_before} → {text_count_after})"
        )

        await agent.stop()

    @pytest.mark.asyncio
    async def test_close_message_stops_agent(self, mock_server: MockDeepgramServer):
        """Test that Close message stops the agent."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        assert agent.is_running

        await mock_server.inject_message({"type": "Close"})

        await asyncio.sleep(0.3)

        # Agent should stop after Close
        assert not agent.is_running, "Agent should stop after receiving Close message"

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, mock_server: MockDeepgramServer):
        """Test that calling stop() multiple times doesn't raise errors."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Call stop multiple times
        await agent.stop()
        await agent.stop()
        await agent.stop()

        assert not agent.is_running

    @pytest.mark.asyncio
    async def test_connect_without_functions(self, mock_server: MockDeepgramServer):
        """Test that connect works with empty function schemas list."""
        import copy

        agent = await create_connected_agent(mock_server)

        # Monkey-patch to inject empty functions
        async def patched_connect_no_funcs() -> bool:
            import websockets as ws_module
            from voice.function_executor import get_function_schemas

            agent._ws = await ws_module.connect(
                MOCK_WS_URL,
                subprotocols=["token", agent.api_key],
            )

            welcome = await asyncio.wait_for(agent._ws.recv(), timeout=10.0)
            if isinstance(welcome, str):
                data = json.loads(welcome)
                if data.get("type") != "Welcome":
                    return False

            settings_payload = copy.deepcopy(AGENT_SETTINGS)
            settings_payload.setdefault("agent", {}).setdefault("think", {})
            # Intentionally NOT adding functions

            await agent._ws.send(json.dumps(settings_payload))

            response = await asyncio.wait_for(agent._ws.recv(), timeout=15.0)
            if isinstance(response, str):
                data = json.loads(response)
                if data.get("type") == "SettingsApplied":
                    agent._settings_applied.set()
                    return True
            return False

        agent.connect = patched_connect_no_funcs  # type: ignore
        connected = await agent.connect()
        assert connected, "Connect should work without function schemas"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_concurrent_function_calls(self, mock_server: MockDeepgramServer):
        """Test that multiple concurrent function calls all get responses."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Send 3 function calls simultaneously
        for i in range(3):
            await mock_server.inject_function_call(
                function_name="get_system_status",
                function_call_id=f"call_concurrent_{i}",
                arguments={},
            )

        await asyncio.sleep(2.0)

        # All 3 should have responses
        assert len(mock_server.function_call_responses) == 3, (
            f"Expected 3 responses, got {len(mock_server.function_call_responses)}"
        )
        call_ids = {r["function_call_id"] for r in mock_server.function_call_responses}
        assert call_ids == {"call_concurrent_0", "call_concurrent_1", "call_concurrent_2"}

        await agent.stop()

    @pytest.mark.asyncio
    async def test_user_spoke_before_greeting_enables_mic(self, mock_server: MockDeepgramServer):
        """Test that if user speaks before greeting is done, mic is enabled early."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected

        # Don't start conversation yet — we want to test mic enablement
        # _can_send_audio should NOT be set yet
        assert not agent._can_send_audio.is_set(), "Mic should not be enabled before greeting"

        # Start conversation — this triggers _audio_send_loop which waits for _can_send_audio
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Simulate user speaking before greeting is done
        await mock_server.inject_message({"type": "UserStartedSpeaking"})

        await asyncio.sleep(0.2)

        # _can_send_audio should now be set (user spoke, mic should enable)
        assert agent._can_send_audio.is_set(), "Mic should be enabled when user speaks before greeting"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_full_transcript_accumulation(self, mock_server: MockDeepgramServer):
        """Test that full_transcript accumulates all final transcripts."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Send multiple final transcripts
        transcripts = [
            "hello barq",
            "minimize chrome",
            "open file reports.txt",
            "what is the weather like",
        ]
        for t in transcripts:
            await mock_server.inject_message({
                "type": "UserTranscript",
                "transcript": t,
                "is_final": True,
            })
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.2)

        full = agent.full_transcript
        for t in transcripts:
            assert t in full, f"Transcript '{t}' should be in full_transcript"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_take_screenshot(self, mock_server: MockDeepgramServer):
        """Test take_screenshot function returns expected schema."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        await mock_server.inject_function_call(
            function_name="take_screenshot",
            function_call_id="call_ss_001",
            arguments={},
        )

        await asyncio.sleep(1.0)

        assert len(mock_server.function_call_responses) >= 1
        response = mock_server.function_call_responses[0]
        assert response["type"] == "FunctionCallResponse"
        assert response["function_call_id"] == "call_ss_001"
        # Screenshot may fail if no display (headless), but schema should work
        assert "output" in response

        await agent.stop()

    @pytest.mark.asyncio
    async def test_clipboard_read(self, mock_server: MockDeepgramServer):
        """Test clipboard read function."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        await mock_server.inject_function_call(
            function_name="clipboard",
            function_call_id="call_cb_001",
            arguments={"action": "read"},
        )

        await asyncio.sleep(0.5)

        assert len(mock_server.function_call_responses) >= 1
        response = mock_server.function_call_responses[0]
        assert response["output"]["status"] == "success" or response["output"]["status"] == "error"
        if response["output"]["status"] == "success":
            assert "content" in response["output"]

        await agent.stop()

    @pytest.mark.asyncio
    async def test_focus_window(self, mock_server: MockDeepgramServer):
        """Test focus_window function handles missing window gracefully."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Focus a window that doesn't exist — should return error gracefully
        await mock_server.inject_function_call(
            function_name="focus_window",
            function_call_id="call_fw_001",
            arguments={"window_name": "_nonexistent_window_xyz_"},
        )

        await asyncio.sleep(0.5)

        assert len(mock_server.function_call_responses) >= 1
        response = mock_server.function_call_responses[0]
        assert response["output"]["status"] in ("success", "error"), f"Unexpected status: {response['output'].get('status')}"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_set_app_volume(self, mock_server: MockDeepgramServer):
        """Test set_app_volume function."""
        agent = await create_connected_agent(mock_server)

        connected = await agent.connect()
        assert connected
        await agent.start_conversation()
        await asyncio.sleep(0.3)

        # Set master volume (no app_name)
        await mock_server.inject_function_call(
            function_name="set_app_volume",
            function_call_id="call_vol_001",
            arguments={"level": 50},
        )

        await asyncio.sleep(0.5)

        assert len(mock_server.function_call_responses) >= 1
        response = mock_server.function_call_responses[0]
        # Volume may fail if no audio hardware, but should not crash
        assert "output" in response

        await agent.stop()

    @pytest.mark.asyncio
    async def test_settings_applied_after_connect(self, mock_server: MockDeepgramServer):
        """Test that _settings_applied event is properly set after connect."""
        agent = await create_connected_agent(mock_server)

        assert not agent._settings_applied.is_set(), "Settings should not be applied before connect"

        connected = await agent.connect()
        assert connected
        assert agent._settings_applied.is_set(), "Settings should be applied after connect"

        await agent.stop()
