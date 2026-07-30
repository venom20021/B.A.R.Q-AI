"""
Voice Agent Factory — creates the appropriate voice agent based on config.

The active backend is stored in the database (settings_dao) under
the key ``voice_agent_backend`` with values ``"deepgram"`` or ``"pipecat"``.
The default is ``"pipecat"`` (local, no API key needed).
"""

import os
from typing import Optional

from config import get_settings

# Module-level cache
_voice_agent_instance = None
_voice_agent_backend: Optional[str] = None


def get_available_backends() -> list[dict[str, str]]:
    """Return metadata about all available voice agent backends."""
    backends = [
        {
            "id": "deepgram",
            "name": "Deepgram Voice Agent",
            "description": "Cloud STT → Gemini LLM → TTS (managed WebSocket). Requires DEEPGRAM_API_KEY.",
            "requires_api_key": True,
            "api_key_configured": bool(get_settings().deepgram_api_key),
            "latency": "low (cloud)",
        },
    ]

    # Pipecat is available if dependencies are installed
    pipecat_available = False
    try:
        import pipecat  # noqa: F401
        pipecat_available = True
    except ImportError:
        pass
    try:
        import faster_whisper  # noqa: F401
        pipecat_available = True
    except ImportError:
        pass

    backends.append({
        "id": "pipecat",
        "name": "Pipecat (local)",
        "description": "Local Whisper STT → Ollama LLM → Piper/Kokoro TTS. No API key needed, uses GPU/CPU.",
        "requires_api_key": False,
        "api_key_configured": True,
        "latency": "medium (local model loading)",
        "available": pipecat_available,
    })

    return backends


async def get_backend_from_db() -> str:
    """Read the current voice agent backend from the database.

    Returns ``"pipecat"`` if not set or on error.
    """
    try:
        from database import settings_dao
        val = await settings_dao.get_setting("voice_agent_backend")
        if val in ("deepgram", "pipecat"):
            return val
    except Exception:
        pass
    # Fallback: check env var
    env_val = os.getenv("VOICE_AGENT_BACKEND", "pipecat")
    if env_val in ("deepgram", "pipecat"):
        return env_val
    return "pipecat"


def _create_agent(backend: str):
    """Create a new voice agent instance (no caching)."""
    settings = get_settings()

    if backend == "pipecat":
        from .pipecat_agent import PipecatVoiceAgent

        # Read TTS backend setting from DB (falls back to env var or "edge-tts")
        import os
        tts_backend = os.getenv("PIPECAT_TTS_BACKEND", "edge-tts")
        # Default voice depends on TTS backend: "af_heart" for kokoro, "en-US-AriaNeural" for edge-tts
        _default_voice = "af_heart" if tts_backend == "kokoro" else "en-US-AriaNeural"
        tts_voice = os.getenv("PIPECAT_TTS_VOICE", _default_voice)
        tts_speed = float(os.getenv("PIPECAT_TTS_SPEED", "1.0"))

        # Try to read from DB (best-effort)
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                from database import settings_dao
                db_backend = loop.run_until_complete(
                    settings_dao.get_setting("pipecat_tts_backend")
                )
                if db_backend in ("edge-tts", "kokoro"):
                    tts_backend = db_backend
                db_voice = loop.run_until_complete(
                    settings_dao.get_setting("pipecat_tts_voice")
                )
                if db_voice:
                    tts_voice = db_voice
                # If kokoro backend but voice doesn't look like a kokoro voice, use default
                if tts_backend == "kokoro" and (not tts_voice or len(tts_voice) < 3 or tts_voice[0] not in "abjzsfhipre"):
                    tts_voice = "af_heart"
                db_speed = loop.run_until_complete(
                    settings_dao.get_setting("pipecat_tts_speed")
                )
                if db_speed:
                    try:
                        tts_speed = float(db_speed)
                    except (ValueError, TypeError):
                        pass
            finally:
                loop.close()
        except Exception:
            pass

        return PipecatVoiceAgent(
            ollama_host=settings.ollama_host,
            ollama_model=settings.ollama_model,
            tts_backend=tts_backend,
            tts_voice=tts_voice,
            tts_speed=tts_speed,
        )

    # Default: Deepgram
    if not settings.deepgram_api_key:
        print("[AgentFactory] WARNING: DEEPGRAM_API_KEY not set — voice agent will fail to connect")
    from .deepgram_agent import DeepgramVoiceAgent
    return DeepgramVoiceAgent(api_key=settings.deepgram_api_key)


def get_voice_agent(backend: Optional[str] = None):
    """Get or create the voice agent singleton.

    Args:
        backend: Force a specific backend. If None, reads from DB/env.

    Returns:
        A VoiceAgentBase instance (DeepgramVoiceAgent or PipecatVoiceAgent).
    """
    global _voice_agent_instance, _voice_agent_backend

    # We need to resolve the backend asynchronously inside the factory
    # since get_backend_from_db() is async.  This synchronous version
    # uses the last-resolved backend or env var.
    import os
    resolved = backend or os.getenv("VOICE_AGENT_BACKEND", "pipecat")

    if _voice_agent_instance is not None and _voice_agent_backend == resolved:
        return _voice_agent_instance

    # Create new instance
    _voice_agent_instance = _create_agent(resolved)
    _voice_agent_backend = resolved
    print(f"[AgentFactory] Created voice agent: {resolved}")
    return _voice_agent_instance


async def get_voice_agent_async(backend: Optional[str] = None):
    """Async version: resolves backend from DB if not specified."""
    global _voice_agent_instance, _voice_agent_backend

    resolved = backend or await get_backend_from_db()

    if _voice_agent_instance is not None and _voice_agent_backend == resolved:
        return _voice_agent_instance

    _voice_agent_instance = _create_agent(resolved)
    _voice_agent_backend = resolved
    print(f"[AgentFactory] Created voice agent (async): {resolved}")
    return _voice_agent_instance


def reset_voice_agent():
    """Clear the cached agent instance.  Call before creating a new one
    with a different backend."""
    global _voice_agent_instance, _voice_agent_backend
    _voice_agent_instance = None
    _voice_agent_backend = None
