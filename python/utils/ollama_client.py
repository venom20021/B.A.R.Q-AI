"""
LLM client for conversational AI responses — with automatic cloud fallback.

Primary client connects to a local Ollama instance. If Ollama is unavailable,
automatically falls back to an OpenAI-compatible cloud API so AI features
keep working even when the local LLM is offline.
"""

import json as _json
from typing import AsyncIterable

import socket

import httpx

from config import get_settings

# Name Ollama is expected to be installed at on Windows / Linux
_OLLAMA_INSTALL_URL = "https://ollama.com/download/windows"


# ═══════════════════════════════════════════════════════════════════════
#  Error classes
# ═══════════════════════════════════════════════════════════════════════


class OllamaNotAvailableError(ConnectionError):
    """Raised when Ollama is unreachable or the model is missing."""
    def __init__(self, host: str, model: str):
        self.ollama_host = host
        self.ollama_model = model
        self.reason = self._diagnose()
        super().__init__(self.reason)

    def _diagnose(self) -> str:
        """Try to give a helpful diagnostic message."""
        host = self.ollama_host
        model = self.ollama_model

        # Parse host:port from URL
        try:
            clean_host = host.replace("http://", "").replace("https://", "")
            hostname, port = clean_host.split(":")
            port = int(port)
        except (ValueError, AttributeError):
            hostname = host
            port = 11434

        # Check if the port is actually open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex((hostname, port))
            sock.close()
        except Exception:
            sock.close()
            result = -1

        if result != 0:
            return (
                f"Ollama is not running at {host}. "
                f"Install Ollama from https://ollama.com/download/windows, "
                f"then run: ollama serve  (or start Ollama from Start Menu)."
            )

        # Port is open — maybe model is missing
        return (
            f"Ollama is running at {host} but the model '{model}' was not found. "
            f"Pull it with: ollama pull {model}"
        )


class CloudLLMNotConfiguredError(ConnectionError):
    """Raised when cloud fallback is not configured."""
    def __init__(self):
        super().__init__(
            "Cloud LLM fallback is not configured. "
            "Set OPENAI_API_KEY in your .env file, or install Ollama locally."
        )


# ═══════════════════════════════════════════════════════════════════════
#  Cloud LLM fallback (OpenAI-compatible API)
# ═══════════════════════════════════════════════════════════════════════


class CloudLLMClient:
    """Client for OpenAI-compatible cloud LLM APIs.

    Works with OpenAI, OpenRouter, Groq, Together AI, and any other
    provider that implements the OpenAI chat completions format.

    Configure via .env:
        OPENAI_API_KEY=sk-...
        CLOUD_LLM_MODEL=gpt-4o-mini       (default)
        CLOUD_LLM_BASE_URL=https://api.openai.com/v1  (default)
    """

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.model = settings.cloud_llm_model
        self.base_url = settings.cloud_llm_base_url.rstrip("/")
        self._enabled = settings.cloud_llm_enabled and bool(self.api_key)

    @property
    def enabled(self) -> bool:
        """Whether the cloud fallback is configured and ready."""
        return self._enabled

    async def chat(self, messages: list[dict]) -> str:
        """Non-streaming chat completion via cloud API."""
        if not self._enabled:
            raise CloudLLMNotConfiguredError()

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "top_p": 0.9,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise CloudLLMNotConfiguredError() from e
            raise

    async def stream_chat(self, messages: list[dict]) -> AsyncIterable[str]:
        """Streaming chat completion via cloud API (SSE format)."""
        if not self._enabled:
            raise CloudLLMNotConfiguredError()

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "temperature": 0.7,
                        "top_p": 0.9,
                    },
                ) as response:
                    try:
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            # SSE format: "data: {...}"
                            if line.startswith("data: "):
                                payload = line[6:].strip()
                                if payload == "[DONE]":
                                    break
                                try:
                                    data = _json.loads(payload)
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    token = delta.get("content", "")
                                    if token:
                                        yield token
                                except (_json.JSONDecodeError, KeyError, IndexError):
                                    continue
                    except (httpx.ReadError, httpx.RemoteProtocolError, httpx.StreamError,
                             httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
                             TimeoutError, ConnectionResetError, ConnectionAbortedError) as mid_err:
                        error_msg = str(mid_err)[:120]
                        print(f"[CloudLLM] Mid-stream error: {error_msg}")
                        yield "\n\n[Sorry, the cloud AI engine encountered a stream error. Please try again.]"
                        try:
                            from voice.evolution_logger import get_evolution_logger
                            get_evolution_logger().record(
                                "llm_error",
                                metadata={"source": "cloud", "error": error_msg, "phase": "stream"},
                            )
                        except Exception:
                            pass
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise CloudLLMNotConfiguredError() from e
            raise
        except httpx.ConnectError:
            raise ConnectionError(
                f"Could not reach cloud LLM at {self.base_url}. "
                f"Check your internet connection and CLOUD_LLM_BASE_URL setting."
            )

    async def is_available(self) -> bool:
        """Check if the cloud LLM API is configured (no connectivity test)."""
        return self._enabled


# ═══════════════════════════════════════════════════════════════════════
#  Primary OllamaClient with automatic cloud fallback
# ═══════════════════════════════════════════════════════════════════════


