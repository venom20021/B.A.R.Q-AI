"""
Conversation listener for continuous voice interaction.
After wake word detection, enters a hands-free conversation mode where BARQ
keeps listening, processes speech, and responds without requiring
the wake word to be said again for each turn.

This provides a Gemini/Alexa-like experience:
1. Wake word triggers conversation mode
2. Records with VAD (silence endpointing) — no need to press a button
3. Transcribes speech using Whisper
4. Generates AI response via Ollama
5. Plays TTS audio response
6. Automatically re-enters listening for follow-ups
7. "Goodbye" / silence timeout returns to wake-word-only standby
"""

import asyncio
import re
from pathlib import Path
from typing import Optional

from ai.responder import BARQResponder
from voice.speech import SpeechProcessor
from voice.interrupt_handler import InterruptHandler


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
        # Check exit command
        if self._is_exit_command(text):
            await self.stop_conversation()
            goodbye = await self.responder.respond("Goodbye!")
            return {"action": "exit", "text": goodbye["text"], "audio_path": goodbye.get("audio_path")}

        # Process through the responder
        result = await self.responder.respond(text)
        return {
            "action": "response",
            "text": result["text"],
            "audio_path": result.get("audio_path"),
        }

    async def _conversation_loop(self):
        """Main conversation loop: listen → transcribe → respond → speak → repeat."""
        try:
            while self._conversation_active:
                # 1. Listen with VAD (silence endpointing)
                print("[Conversation] Listening for speech...")
                text = await self.stt.transcribe_until_silence(
                    max_duration=15.0,
                    silence_timeout=1.8,
                    energy_threshold=300.0,
                )

                if not self._conversation_active:
                    break

                # 2. If no speech detected (silence timeout), exit
                if text is None or not text.strip():
                    print("[Conversation] No speech detected — ending conversation")
                    await self.stop_conversation()
                    return

                print(f"[Conversation] User: '{text}'")

                # 3. Check exit command
                if self._is_exit_command(text):
                    print("[Conversation] Exit command detected")
                    result = await self.responder.respond("Goodbye! Say the wake word when you need me again.")
                    await self.interrupt_handler.play_with_interrupt(
                        str(result.get("audio_path", "")),
                        listen_for_interrupt=False,
                    )
                    await self.stop_conversation()
                    return

                # 4. Process through BARQResponder (LLM + TTS)
                try:
                    result = await self.responder.respond(text)
                    response_text = result.get("text", "")
                    audio_path = result.get("audio_path", "")

                    print(f"[Conversation] BARQ: {response_text}")

                    # 5. Play response with interrupt detection
                    if audio_path and Path(audio_path).exists():
                        interrupted = await self.interrupt_handler.play_with_interrupt(
                            str(audio_path),
                            listen_for_interrupt=True,
                        )
                        if interrupted:
                            # User spoke over BARQ — record and process the interruption
                            print("[Conversation] Interrupted — listening for follow-up...")
                            continue
                except Exception as e:
                    print(f"[Conversation] Error processing response: {e}")
                    await asyncio.sleep(0.5)
                    continue

        except asyncio.CancelledError:
            print("[Conversation] Conversation loop cancelled")
            raise
        except Exception as e:
            print(f"[Conversation] Conversation loop error: {e}")
            self._conversation_active = False
            self.responder.conversation.end_session()

    def _is_exit_command(self, text: str) -> bool:
        """Check if user wants to end the conversation.
        Uses word-boundary matching to avoid accidental triggers (e.g. "stop" in "stop that song")."""
        text_lower = text.lower().strip()
        for phrase in self._exit_phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", text_lower):
                return True
        return False
