"""
Deepgram Voice Agent for BARQ.

Manages a full STT → LLM → TTS pipeline via Deepgram's managed Voice Agent API.
Connects via WebSocket to wss://agent.deepgram.com/, sends the Voice Agent
configuration, streams microphone audio, and plays back responses.

Architecture:
  Wake word (local Vosk) → Deepgram Voice Agent (STT + LLM + TTS) → Audio out

The Voice Agent handles:
  - Speech-to-text (Deepgram flux-general-en)
  - LLM reasoning (Google Gemini 3.1 Flash Lite)
  - Text-to-speech (Deepgram aura-2-odysseus-en)

BARQ only handles:
  - Wake word detection (Vosk, local)
  - Audio capture from mic → agent
  - Audio playback from agent → speakers
"""

import asyncio
import json
import queue
import threading
from typing import Optional

import numpy as np

from config import get_settings


# ── Voice Agent Settings (from user's config) ──────────────────────────

AGENT_SETTINGS = {
    "type": "Settings",
    "audio": {
        "input": {
            "encoding": "linear16",
            "sample_rate": 48000,
        },
        "output": {
            "encoding": "linear16",
            "sample_rate": 24000,
            "container": "none",
        },
    },
    "agent": {
        "listen": {
            "provider": {
                "type": "deepgram",
                "version": "v2",
                "model": "flux-general-en",
            },
        },
        "think": {
            "provider": {
                "type": "google",
                "model": "gemini-3.1-flash-lite",
            },
            "prompt": (
                "#Role\n"
                "You are a general-purpose virtual assistant speaking to users over the phone. "
                "Your task is to help them find accurate, helpful information across a wide range "
                "of everyday topics.\n\n"
                "#General Guidelines\n"
                "-Be warm, friendly, and professional.\n"
                "-Speak clearly and naturally in plain language.\n"
                "-Keep most responses to 1–2 sentences and under 120 characters unless "
                "the caller asks for more detail (max: 300 characters).\n"
                "-Do not use markdown formatting.\n"
                "-Use line breaks in lists.\n"
                "-If unclear, ask for clarification.\n"
                "-If asked about your well-being, respond briefly and kindly.\n"
                "-Use active listening cues.\n"
                "-Be warm and understanding, but concise.\n"
                "\n"
                "#Greeting\n"
                "Start with: \"Hi there, I'm your virtual assistant—how can I help today?\"\n"
                "\n"
                "#Closing\n"
                "Always ask: \"Is there anything else I can help you with today?\"\n"
                "Then say: \"Thanks for calling. Take care and have a great day!\""
            ),
        },
        "speak": {
            "provider": {
                "type": "deepgram",
                "model": "aura-2-odysseus-en",
            },
        },
        "greeting": "Hello! How may I help you?",
    },
}

# Deepgram Voice Agent WebSocket endpoint
# Use /v1/agent/converse for the managed voice pipeline
AGENT_WS_URL = "wss://agent.deepgram.com/v1/agent/converse"

# Audio capture settings (mic → agent requires 48kHz)
AGENT_INPUT_SAMPLE_RATE = 48000
AGENT_INPUT_BLOCK_SIZE = 2400  # 50ms at 48kHz

# Audio playback settings (agent output is 24kHz raw PCM)
AGENT_OUTPUT_SAMPLE_RATE = 24000