class OllamaClient:
    """Client for Ollama's local LLM API with automatic cloud fallback.

    All methods try Ollama first. If Ollama is unreachable and a cloud
    API key is configured, they transparently fall back to the cloud LLM.
    If neither is available, an appropriate error is raised.
    """

    def __init__(self, host: str = "http://127.0.0.1:11434", model: str | None = None):
        self.host = host
        self.model = model or get_settings().ollama_model
        self._cloud = CloudLLMClient()
        self._fallback_reported = False  # only print fallback message once

    async def chat(self, messages: list[dict]) -> str:
        """Send a conversation to the LLM and get a response.

        Tries local Ollama first. Falls back to cloud LLM if configured.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Generated response text.

        Raises:
            OllamaNotAvailableError: If Ollama is down and no cloud fallback.
            CloudLLMNotConfiguredError: If both are unavailable.
        """
        try:
            return await self._ollama_chat(messages)
        except OllamaNotAvailableError:
            return await self._fallback_chat(messages)

    async def stream_chat(self, messages: list[dict]) -> AsyncIterable[str]:
        """Stream a conversation response token-by-token.

        Tries local Ollama first. Falls back to cloud LLM if configured.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Yields:
            Each text token as it arrives.

        Raises:
            OllamaNotAvailableError: If Ollama is down and no cloud fallback.
            CloudLLMNotConfiguredError: If both are unavailable.
        """
        try:
            async for token in self._ollama_stream_chat(messages):
                yield token
        except OllamaNotAvailableError:
            async for token in self._fallback_stream_chat(messages):
                yield token

    async def generate(self, prompt: str) -> str:
        """Simple single-prompt generation (no conversation history).

        Tries local Ollama first. Falls back to cloud LLM if configured.

        Args:
            prompt: The prompt text.

        Returns:
            Generated response text.
        """
        try:
            return await self._ollama_generate(prompt)
        except OllamaNotAvailableError:
            # Use chat method as generate for cloud (wrapped in user message)
            messages = [{"role": "user", "content": prompt}]
            return await self._fallback_chat(messages)

    async def is_available(self) -> bool:
        """Check if any LLM backend is available (Ollama or cloud)."""
        # Check Ollama first
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{self.host}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    if any(m["name"].startswith(self.model) for m in models):
                        return True
        except Exception:
            pass
        # Fallback: check cloud
        return self._cloud.is_available()

    # ── Internal: Ollama methods ─────────────────────────────────────

    async def _ollama_chat(self, messages: list[dict]) -> str:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.host}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": 0.7, "top_p": 0.9},
                    },
                )
                resp.raise_for_status()
                return resp.json()["message"]["content"]
        except httpx.ConnectError:
            raise OllamaNotAvailableError(self.host, self.model)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise OllamaNotAvailableError(self.host, self.model)
            raise

    async def _ollama_stream_chat(self, messages: list[dict]) -> AsyncIterable[str]:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{self.host}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "options": {"temperature": 0.7, "top_p": 0.9},
                    },
                ) as response:
                    try:
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                data = _json.loads(line)
                                if data.get("done"):
                                    break
                                token = data.get("message", {}).get("content", "")
                                if token:
                                    yield token
                            except (_json.JSONDecodeError, KeyError):
                                continue
                    except (httpx.ReadError, httpx.RemoteProtocolError, httpx.StreamError,
                             httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
                             TimeoutError, ConnectionResetError, ConnectionAbortedError) as mid_err:
                        error_msg = str(mid_err)[:120]
                        print(f"[Ollama] Mid-stream error in _ollama_stream_chat: {error_msg}")
                        # Yield a fallback error token so the caller doesn't hang with partial output
                        yield "\n\n[Sorry, the local AI engine encountered a stream error. Please try again.]"
                        # Log to evolution tracker
                        try:
                            from voice.evolution_logger import get_evolution_logger
                            get_evolution_logger().record(
                                "llm_error",
                                metadata={"source": "ollama", "error": error_msg, "phase": "stream"},
                            )
                        except Exception:
                            pass
        except httpx.ConnectError:
            raise OllamaNotAvailableError(self.host, self.model)

    async def _ollama_generate(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.host}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                return resp.json()["response"]
        except httpx.ConnectError:
            raise OllamaNotAvailableError(self.host, self.model)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise OllamaNotAvailableError(self.host, self.model)
            raise

    # ── Internal: Cloud fallback methods ────────────────────────────

    async def _report_fallback_once(self):
        if not self._fallback_reported:
            self._fallback_reported = True
            import logging
            logging.getLogger("barq").warning(
                "Ollama unavailable — using cloud LLM fallback (%s)", self._cloud.model
            )

    async def _fallback_chat(self, messages: list[dict]) -> str:
        if not self._cloud.enabled:
            raise CloudLLMNotConfiguredError()
        await self._report_fallback_once()
        return await self._cloud.chat(messages)

    async def _fallback_stream_chat(self, messages: list[dict]) -> AsyncIterable[str]:
        if not self._cloud.enabled:
            raise CloudLLMNotConfiguredError()
        await self._report_fallback_once()
        async for token in self._cloud.stream_chat(messages):
            yield token
