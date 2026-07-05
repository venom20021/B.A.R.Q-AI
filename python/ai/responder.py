"""
BARQ Responder - generates both text and audio responses.
Uses ConversationManager for context and Ollama for LLM responses."""

import asyncio
import json
import hashlib
import os
from pathlib import Path
from typing import Optional

import edge_tts

from ai.conversation import ConversationManager
from utils.ollama_client import OllamaClient
from voice.speech import SpeechProcessor

# Audio output directory
AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


class BARQResponder:
    """Handles user input and returns both text + audio response."""

    def __init__(self):
        self.conversation = ConversationManager()
        self.llm = OllamaClient()
        self.speech = SpeechProcessor()
        self.tts_voice: str = "en-US-GuyNeural"
        self.is_speaking = False

    async def respond(self, user_input: str, confidence: float = 0.0) -> dict:
        """Process user input and return text + audio response.

        Args:
            user_input: The transcribed text from the user.
            confidence: Confidence score of the transcription (0.0-1.0).

        Returns:
            Dict with keys: text, audio_path, action
        """
        # 1. Store user message
        self.conversation.add_user_message(user_input)

        # 2. Classify intent
        intent = self._classify_intent(user_input)

        if intent == "command":
            response_text = await self._handle_command(user_input)
        else:
            # Natural conversation — generate response via Ollama
            context = self.conversation.get_context()
            try:
                response_text = await self.llm.chat(context)
            except Exception as e:
                response_text = f"Sorry, I couldn't reach the language model. {e}"

        # 3. Store BARQ's response
        self.conversation.add_assistant_message(response_text)

        # 4. Generate speech audio
        audio_path = await self._text_to_speech(response_text)

        return {
            "text": response_text,
            "audio_path": str(audio_path),
            "action": intent,
        }

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

    async def _handle_command(self, text: str) -> str:
        """Route a command and return a human-readable result."""
        # Check exit/conversation-end commands
        exit_phrases = ["goodbye", "bye", "exit", "end conversation", "that's all", "we're done"]
        if any(p in text.lower() for p in exit_phrases):
            self.conversation.end_session()
            return "Goodbye! Say 'Hey BARQ' when you need me again."

        # Route through the existing command parser from voice.routes
        try:
            from voice.routes import _parse_and_route
            result = await _parse_and_route(text, is_follow_up=False, last_intent=None)
            if result.get("action") == "unknown":
                # Unknown command — fall back to LLM conversation
                context = self.conversation.get_context()
                try:
                    return await self.llm.chat(context)
                except Exception:
                    return f"Sorry, I didn't understand that command."
            action = result.get("action", "unknown").replace("_", " ")
            target = result.get("target", "") or result.get("query", "")
            if target:
                return f"Okay, I'll {action} {target}."
            return f"Okay, {action}."
        except Exception as e:
            return f"I heard: '{text}' but couldn't process it. {e}"

    async def _text_to_speech(self, text: str) -> Path:
        """Convert text to speech using edge-tts."""
        content_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        output_path = AUDIO_DIR / f"response_{content_hash}.mp3"

        # Only generate if not already cached
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
