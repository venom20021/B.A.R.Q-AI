"""
Conversation listener for continuous voice interaction.

Powered by the Deepgram Voice Agent — a managed STT → LLM → TTS pipeline.
Wake word (Vosk) triggers the conversation, then the Voice Agent handles
all speech processing. Say "nothing" to end the conversation.
"""

import asyncio
import re
from collections.abc import Awaitable
from typing import Callable, Optional

from ai.responder import BARQResponder
from voice.evolution_logger import get_evolution_logger
from voice.websocket_manager import VoiceWSManager
from voice.speech import SpeechProcessor

# Lazy import for Deepgram Voice Agent
_voice_agent_instance = None

def get_voice_agent_instance():
    global _voice_agent_instance
    if _voice_agent_instance is None:
        from config import get_settings
        settings = get_settings()
        if settings.deepgram_api_key:
            from .deepgram_agent import DeepgramVoiceAgent
            _voice_agent_instance = DeepgramVoiceAgent(api_key=settings.deepgram_api_key)
    return _voice_agent_instance

def reset_voice_agent_instance():
    global _voice_agent_instance
    _voice_agent_instance = None

# Type aliases for optional command callbacks
ParseCommandFn = Callable[[str, bool, Optional[str]], Awaitable[dict]]
ExecuteCommandFn = Callable[[str, dict], Awaitable[str]]


