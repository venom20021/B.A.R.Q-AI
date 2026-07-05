"""
Conversation memory and persona management for BARQ.
Maintains chat history, loads the BARQ personality, and formats context for Ollama.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Default persona that defines BARQ's speaking style
DEFAULT_PERSONA = """You are BARQ, a voice-first AI desktop assistant.
You speak naturally, like a knowledgeable friend, not a robot.
Keep responses conversational and concise (2-4 sentences max for voice).
Be direct. Use casual but professional tone.
You can help with: jobs, coding, system control, research, social media, web browsing.
When unsure, say so honestly rather than guessing.
If the user speaks in Hindi, you may respond in Hindi.
If the user switches to English, you switch back to English."""


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