class DeepgramVoiceAgent:
    """Manages a Deepgram Voice Agent WebSocket session.

    Creates a connection to Deepgram's managed voice pipeline,
    streams microphone audio, and plays back responses.

    Usage:
        agent = DeepgramVoiceAgent(api_key=...)
        await agent.connect()
        await agent.start_conversation()
        # ... conversation runs until stop is called ...
        await agent.stop()
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.settings = get_settings()
        self._ws: Optional[any] = None  # websocket connection
        self._running = False
        self._settings_applied = asyncio.Event()
        # Wait for agent greeting to finish before sending mic audio
        self._can_send_audio = asyncio.Event()
        self._input_stream: Optional[any] = None  # sd.InputStream
        self._send_task: Optional[asyncio.Task] = None
        self._output_thread: Optional[threading.Thread] = None
        self._captured_text: list[str] = []

        # Thread-safe queues for audio bridge
        # Callback-based InputStream puts data into _audio_queue (background thread)
        # Async task gets from _audio_queue and sends via WebSocket
        self._audio_queue: queue.Queue = queue.Queue(maxsize=100)
        # Output queue: received audio chunks are played sequentially
        self._audio_output_queue: queue.Queue = queue.Queue(maxsize=100)

        # Callbacks — wired by the conversation listener
        self.on_interim_transcript = None  # callback(text)
        self.on_final_transcript = None    # callback(text)
        self.on_agent_speaking = None      # callback()
        self.on_agent_done_speaking = None # callback()
        self.on_audio_chunk = None         # callback(pcm_array, sample_rate)

        # Sentinel for output thread shutdown
    _STOP_SENTINEL = (None, None)

    @property
    def is_running(self) -> bool:
        return self._running

    async def connect(self) -> bool:
        """Connect to the Deepgram Voice Agent WebSocket.

        Protocol:
        1. Open WebSocket connection with auth subprotocol
        2. Receive "Welcome" message from server
        3. Send Settings configuration
        4. Receive "SettingsApplied" confirmation

        Returns:
            True if connected and configured successfully.
            False on any protocol or connection error.
        """
        try:
            import websockets as ws_module
            self._ws = await ws_module.connect(
                AGENT_WS_URL,
                subprotocols=["token", self.api_key],
            )
            print("[DeepgramAgent] WebSocket connected")

            # ── Step 1: Receive Welcome message ─────────────────────
            # The server sends a Welcome message immediately after
            # connection to confirm the protocol is ready.
            welcome = await asyncio.wait_for(
                self._ws.recv(), timeout=10.0
            )
            if isinstance(welcome, str):
                data = json.loads(welcome)
                if data.get("type") != "Welcome":
                    print(f"[DeepgramAgent] Expected Welcome, got: {data.get('type', 'unknown')}")
                    return False
                print("[DeepgramAgent] Welcome received — protocol ready")
            else:
                print("[DeepgramAgent] Expected text Welcome, got binary")
                return False

            # ── Step 2: Send Settings configuration ─────────────────
            settings_json = json.dumps(AGENT_SETTINGS)
            await self._ws.send(settings_json)
            print("[DeepgramAgent] Settings sent — waiting for confirmation...")

            # ── Step 3: Wait for SettingsApplied confirmation ───────
            response = await asyncio.wait_for(
                self._ws.recv(), timeout=15.0
            )
            if isinstance(response, str):
                data = json.loads(response)
                if data.get("type") == "SettingsApplied":
                    print("[DeepgramAgent] Settings applied — agent ready")
                    self._settings_applied.set()
                    return True
                else:
                    print(f"[DeepgramAgent] Expected SettingsApplied, got: {data.get('type', 'unknown')}")
                    return False
            else:
                print("[DeepgramAgent] Expected text SettingsApplied, got binary")
                return False

        except asyncio.TimeoutError:
            print("[DeepgramAgent] Timeout during connect handshake")
            return False
        except Exception as e:
            print(f"[DeepgramAgent] Connection failed: {e}")
            return False

    async def start_conversation(self, audio_device: Optional[int] = None):
        """Start streaming microphone audio and receiving responses.

        Runs two concurrent tasks:
        1. Audio capture → send as Media messages (48kHz)
        2. Receive messages → play audio / dispatch callbacks

        Args:
            audio_device: sounddevice input device index. None = default.
        """
        if not self._running:
            self._running = True
            self._send_task = asyncio.create_task(
                self._audio_send_loop(audio_device)
            )
            asyncio.create_task(self._receive_loop())

    async def stop(self):
        """Stop the conversation and close the WebSocket connection."""
        self._running = False

        # Cancel the send task
        if self._send_task:
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass
            self._send_task = None

        # Close input stream
        if self._input_stream:
            try:
                self._input_stream.stop()
                self._input_stream.close()
            except Exception:
                pass
            self._input_stream = None

        # Stop output thread by sending sentinel
        try:
            self._audio_output_queue.put_nowait(self._STOP_SENTINEL)
        except queue.Full:
            pass

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._settings_applied.clear()
        self._can_send_audio.clear()
        print("[DeepgramAgent] Disconnected")

    # ── Audio Send Loop (mic → agent) ──────────────────────────────

    def _audio_capture_callback(self, indata, frames, time_info, status):
        """sounddevice InputStream callback — runs on a background thread.

        Puts audio data into a thread-safe queue. The async task reads
        from this queue and sends via WebSocket.

        Args:
            indata: numpy array of captured audio (int16)
            frames: number of frames
            time_info: timing info (unused)
            status: PortAudio status flags
        """
        if status:
            print(f"[DeepgramAgent] Audio callback status: {status}")
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
            print("[DeepgramAgent] Audio queue full — dropping chunk")

    def _output_loop(self):
        """Playback thread — runs sd.play() + sd.wait() sequentially.

        The Voice Agent sends audio in small chunks (~20ms each). These
        must be played sequentially without overlap. This thread reads
        from _audio_output_queue and plays one chunk at a time.
        """
        try:
            import sounddevice as sd
            from .audio_device import resolve_output_device

            output_device = resolve_output_device(
                self.settings.audio_output_device
            )

            while self._running:
                try:
                    item = self._audio_output_queue.get(timeout=0.5)
                    if item is self._STOP_SENTINEL:
                        break
                    pcm_array, sample_rate = item
                    sd.play(
                        pcm_array,
                        samplerate=sample_rate,
                        device=output_device,
                    )
                    sd.wait()
                except queue.Empty:
                    continue
        except Exception as e:
            print(f"[DeepgramAgent] Output thread error: {e}")

    async def _audio_send_loop(self, device: Optional[int] = None):
        """Capture microphone audio via callback-based InputStream and send as raw PCM.

        Uses a callback-based InputStream to avoid blocking the asyncio event loop.
        The callback runs on a background thread and puts data into a thread-safe
        queue. The async task reads from the queue and sends via WebSocket.

        Waits for:
        1. SettingsApplied (handshake complete)
        2. Agent greeting to finish (ConversationText or timeout)

        Then starts the output playback thread and mic capture.
        """
        # Step 1: Wait for SettingsApplied
        await self._settings_applied.wait()

        # Step 2: Wait for greeting to finish
        print("[DeepgramAgent] Waiting for greeting to finish before starting mic...")
        try:
            await asyncio.wait_for(self._can_send_audio.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            print("[DeepgramAgent] Timeout waiting for greeting — starting mic anyway")
            self._can_send_audio.set()

        import sounddevice as sd

        # Resolve input device
        from .audio_device import resolve_input_device
        if device is None:
            device = resolve_input_device(self.settings.audio_input_device)

        # Start output playback thread
        self._output_thread = threading.Thread(
            target=self._output_loop, daemon=True
        )
        self._output_thread.start()

        try:
            # Open callback-based InputStream (non-blocking, runs on background thread)
            self._input_stream = sd.InputStream(
                device=device,
                samplerate=AGENT_INPUT_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=AGENT_INPUT_BLOCK_SIZE,
                callback=self._audio_capture_callback,
            )
            self._input_stream.start()
            print("[DeepgramAgent] Mic streaming started — callback mode")

            # Async loop: read from thread-safe queue and send via WebSocket
            while self._running:
                try:
                    # Get audio data from the callback thread via thread pool
                    data = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._audio_queue.get(timeout=0.1),
                    )
                    audio_bytes = data.tobytes()
                    await self._ws.send(audio_bytes)
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"[DeepgramAgent] Send error: {e}")
                    break

        except Exception as e:
            print(f"[DeepgramAgent] Audio capture error: {e}")
        finally:
            self._running = False
            print("[DeepgramAgent] Audio send loop ended")

    # ── Receive Loop (agent → us) ──────────────────────────────────

    async def _receive_loop(self):
        """Receive messages from the Voice Agent WebSocket.

        Handles:
        - Binary messages → Audio samples (raw PCM 24kHz)
        - JSON messages → UserStartedSpeaking, AgentThinking, etc.

        IMPORTANT: The server sends messages in this order after connect:
          1. Welcome (text, handled in connect())
          2. SettingsApplied (text, handled in connect())
          3. BINARY — greeting audio chunks (960 bytes each at 24kHz)
          4. ConversationText (text) — "Hello! How may I help you?"
          5. History (text)
          6. BINARY — more audio
          7. ... (listening for user input)

        We must NOT send any text messages back except:
          - KeepAlive (only after 30s of inactivity, which should never happen)
        """
        if not self._ws:
            return

        try:
            while self._running:
                try:
                    message = await asyncio.wait_for(
                        self._ws.recv(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    print("[DeepgramAgent] Receive timeout — connection may be idle, continuing")
                    continue

                if isinstance(message, bytes):
                    # Audio chunk — raw PCM at 24kHz
                    await self._handle_audio_bytes(message)
                else:
                    # JSON message
                    try:
                        data = json.loads(message)
                        await self._handle_json_message(data)
                    except json.JSONDecodeError:
                        print(f"[DeepgramAgent] Non-JSON message: {message[:100]}")

        except Exception as e:
            print(f"[DeepgramAgent] Receive loop error: {e}")
        finally:
            self._running = False
            print("[DeepgramAgent] Receive loop ended")

    async def _handle_audio_bytes(self, audio_bytes: bytes):
        """Process raw PCM audio from the agent.

        Queues the audio for sequential playback via _output_thread.
        Also dispatches to on_audio_chunk callback for state updates.

        Args:
            audio_bytes: Raw linear16 PCM audio at 24kHz (container=none).
        """
        # Convert bytes to float32 numpy array
        pcm_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(
            np.float32
        ) / 32768.0

        # Queue for sequential playback (thread-safe)
        try:
            self._audio_output_queue.put_nowait(
                (pcm_array, AGENT_OUTPUT_SAMPLE_RATE)
            )
        except queue.Full:
            print("[DeepgramAgent] Output queue full — dropping audio chunk")

        # Dispatch to callback (conversation listener for state updates)
        if self.on_audio_chunk:
            self.on_audio_chunk(pcm_array, AGENT_OUTPUT_SAMPLE_RATE)

    async def _handle_json_message(self, data: dict):
        """Process a JSON control message from the agent.

        Args:
            data: Parsed JSON dict with message type.
        """
        msg_type = data.get("type", "")

        if msg_type == "SettingsApplied":
            self._settings_applied.set()

        elif msg_type == "UserStartedSpeaking":
            print("[DeepgramAgent] User started speaking — barge-in")
            self._captured_text = []
            # ── Barge-in: immediately stop TTS playback ──────────────
            # The user interrupted the agent's response. Stop audio output
            # immediately, flush buffered chunks, and tell the frontend
            # that the agent is no longer speaking.
            try:
                import sounddevice as _sd
                _sd.stop()  # Interrupts sd.play() — sd.wait() returns immediately
                # Flush the output queue so stale chunks aren't played
                while not self._audio_output_queue.empty():
                    try:
                        self._audio_output_queue.get_nowait()
                    except queue.Empty:
                        break
                print("[DeepgramAgent] Barge-in: TTS stopped, output queue flushed")
            except Exception as e:
                print(f"[DeepgramAgent] Barge-in stop error: {e}")
            # Notify frontend that agent stopped speaking
            if self.on_agent_done_speaking:
                self.on_agent_done_speaking()
            # If user speaks before agent finishes greeting, enable audio sending
            if not self._can_send_audio.is_set():
                self._can_send_audio.set()
                print("[DeepgramAgent] User spoke before greeting done — enabling mic now")

        elif msg_type == "UserTranscript":
            transcript = data.get("transcript", "")
            is_final = data.get("is_final", False)
            if is_final and transcript.strip():
                self._captured_text.append(transcript.strip())
                if self.on_final_transcript:
                    self.on_final_transcript(transcript.strip())
            elif transcript.strip():
                if self.on_interim_transcript:
                    self.on_interim_transcript(transcript)

        elif msg_type == "AgentThinking":
            print("[DeepgramAgent] Agent is thinking...")

        elif msg_type == "AgentStartedSpeaking":
            print("[DeepgramAgent] Agent is speaking")
            if self.on_agent_speaking:
                self.on_agent_speaking()

        elif msg_type == "AgentAudioDone":
            print("[DeepgramAgent] Agent finished speaking")
            if not self._can_send_audio.is_set():
                self._can_send_audio.set()
                print("[DeepgramAgent] Agent greeting done — ready to receive mic audio")
            if self.on_agent_done_speaking:
                self.on_agent_done_speaking()

        elif msg_type == "ConversationText":
            # Greeting or agent response text — signal that mic audio can start
            # The server sends this after the greeting audio finishes.
            if not self._can_send_audio.is_set():
                self._can_send_audio.set()
                print("[DeepgramAgent] Greeting text received — mic audio can start now")

        elif msg_type == "FunctionCallRequest":
            print(f"[DeepgramAgent] Function call: {data}")

        elif msg_type == "KeepAlive":
            # Server keepalive — do NOT respond. The Voice Agent API
            # does not expect a response for keepalive, and sending one
            # will cause a "Text message received from client did not
            # match any of the formats we expect" error.
            pass

        elif msg_type == "Close":
            print("[DeepgramAgent] Server requested close")
            self._running = False

        elif msg_type == "Error":
            error_msg = data.get("description", data.get("message", "Unknown"))
            print(f"[DeepgramAgent] Error: {error_msg}")

    @property
    def full_transcript(self) -> str:
        """Get the full accumulated transcript from this conversation."""
        return " ".join(self._captured_text)


def get_agent_config_json() -> dict:
    """Return the Voice Agent configuration as a dict.

    Can be inspected or modified at runtime.
    """
    return dict(AGENT_SETTINGS)
