"""
Conversation listener for continuous voice interaction.
After wake word detection, enters a hands-free conversation mode where BARQ
keeps listening, processes speech, and responds without requiring
the wake word to be said again for each turn.

This provides a Gemini/Alexa-like experience:
1. Wake word triggers conversation mode
2. Records with aggressive VAD (400 ms silence endpointing)
3. Transcribes speech using Whisper
4. Generates AI response via streaming Ollama
5. Sentence-aware TTS chunking — begins playback while LLM continues
6. Barge-in — user speech during playback stops audio + flushes LLM
7. "Goodbye" / silence timeout returns to wake-word-only standby
"""

import asyncio
import re
from pathlib import Path
from typing import Optional

from ai.responder import BARQResponder
from voice.speech import SpeechProcessor
from voice.interrupt_handler import InterruptHandler


# Aggressive silence endpointing defaults (overridable per-instance)
# Use conversation_listener.vad_silence_timeout to customise at runtime
VAD_SILENCE_TIMEOUT = 0.4        # seconds of silence before cutting
VAD_ENERGY_THRESHOLD = 300.0     # RMS floor
VAD_MAX_DURATION = 15.0          # safety cap


class ConversationListener:
    """Manages the continuous listening loop for back-and-forth conversation."""

    def __init__(
        self,
        stt: SpeechProcessor,
        responder: BARQResponder,
    ):
        self.stt = stt
        self.responder = responder
        self.interrupt_handler = InterruptHandler()
        self._conversation_active = False
        self._loop_task: Optional[asyncio.Task] = None
        self.vad_silence_timeout: float = VAD_SILENCE_TIMEOUT  # overridable per-instance
        self._exit_phrases = [
            "goodbye", "bye bye", "that's all", "we're done",
            "end conversation", "stop conversation", "never mind",
            "go to sleep", "shut down", "that's it for now",
        ]

    @property
    def is_active(self) -> bool:
        return self._conversation_active

    async def start_conversation(self):
        """Start the continuous conversation loop in the background."""
        if self._conversation_active:
            return
        self._conversation_active = True
        self.responder.conversation.start_session("voice_conversation")
        print("[Conversation] Hands-free conversation mode started — listening...")
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
        print("[Conversation] Conversation mode ended — back to wake word standby")

    async def trigger_conversation_turn(self, text: str) -> dict:
        """Process a single conversation turn (used by the wake word callback or API)."""
        if self._is_exit_command(text):
            await self.stop_conversation()
            goodbye = await self.responder.respond("Goodbye!")
            return {"action": "exit", "text": goodbye["text"],
                    "audio_path": goodbye.get("audio_path")}

        result = await self.responder.respond(text)
        return {
            "action": "response",
            "text": result["text"],
            "audio_path": result.get("audio_path", ""),
        }

    # ── Core conversation loop ──────────────────────────────────────

    async def _conversation_loop(self):
        """Main conversation loop: listen → transcribe → stream-respond → play → repeat.

        Uses aggressive VAD (400 ms silence), streaming LLM, and sentence-aware
        TTS chunking for sub-second first-audible latency.  Barge-in stops
        audio playback AND flushes the active LLM stream so the system is
        immediately ready for the next user utterance.
        """
        try:
            while self._conversation_active:
                # ── 1. Listen with streaming STT (interim + final) ──
                print("[Conversation] Listening for speech (streaming STT)...")
                self.responder.stt_text = ""
                text = None

                try:
                    async for result in self.stt.transcribe_streaming(
                        max_duration=VAD_MAX_DURATION,
                        silence_timeout=self.vad_silence_timeout,
                        energy_threshold=VAD_ENERGY_THRESHOLD,
                    ):
                        if result["type"] == "interim":
                            self.responder.stt_text = result["text"]
                            print(f"[Conversation] STT interim: '{result['text']}'")
                        elif result["type"] == "final":
                            text = result["text"] if result["text"].strip() else None
                            self.responder.stt_text = ""  # clear after final
                except Exception as e:
                    print(f"[Conversation] STT streaming error: {e}")
                    text = None
                    self.responder.stt_text = ""

                if not self._conversation_active:
                    break

                if text is None or not text.strip():
                    print("[Conversation] No speech detected — ending conversation")
                    await self.stop_conversation()
                    return

                print(f"[Conversation] User: '{text}'")

                # ── 2. Check exit command ────────────────────────────
                if self._is_exit_command(text):
                    print("[Conversation] Exit command detected")
                    result = await self.responder.respond(
                        "Goodbye! Say the wake word when you need me again."
                    )
                    audio_path = result.get("audio_path", "")
                    if audio_path:
                        self.responder.is_speaking = True
                        try:
                            await self.interrupt_handler.play_with_interrupt(
                                str(audio_path),
                                listen_for_interrupt=False,
                            )
                        finally:
                            self.responder.is_speaking = False
                    await self.stop_conversation()
                    return

                # ── 3. Streaming respond with sentence-aware TTS ─────
                try:
                    self.responder.is_speaking = True
                    interrupted = False

                    async for chunk in self.responder.stream_respond(text):
                        if self._interrupt_requested():
                            # Barge-in signalled during TTS gen — cancel
                            self.responder._interrupt_requested = True
                            interrupted = True
                            break

                        audio_path = chunk.get("audio_path", "")
                        if audio_path and Path(audio_path).exists():
                            playback_interrupted = (
                                await self.interrupt_handler.play_with_interrupt(
                                    str(audio_path),
                                    listen_for_interrupt=True,
                                )
                            )
                            if playback_interrupted:
                                # User spoke over BARQ — flush LLM stream
                                self.responder._interrupt_requested = True
                                interrupted = True
                                break

                    if interrupted:
                        print("[Conversation] Barge-in — flushing LLM & restarting listen")
                        continue

                except Exception as e:
                    print(f"[Conversation] Error processing response: {e}")
                    await asyncio.sleep(0.5)
                    continue
                finally:
                    self.responder.is_speaking = False

        except asyncio.CancelledError:
            print("[Conversation] Conversation loop cancelled")
            raise
        except Exception as e:
            print(f"[Conversation] Conversation loop error: {e}")
            self._conversation_active = False
            self.responder.conversation.end_session()

    # ── Helpers ─────────────────────────────────────────────────────

    def _interrupt_requested(self) -> bool:
        """Check whether the responder has been flagged for interrupt."""
        return self.responder._interrupt_requested

    def _is_exit_command(self, text: str) -> bool:
        """Check if user wants to end the conversation."""
        text_lower = text.lower().strip()
        for phrase in self._exit_phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", text_lower):
                return True
        return False
