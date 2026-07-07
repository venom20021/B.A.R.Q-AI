"""
BARQ Responder - generates both text and audio responses.
Uses ConversationManager for context and Ollama for LLM responses.

Supports streaming: LLM tokens are emitted incrementally, split at sentence
boundaries, and each sentence is immediately sent to TTS so audio playback
can begin while the LLM continues generating the rest of the response.
"""

import hashlib
import re
from pathlib import Path
from typing import AsyncIterable, Optional

import edge_tts

from ai.conversation import ConversationManager
from utils.ollama_client import OllamaClient
from voice.speech import SpeechProcessor

# Audio output directory
AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _split_sentences(text: str) -> list[str]:
    """Split text at sentence/natural-pause boundaries.
    Returns complete chunks that are at least a few words long;
    the caller should keep the last element as a running buffer
    if it does not end with terminal punctuation.
    Splits on . ! ? : ; and commas so that smaller chunks
    can be sent to TTS faster while the LLM keeps generating.
    """
    parts = re.split(r'(?<=[.!?:;,])\s+', text)
    return [p.strip() for p in parts if p.strip()]


class BARQResponder:
    """Handles user input and returns both text + audio response."""

    def __init__(self):
        self.conversation = ConversationManager()
        self.llm = OllamaClient()
        self.speech = SpeechProcessor()
        self.tts_voice: str = "en-US-GuyNeural"
        self.is_speaking = False
        self.is_processing = False
        self._interrupt_requested = False  # set True to abort an active stream
        self.stt_text: str = ""  # latest interim STT transcript (for live display via WebSocket)
        self.stt_confidence: float = 0.0  # confidence score of current/interim STT (0.0-1.0)

    # ── Non-streaming (legacy) respond ───────────────────────────────

    async def respond(self, user_input: str, confidence: float = 0.0) -> dict:
        """Process user input and return text + audio response.

        Args:
            user_input: The transcribed text from the user.
            confidence: Confidence score of the transcription (0.0-1.0).

        Returns:
            Dict with keys: text, audio_path, action
        """
        self.is_processing = True
        try:
            self.conversation.add_user_message(user_input)
            intent = self._classify_intent(user_input)

            if intent == "command":
                response_text = await self._handle_command(user_input)
            else:
                context = self.conversation.get_context()
                try:
                    response_text = await self.llm.chat(context)
                except Exception as e:
                    response_text = f"Sorry, I couldn't reach the language model. {e}"

            self.conversation.add_assistant_message(response_text)
            audio_path = await self._text_to_speech(response_text)

            return {
                "text": response_text,
                "audio_path": str(audio_path),
                "action": intent,
            }
        finally:
            self.is_processing = False

    # ── Streaming respond ───────────────────────────────────────────

    async def stream_respond(self, user_input: str, confidence: float = 0.0) -> AsyncIterable[dict]:
        """Stream-process user input: LLM tokens → sentence-aware TTS chunks.

        Each yielded dict has the shape:
            {"text": "<sentence>", "audio_path": "<path-to-mp3>"}

        The caller should play each audio chunk immediately.  If
        ``self._interrupt_requested`` is set to True while iterating,
        the remaining stream is abandoned cleanly.

        Args:
            user_input: The transcribed text from the user.
            confidence: Confidence score of the transcription (0.0-1.0).
        """
        self.is_processing = True
        self._interrupt_requested = False
        try:
            # ── 1. Store user message & classify ─────────────────────
            self.conversation.add_user_message(user_input)
            intent = self._classify_intent(user_input)

            # Commands are short — use non-streaming path
            if intent == "command":
                result = await self.respond(user_input)
                yield result
                return

            # ── 2. Streaming LLM ────────────────────────────────────
            context = self.conversation.get_context()
            buffer = ""
            full_text = ""

            try:
                async for token in self.llm.stream_chat(context):
                    if self._interrupt_requested:
                        break
                    buffer += token
                    full_text += token

                    # Flush complete sentences from the buffer
                    parts = _split_sentences(buffer)
                    if len(parts) > 1:
                        # All parts except the last are guaranteed complete
                        complete = parts[:-1]
                        buffer = parts[-1]  # keep the potentially-incomplete tail
                        for sentence in complete:
                            if sentence.strip():
                                audio_path = await self._text_to_speech(sentence)
                                yield {"text": sentence, "audio_path": str(audio_path)}
            except Exception as e:
                print(f"[Responder] LLM streaming error: {e}")
                # If we got partial text, use it as-is
                if not full_text.strip():
                    full_text = f"Sorry, I encountered an error. {e}"
                    yield {"text": full_text, "audio_path": str(await self._text_to_speech(full_text))}
                    return

            # ── 3. Flush remaining buffer ───────────────────────────
            if buffer.strip() and not self._interrupt_requested:
                audio_path = await self._text_to_speech(buffer)
                yield {"text": buffer, "audio_path": str(audio_path)}

            # ── 4. Store complete response in history ───────────────
            if full_text.strip():
                self.conversation.add_assistant_message(full_text)

        finally:
            self.is_processing = False
            self._interrupt_requested = False

    # ── Intent classification ────────────────────────────────────────

    def _classify_intent(self, text: str) -> str:
        """Determine if user wants a command executed or just chatting."""
        command_keywords = [
            "open", "close", "run", "scan", "create", "delete",
            "search", "find", "show", "set", "change", "toggle",
            "minimize", "maximize", "launch", "start", "stop",
            "shut up", "silence",
        ]
        text_lower = text.lower().strip()
        for kw in command_keywords:
            if text_lower.startswith(kw):
                return "command"
        return "conversation"

    # ── Command handler ──────────────────────────────────────────────

    async def _handle_command(self, text: str) -> str:
        """Route a command and return a human-readable result."""
        exit_phrases = ["goodbye", "bye", "exit", "end conversation",
                        "that's all", "we're done"]
        if any(p in text.lower() for p in exit_phrases):
            self.conversation.end_session()
            return "Goodbye! Say 'computer' when you need me again."

        try:
            from voice.routes import _parse_and_route
            result = await _parse_and_route(text, is_follow_up=False, last_intent=None)
            action = result.get("action", "unknown")

            if action == "run_command_confirm":
                cmd = result.get("command", "")
                tier = result.get("tier", "warn")
                desc = result.get("tier_description", "")
                tier_upper = "DANGEROUS" if tier == "dangerous" else "MODERATE RISK"
                return (
                    f"The command {cmd} is flagged as {tier_upper}. "
                    f"{desc} "
                    f"Say 'yes' to confirm or 'cancel' to abort."
                )

            if action == "run_command_execute":
                return result.get("message", "Command approved and executed.")

            if action == "cancel":
                return "Command cancelled."

            if action == "unknown":
                context = self.conversation.get_context()
                try:
                    return await self.llm.chat(context)
                except Exception:
                    return "Sorry, I didn't understand that command."

            action_text = action.replace("_", " ")
            target = result.get("target", "") or result.get("query", "")
            if target:
                return f"Okay, I'll {action_text} {target}."
            return f"Okay, {action_text}."
        except Exception as e:
            return f"I heard: '{text}' but couldn't process it. {e}"

    # ── TTS helpers ─────────────────────────────────────────────────

    async def _text_to_speech(self, text: str) -> Path:
        """Convert text to speech using edge-tts."""
        content_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        output_path = AUDIO_DIR / f"response_{content_hash}.mp3"

        if not output_path.exists():
            communicate = edge_tts.Communicate(text, self.tts_voice)
            await communicate.save(str(output_path))

        return output_path

    async def respond_text_only(self, user_input: str) -> str:
        """Quick text-only response (no audio generation)."""
        self.conversation.add_user_message(user_input)
        context = self.conversation.get_context()
        try:
            response_text = await self.llm.chat(context)
        except Exception as e:
            response_text = f"Error: {e}"
        self.conversation.add_assistant_message(response_text)
        return response_text
