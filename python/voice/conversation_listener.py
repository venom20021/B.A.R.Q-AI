"""
Conversation listener for continuous voice interaction.
After wake word detection, enters a persistent listening mode where BARQ
keeps the mic on and processes speech until you say "nothing".

Flow:
1. Wake word triggers conversation mode
2. Records with VAD (silence = just re-listen; no auto-exit)
3. Transcribes speech using faster-whisper
4. Generates AI response via streaming Ollama
5. Sentence-aware TTS chunking — begins playback while LLM continues
6. Barge-in — user speech during playback stops audio + flushes LLM
7. Say "nothing" → returns to wake-word standby
8. Say "computer" → starts listening again
"""

import asyncio
import re
import time
from pathlib import Path
from collections.abc import Awaitable
from typing import Callable, Optional

from ai.responder import BARQResponder
from voice.evolution_logger import get_evolution_logger
from voice.interrupt_handler import InterruptHandler
from voice.pipeline import (
    TranscriptionFrame as PipelineTranscriptionFrame,
)
from voice.websocket_manager import VoiceWSManager
from voice.pipeline import (
    TTSAudioFrame as PipelineTTSAudioFrame,
)
from voice.speech import SpeechProcessor

# Type aliases for optional command callbacks (both are async)
ParseCommandFn = Callable[[str, bool, Optional[str]], Awaitable[dict]]
# execute_command(text, action_result) -> str (spoken confirmation)
ExecuteCommandFn = Callable[[str, dict], Awaitable[str]]


# Silence endpointing defaults (overridable per-instance)
# Use conversation_listener.vad_silence_timeout to customise at runtime.
# 400ms balances responsiveness with not cutting off natural pauses.
# Increase to 0.6-0.8s for slower-paced conversations.
VAD_SILENCE_TIMEOUT = 0.4       # seconds of silence before cutting (400ms for natural feel)
VAD_MAX_DURATION = 15.0          # safety cap