class ConversationListener:
    """Manages the Deepgram Voice Agent conversation loop.

    Once activated (via wake word), connects to the Voice Agent WebSocket.
    The Voice Agent handles STT → LLM → TTS internally.
    Say "nothing" (or another exit phrase) to end and return to wake-word standby.
    """

    def __init__(
        self,
        stt: SpeechProcessor,
        responder: BARQResponder,
        on_stop: Optional[Callable] = None,
        parse_command: Optional[ParseCommandFn] = None,
        execute_command: Optional[ExecuteCommandFn] = None,
    ):
        self.stt = stt
        self.responder = responder
        self.ws_manager = VoiceWSManager.get_instance()
        self.evo_logger = get_evolution_logger()
        self.on_stop = on_stop
        self._conversation_active = False
        self._loop_task: Optional[asyncio.Task] = None
        self._managed_loop: Optional[asyncio.AbstractEventLoop] = None
        self._exit_phrases = [
            "nothing", "that's all", "we're done",
            "end conversation", "stop conversation",
            "go to sleep", "shut down", "that's it for now",
        ]
        self._parse_command: Optional[ParseCommandFn] = parse_command
        self._execute_command: Optional[ExecuteCommandFn] = execute_command

    @property
    def is_active(self) -> bool:
        return self._conversation_active

    async def start_conversation(self):
        """Start the Voice Agent conversation loop in the background."""
        if self._conversation_active:
            return
        self._conversation_active = True
        self.responder.conversation.start_session("voice_conversation")

        print("[Conversation] Deepgram Voice Agent starting...")
        self._loop_task = asyncio.create_task(self._conversation_loop())

    async def stop_conversation(self):
        """End the conversation loop and return to wake-word standby."""
        self._conversation_active = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        self.responder.conversation.end_session()

        await self.ws_manager.cancel_all()

        if self._managed_loop is not None and self._managed_loop.is_running():
            try:
                self._managed_loop.stop()
                print("[Conversation] Managed event loop stopped")
            except RuntimeError:
                pass

        self.ws_manager.fire(self.ws_manager.broadcast_state("idle"))

        if self.on_stop:
            try:
                self.on_stop()
            except Exception as e:
                print(f"[Conversation] on_stop callback error: {e}")

        print("[Conversation] Conversation ended — back to wake word standby")

    # ── Deepgram Voice Agent loop ──────────────────────────────────

    async def _conversation_loop(self):
        """Connect to Deepgram Voice Agent and stream audio.

        The Voice Agent handles STT → Gemini LLM → TTS internally.
        Streams microphone audio and plays back responses.

        Retries WebSocket connection up to 5 times with exponential
        backoff (1s, 3s, 9s, 27s, 81s) if the connection drops
        unexpectedly during a conversation. This handles transient
        network issues without needing a full process restart.

        If the entire Python process crashes (exit code 3221226356),
        recovery is handled at the Electron sidecar level in
        python-bridge.ts (_handleProcessCrash).
        """

        max_retries = 5
        retry_delay = 1.0  # initial delay in seconds

        for attempt in range(1, max_retries + 1):
            if not self._conversation_active:
                return

            agent = get_voice_agent_instance()
            if not agent:
                print("[VoiceAgent] No Deepgram API key configured — cannot start conversation")
                self._conversation_active = False
                return

            try:
                connected = await agent.connect()
                if not connected:
                    print(f"[VoiceAgent] Failed to connect (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        wait = retry_delay * (3 ** (attempt - 1))  # 1, 3, 9, 27, 81
                        print(f"[VoiceAgent] Retrying in {wait:.0f}s...")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        print("[VoiceAgent] All connection attempts failed — ending conversation")
                        self._conversation_active = False
                        return

                # Wire up agent callbacks
                agent.on_interim_transcript = lambda text: self.ws_manager.fire(
                    self.ws_manager.broadcast({
                        "type": "caption_user",
                        "text": text,
                        "isFinal": False,
                    })
                )
                agent.on_final_transcript = self._on_agent_final_transcript
                agent.on_agent_speaking = lambda: self.ws_manager.fire(
                    self.ws_manager.broadcast_state("speaking")
                )
                agent.on_agent_done_speaking = lambda: self.ws_manager.fire(
                    self.ws_manager.broadcast_state("listening")
                )
                agent.on_audio_chunk = self._on_agent_audio_chunk

                self.responder.is_speaking_event.set()
                await agent.start_conversation()

                print(f"[VoiceAgent] Conversation active (attempt {attempt}/{max_retries})")

                # Wait until conversation ends
                while self._conversation_active and agent.is_running:
                    await asyncio.sleep(0.5)

                # Check why we exited the loop
                if not self._conversation_active:
                    print("[VoiceAgent] Conversation ended by user")
                    break
                elif not agent.is_running:
                    # Agent stopped unexpectedly (WS disconnected, not process crash)
                    print(f"[VoiceAgent] Agent disconnected unexpectedly (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        wait = retry_delay * (3 ** (attempt - 1))
                        print(f"[VoiceAgent] Reconnecting in {wait:.0f}s...")
                        await asyncio.sleep(wait)
                        # Reset agent state for clean reconnection
                        reset_voice_agent_instance()
                        continue
                    else:
                        print("[VoiceAgent] Max retries reached — ending conversation")
                        break

            except Exception as e:
                print(f"[VoiceAgent] Loop error: {e}")
                if attempt < max_retries:
                    wait = retry_delay * (3 ** (attempt - 1))
                    print(f"[VoiceAgent] Retrying in {wait:.0f}s...")
                    await asyncio.sleep(wait)
                    reset_voice_agent_instance()
                    continue
                else:
                    break
            finally:
                self.responder.is_speaking_event.clear()
                await agent.stop()

    def _on_agent_final_transcript(self, text: str):
        """Handle a final transcript from the Voice Agent."""
        self.ws_manager.fire(self.ws_manager.broadcast({
            "type": "caption_user",
            "text": text,
            "isFinal": True,
        }))

        if self._is_exit_command(text):
            print("[VoiceAgent] Exit command detected — stopping conversation")
            asyncio.create_task(self.stop_conversation())

    def _on_agent_audio_chunk(self, pcm_array, sample_rate: int):
        """Handle an audio chunk from the Voice Agent.

        NOTE: Playback is now handled internally by DeepgramVoiceAgent's
        _output_thread, which plays chunks sequentially via sd.play()
        + sd.wait(). This callback is kept for state tracking only.
        """
        # Playback is handled by deepgram_agent.py's _output_thread.
        # This callback exists for future state tracking (e.g., captions).
        pass

    # ── Helpers ─────────────────────────────────────────────────────

    def _is_exit_command(self, text: str) -> bool:
        """Check if user wants to end the conversation."""
        text_lower = text.lower().strip()
        for phrase in self._exit_phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", text_lower):
                return True
        return False
