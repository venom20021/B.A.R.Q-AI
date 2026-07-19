"""
Async Ollama API client.

Sends prompts to the local Ollama instance and returns structured responses.
Used for element selection, Q&A generation, and form reasoning.
"""

import json
import logging
from typing import Any, Optional

import httpx

from ..config import CONFIG

logger = logging.getLogger("barq.auto_applier.ollama")


class OllamaError(Exception):
    """Raised when Ollama returns an error or times out."""
    pass


class OllamaClient:
    """Thin async wrapper around the Ollama generate API."""

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = (host or CONFIG.ollama_host).rstrip("/")
        self.model = model or CONFIG.ollama_model
        self._timeout = CONFIG.ollama_timeout

    # ── Public API ──────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        format_json: bool = False,
    ) -> str:
        """Send a prompt to Ollama and return the raw text response.

        Args:
            prompt: The user message / instruction.
            system: Optional system prompt for context.
            temperature: 0.0 = deterministic, 1.0 = creative.
            max_tokens: Maximum response length.
            format_json: If True, request JSON-formatted output.

        Returns:
            The model's text response.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system:
            payload["system"] = system

        if format_json:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self.host}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                text = data.get("response", "").strip()

                if not text:
                    raise OllamaError("Empty response from Ollama")

                logger.debug("Ollama response: %d chars (model=%s, temp=%.1f)",
                             len(text), self.model, temperature)
                return text

        except httpx.TimeoutException:
            raise OllamaError(
                f"Ollama request timed out after {self._timeout}s "
                f"(model={self.model}, host={self.host})"
            )
        except httpx.RequestError as exc:
            raise OllamaError(
                f"Ollama connection failed: {exc}. "
                f"Is Ollama running at {self.host}?"
            )

    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Send a prompt and parse the response as JSON."""
        text = await self.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            format_json=True,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Ollama returned non-JSON: %s...", text[:200])
            # Try to extract JSON from the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            raise OllamaError(f"Failed to parse JSON from Ollama response: {exc}")

    async def is_available(self) -> bool:
        """Check if the Ollama server is running."""
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self.host}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