class ConversationListener:
    """Manages the persistent listening loop for back-and-forth conversation.

    Once activated (via wake word), the mic stays on and listens continuously.
    Silence just loops back to listening — the conversation only ends when
    the user says "nothing" (or another exit phrase).

    When ``use_pipeline=True``, the inner loop uses the pipecat-inspired
    frame-based ``VoicePipeline`` for LLM → TTS processing, with
    ``InterruptFrame`` for priority-based barge-in instead of boolean flags.
    """

    def __init__(
        self,
        stt: SpeechProcessor,
        responder: BARQResponder,
        on_stop: Optional[Callable] = None,
        use_pipeline: bool = True,
        energy_threshold: float = 500.0,
        parse_command: Optional[ParseCommandFn] = None,
        execute_command: Optional[ExecuteCommandFn] = None,
    ):
        self.stt = stt
        self.responder = responder
        self.ws_manager = VoiceWSManager.get_instance()
        self.evo_logger = get_evolution_logger()
        self.use_pipeline = use_pipeline
        self.energy_threshold = energy_threshold  # RMS energy threshold for barge-in detection
        self.interrupt_handler = InterruptHandler(energy_threshold=energy_threshold)
        self.on_stop = on_stop  # callback invoked when conversation stops (e.g. to resume wake detector)
        self._conversation_active = False
        self._loop_task: Optional[asyncio.Task] = None
        self.vad_silence_timeout: float = VAD_SILENCE_TIMEOUT  # overridable per-instance
        self._managed_loop: Optional[asyncio.AbstractEventLoop] = None  # event loop to stop on conversation end
        self._exit_phrases = [
            "nothing", "that's all", "we're done",
            "end conversation", "stop conversation",
            "go to sleep", "shut down", "that's it for now",
        ]
        # Optional voice command callbacks — wired by routes.py
        self._parse_command: Optional[ParseCommandFn] = parse_command
        self._execute_command: Optional[ExecuteCommandFn] = execute_command

    @property
    def is_active(self) -> bool:
        return self._conversation_active

    async def start_conversation(self):
        """Start the continuous conversation loop in the background."""
        if self._conversation_active:
            return
        self._conversation_active = True
        self.responder.conversation.start_session("voice_conversation")

        # Start background mic monitor so the sphere shows audio wave
        # reactivity even between speech turns (before the first STT stream).
        self.stt.start_mic_monitor()

        print("[Conversation] Hands-free conversation mode started — listening...")
        if self.use_pipeline:
            print("[Conversation] Using pipecat-inspired frame-based pipeline")
            self._loop_task = asyncio.create_task(self._conversation_loop_pipeline())
        else:
            self._loop_task = asyncio.create_task(self._conversation_loop())

    async def stop_conversation(self):
        """End the conversation loop and return to wake-word standby.

        Calls ``self.on_stop`` (if set) so the wake word detector can resume
        listening after the conversation ends.

        Also stops the running asyncio event loop so that ``loop.run_forever()``
        (used in the wake word callback) can exit cleanly.
        """
        self._conversation_active = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        self.responder.conversation.end_session()

        # Stop the managed event loop (set by the wake word callback) so that
        # loop.run_forever() in the callback thread can exit cleanly.
        # This must happen BEFORE on_stop so the event loop is fully stopped
        # before the wake detector reopens its mic stream.
        if self._managed_loop is not None and self._managed_loop.is_running():
            try:
                self._managed_loop.stop()
                print("[Conversation] Managed event loop stopped")
            except RuntimeError:
                pass

        # Stop the background mic monitor (conversation is done).
        self.stt.stop_mic_monitor()

        # Broadcast idle state to frontend
        asyncio.ensure_future(self.ws_manager.broadcast_state("idle"))

        # Notify caller that conversation has stopped (e.g. resume wake detector)
        if self.on_stop:
            try:
                self.on_stop()
            except Exception as e:
                print(f"[Conversation] on_stop callback error: {e}")

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
                _stt_start = time.perf_counter()

                try:
                    async for result in self.stt.transcribe_streaming(
                        max_duration=VAD_MAX_DURATION,
                        silence_timeout=self.vad_silence_timeout,
                        energy_threshold=self.energy_threshold,
                    ):
                        if result["type"] == "interim":
                            self.responder.stt_text = result["text"]
                            self.responder.stt_confidence = result.get("confidence", 0.0)
                            # Broadcast interim STT caption to frontend
                            asyncio.ensure_future(self.ws_manager.broadcast({
                                "type": "caption_user",
                                "text": result["text"],
                                "isFinal": False,
                            }))
                            print(f"[Conversation] STT interim: '{result['text']}' (conf: {result.get('confidence', 0.0):.2%})")
                        elif result["type"] == "final":
                            text = result["text"] if result["text"].strip() else None
                            self.responder.stt_text = ""  # clear after final
                            # Record STT latency
                            stt_duration = (time.perf_counter() - _stt_start) * 1000
                            self.evo_logger.record("stt_latency", duration_ms=stt_duration, metadata={
                                "text_length": len(result["text"]),
                                "confidence": result.get("confidence", 0.0),
                                "silence_timeout": self.vad_silence_timeout,
                            })
                            # Broadcast final STT caption to frontend
                            if text:
                                asyncio.ensure_future(self.ws_manager.broadcast({
                                    "type": "caption_user",
                                    "text": text,
                                    "isFinal": True,
                                }))
                except Exception as e:
                    print(f"[Conversation] STT streaming error: {e}")
                    text = None
                    self.responder.stt_text = ""
                    self.responder.stt_confidence = 0.0

                if not self._conversation_active:
                    break

                if text is None or not text.strip():
                    print("[Conversation] No speech detected — listening again...")
                    continue

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

                # ── 3. Check if it's a voice command (open/launch/run/etc.) ──
                if self._parse_command and self._execute_command:
                    parsed = await self._parse_command(text, False, None)
                    if parsed.get("action") != "unknown":
                        print(f"[Conversation] Voice command detected: {parsed['action']} → {parsed.get('target', parsed.get('command', ''))}")
                        # Execute the command and speak the result
                        confirmation = await self._execute_command(text, parsed)
                        self.responder.is_speaking = True
                        try:
                            pcm, sr = await self.responder.speech.synthesize_pcm(confirmation)
                            await self.interrupt_handler.play_pcm_with_interrupt(
                                pcm, sr, listen_for_interrupt=True,
                            )
                        except Exception as e:
                            print(f"[Conversation] Command feedback TTS error: {e}")
                        finally:
                            self.responder.is_speaking = False
                        continue

                # ── 4. Streaming respond with sentence-aware TTS ─────
                interrupted = False
                try:
                    self.responder.is_speaking = True
                    self.responder.is_speaking_event.set()

                    async for chunk in self.responder.stream_respond(text):
                        if self._interrupt_requested():
                            self.responder._interrupt_requested = True
                            interrupted = True
                            break

                        # Pause mic monitor during TTS playback (prevents echo)
                        self.stt.stop_mic_monitor()

                        audio_pcm = chunk.get("audio_pcm")
                        if audio_pcm is not None:
                            pcm_array, sample_rate = audio_pcm
                            playback_interrupted = (
                                await self.interrupt_handler.play_pcm_with_interrupt(
                                    pcm_array, sample_rate,
                                    listen_for_interrupt=True,
                                )
                            )
                        else:
                            audio_path = chunk.get("audio_path", "")
                            if audio_path and Path(audio_path).exists():
                                playback_interrupted = (
                                    await self.interrupt_handler.play_with_interrupt(
                                        str(audio_path),
                                        listen_for_interrupt=True,
                                    )
                                )
                            else:
                                playback_interrupted = False

                        if playback_interrupted:
                            self.responder._interrupt_requested = True
                            interrupted = True
                            break

                    if interrupted:
                        print("[Conversation] Barge-in — flushing LLM & restarting listen")
                        await asyncio.sleep(0.15)
                        continue

                except Exception as e:
                    print(f"[Conversation] Error processing response: {e}")
                    await asyncio.sleep(0.5)
                    continue
                finally:
                    self.responder.is_speaking = False
                    self.responder.is_speaking_event.clear()
                    # Flush the audio input buffer to discard stale frames recorded
                    # during TTS playback. Prevents echo-spiral where BARQ hears
                    # its own voice and tries to respond.
                    try:
                        await self.stt.flush_audio_buffer()
                    except Exception as flush_err:
                        print(f"[Conversation] Buffer flush warning: {flush_err}")

        except asyncio.CancelledError:
            print("[Conversation] Conversation loop cancelled")
            raise
        except Exception as e:
            print(f"[Conversation] Conversation loop error: {e}")
            self._conversation_active = False
            self.responder.conversation.end_session()

    # ── Pipeline-based conversation loop ────────────────────────────

    async def _conversation_loop_pipeline(self):
        """Pipecat-inspired conversation loop using the frame-based pipeline.

        Uses the existing ``transcribe_streaming()`` for VAD-based STT,
        then feeds ``TranscriptionFrame`` into the LLM→TTS pipeline.
        Barge-in is handled via ``InterruptFrame`` (priority signal)
        instead of a boolean flag — the pipeline flushes its output
        and is ready for new input immediately.
        """
        try:
            while self._conversation_active:
                # ── 1. Listen with streaming STT (VAD-based) ──────────
                print("[Conversation·Pipeline] Listening for speech...")
                self.responder.stt_text = ""
                text = None
                _stt_start = time.perf_counter()

                try:
                    async for result in self.stt.transcribe_streaming(
                        max_duration=VAD_MAX_DURATION,
                        silence_timeout=self.vad_silence_timeout,
                        energy_threshold=self.energy_threshold,
                    ):
                        if result["type"] == "interim":
                            self.responder.stt_text = result["text"]
                            self.responder.stt_confidence = result.get("confidence", 0.0)
                            asyncio.ensure_future(self.ws_manager.broadcast({
                                "type": "caption_user",
                                "text": result["text"],
                                "isFinal": False,
                            }))
                        elif result["type"] == "final":
                            text = result["text"] if result["text"].strip() else None
                            self.responder.stt_text = ""
                            # Record STT latency
                            stt_duration = (time.perf_counter() - _stt_start) * 1000
                            self.evo_logger.record("stt_latency", duration_ms=stt_duration, metadata={
                                "text_length": len(result["text"]),
                                "confidence": result.get("confidence", 0.0),
                                "silence_timeout": self.vad_silence_timeout,
                            })
                            if text:
                                asyncio.ensure_future(self.ws_manager.broadcast({
                                    "type": "caption_user",
                                    "text": text,
                                    "isFinal": True,
                                }))
                except Exception as e:
                    print(f"[Conversation·Pipeline] STT error: {e}")
                    text = None
                    self.responder.stt_text = ""
                    self.responder.stt_confidence = 0.0

                if not self._conversation_active:
                    break

                if text is None or not text.strip():
                    print("[Conversation·Pipeline] No speech — listening again...")
                    continue

                print(f"[Conversation·Pipeline] User: '{text}'")

                # ── 2. Check exit command ────────────────────────────
                if self._is_exit_command(text):
                    print("[Conversation·Pipeline] Exit command detected")
                    result = await self.responder.respond(
                        "Goodbye! Say the wake word when you need me again."
                    )
                    audio_path = result.get("audio_path", "")
                    if audio_path:
                        self.responder.is_speaking = True
                        try:
                            await self.interrupt_handler.play_with_interrupt(
                                str(audio_path), listen_for_interrupt=False,
                            )
                        finally:
                            self.responder.is_speaking = False
                    await self.stop_conversation()
                    return

                # ── 3. Check if it's a voice command (open/launch/run/etc.) ──
                if self._parse_command and self._execute_command:
                    parsed = await self._parse_command(text, False, None)
                    if parsed.get("action") != "unknown":
                        print(f"[Conversation·Pipeline] Voice command detected: {parsed['action']} → {parsed.get('target', parsed.get('command', ''))}")
                        # Execute the command and speak the result
                        confirmation = await self._execute_command(text, parsed)
                        self.responder.is_speaking = True
                        try:
                            pcm, sr = await self.responder.speech.synthesize_pcm(confirmation)
                            await self.interrupt_handler.play_pcm_with_interrupt(
                                pcm, sr, listen_for_interrupt=True,
                            )
                        except Exception as e:
                            print(f"[Conversation·Pipeline] Command feedback TTS error: {e}")
                        finally:
                            self.responder.is_speaking = False
                        continue

                # ── 4. Feed into pipeline (LLM → TTS) ───────────────
                interrupted = False
                try:
                    self.responder.is_speaking = True
                    self.responder.is_speaking_event.set()
                    self.responder._interrupt_requested = False

                    # Store user message in conversation history
                    self.responder.conversation.add_user_message(text)

                    # Build a fresh LLM → TTS pipeline for this turn
                    from voice.pipeline import build_conversation_pipeline

                    pipeline = build_conversation_pipeline(
                        self.responder, include_stt=False,
                    )

                    # Feed a single TranscriptionFrame into the pipeline
                    async def input_stream():
                        yield PipelineTranscriptionFrame(text=text)

                    async for frame in pipeline.run(input_stream()):
                        if isinstance(frame, PipelineTTSAudioFrame):
                            # Pause mic monitor during TTS playback
                            self.stt.stop_mic_monitor()

                            playback_interrupted = (
                                await self.interrupt_handler.play_pcm_with_interrupt(
                                    frame.pcm, frame.sample_rate,
                                    listen_for_interrupt=True,
                                )
                            )
                            if playback_interrupted:
                                interrupted = True
                                break

                    if interrupted:
                        print("[Conversation·Pipeline] Barge-in — restarting listen")
                        await asyncio.sleep(0.15)
                        continue

                except Exception as e:
                    print(f"[Conversation·Pipeline] Error: {e}")
                    await asyncio.sleep(0.5)
                    continue
                finally:
                    self.responder.is_speaking = False
                    self.responder.is_speaking_event.clear()
                    # Flush stale audio recorded during TTS playback
                    try:
                        await self.stt.flush_audio_buffer()
                    except Exception as flush_err:
                        print(f"[Conversation·Pipeline] Buffer flush warning: {flush_err}")

        except asyncio.CancelledError:
            print("[Conversation·Pipeline] Loop cancelled")
            raise
        except Exception as e:
            print(f"[Conversation·Pipeline] Loop error: {e}")
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
