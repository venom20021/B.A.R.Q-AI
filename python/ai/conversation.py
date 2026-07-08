"""
Conversation memory and persona management for BARQ.
Maintains chat history, loads the BARQ personality, and formats context for Ollama.
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Default persona that defines BARQ's speaking style
DEFAULT_PERSONA = """You are BARQ, a voice-first AI desktop assistant.

SPEAKING STYLE:
- Speak naturally, like a knowledgeable friend — NOT like a robot.
- Keep responses short and snappy, 1-3 sentences for voice. No long paragraphs.
- Vary your phrasing. Don't use the same sentence structure every time.
- Use casual language: contractions (it's, don't, I'll), occasional filler words (well, so, actually), and warm tone.
- Sound human, not like a manual. No bullet points or lists unless asked.
- If the answer is obvious, just say it simply — no need to explain how you did it.
- Ask follow-up questions to keep the conversation flowing.
- When you don't know something, just say "I'm not sure" — don't over-apologize.

LANGUAGE:
- If the user speaks in Hindi, respond in Hindi (Hinglish is fine — mix of Hindi and English).
- If the user switches to English, you switch back to English naturally.
- Match the user's language and energy level.

CAPABILITIES:
You can help with: jobs, coding, system control, research, social media, web browsing, weather, stocks, and more."""


# ── Small talk handler ────────────────────────────────────────────────
# Quick canned responses for common phrases — avoids hitting the LLM
# for trivial greetings / thanks / goodbyes, saving latency and tokens.

SMALL_TALK: dict[str, list[str]] = {
    "how are you": [
        "I'm doing great, thanks for asking! How about you?",
        "Pretty good! Ready to help. What's on your mind?",
        "All good here! What can I do for you?",
    ],
    "what is your name": [
        "I'm BARQ, your voice assistant. Nice to meet you!",
        "Call me BARQ! What can I help with?",
        "BARQ here! What's up?",
    ],
    "thank you": [
        "Anytime! Let me know if you need anything else.",
        "You're welcome! Happy to help.",
        "No problem at all!",
    ],
    "goodbye": [
        "See you later! Take care.",
        "Bye! Come back anytime.",
        "Catch you later!",
    ],
    "good morning": [
        "Good morning! Hope you're having a great start to your day.",
        "Morning! What can I help you with today?",
    ],
    "good night": [
        "Good night! Sleep well.",
        "Night! Talk to you tomorrow.",
    ],
    "what can you do": [
        "I can help with jobs, coding, system control, research, social media, and more! Just ask.",
        "I'm your AI desktop assistant — I can help with almost anything. Try asking me to open an app, search for jobs, or check the weather!",
    ],
    "i love you": [
        "Aw, thanks! I'm here to help, always.",
        "That's sweet of you to say! Let me know what you need.",
    ],
    "nothing": [
        "Okay! I'll be here if you need me. Just say 'computer' when you're ready.",
        "Got it! Going to standby. Say the wake word when you need me.",
        "Alright, signing off. Call my name when you want me back.",
    ],
}


def get_small_talk(text: str) -> str | None:
    """Check if the input matches a common small talk pattern.

    Returns a canned response string, or None if no pattern matched
    (in which case the caller should route to the LLM).
    """
    text_lower = text.lower().strip()
    for phrase, responses in SMALL_TALK.items():
        if phrase in text_lower:
            return random.choice(responses)
    return None


class ConversationManager:
    """Manages conversation history, persona, and context for Ollama."""

    def __init__(self, max_history: int = 20):
        self.history: list[dict] = []
        self.max_history = max_history
        self.persona = DEFAULT_PERSONA
        self._active = False
        self._session_id: Optional[str] = None

    def start_session(self, topic: Optional[str] = None) -> str:
        """Start a new conversation session.

        Returns:
            Session ID string.
        """
        import time
        self._session_id = f"conv_{int(time.time())}"
        self._active = True
        if topic:
            self.add_system_message(f"Conversation topic: {topic}")
        return self._session_id

    def end_session(self):
        """End the current conversation session."""
        self._active = False
        self._session_id = None

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def turn_count(self) -> int:
        """Number of user-assistant exchange pairs."""
        user_msgs = sum(1 for m in self.history if m["role"] == "user")
        return user_msgs

    def set_persona(self, persona_text: str):
        """Override the default persona."""
        self.persona = persona_text

    def add_system_message(self, content: str):
        """Add a system-level instruction message."""
        self.history.append({
            "role": "system",
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def add_user_message(self, text: str):
        """Store what the user said."""
        self.history.append({
            "role": "user",
            "content": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._trim_history()

    def add_assistant_message(self, text: str):
        """Store what BARQ said."""
        self.history.append({
            "role": "assistant",
            "content": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._trim_history()

    def _trim_history(self):
        """Keep history within max_history by removing oldest non-system messages."""
        if len(self.history) <= self.max_history:
            return
        # Count system messages, which we want to preserve
        system_count = sum(1 for m in self.history if m["role"] == "system")
        # Remove oldest user/assistant messages until under limit
        while len(self.history) > self.max_history:
            for i, msg in enumerate(self.history):
                if msg["role"] != "system":
                    self.history.pop(i)
                    break

    def get_context(self) -> list[dict]:
        """Return formatted history for Ollama, with persona as system prompt.

        Returns:
            List of message dicts compatible with Ollama's /api/chat endpoint.
        """
        messages = [{"role": "system", "content": self.persona}]
        for msg in self.history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        return messages

    def get_recent_history(self, count: int = 5) -> list[dict]:
        """Get the most recent messages (excluding system)."""
        non_system = [m for m in self.history if m["role"] != "system"]
        return non_system[-count:]

    def clear(self):
        """Start fresh conversation, preserving persona."""
        self.history = []
        self._active = False
        self._session_id = None

    def save(self, path: str):
        """Persist conversation history to disk."""
        Path(path).write_text(json.dumps(self.history, indent=2))

    def load(self, path: str):
        """Load previous conversation history from disk."""
        if Path(path).exists():
            self.history = json.loads(Path(path).read_text())
            if self.history:
                self._active = True
