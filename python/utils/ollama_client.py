"""
Ollama LLM client for conversational AI responses.
Connects to a local Ollama instance to generate natural language replies.
"""

import httpx
from typing import Any, AsyncIterable

from config import get_settings


class OllamaClient:
    """Client for Ollama's local LLM API."""

    def __init__(self, host: str = "http://127.0.0.1:11434", model: str | None = None):
        self.host = host
        self.model = model or get_settings().ollama_model

    async def chat(self, messages: list[dict]) -> str:
        """Send a conversation to Ollama and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                      Should include system prompt, user messages, and assistant messages.

        Returns:
            Generated response text.
        """
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                    },
                },
            )
            data = resp.json()
            return data["message"]["content"]

    async def stream_chat(self, messages: list[dict]) -> AsyncIterable[str]:
        """Stream a conversation response token-by-token from Ollama.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Yields:
            Each text token as it arrives from Ollama's streaming API.
        """
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                    },
                },
            ) as response:
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        import json as _json
                        data = _json.loads(line)
                        if data.get("done"):
                            break
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                    except (_json.JSONDecodeError, KeyError):
                        continue

    async def generate(self, prompt: str) -> str:
        """Simple single-prompt generation (no conversation history).

        Args:
            prompt: The prompt text.

        Returns:
            Generated response text.
        """
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            data = resp.json()
            return data["response"]

    async def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{self.host}/api/tags")
                if resp.status_code != 200:
                    return False
                models = resp.json().get("models", [])
                return any(m["name"].startswith(self.model) for m in models)
        except Exception:
            return False
