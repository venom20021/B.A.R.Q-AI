"""
BARQ Voice Control Module

Now powered by a pluggable voice agent (Deepgram or Pipecat).
Wake word detection (Vosk) remains for hands-free trigger.
"""

from .agent_base import VoiceAgentBase
from .deepgram_agent import DeepgramVoiceAgent
from .speech import SpeechProcessor
from .wake_word import (
    WakeWordDetector,
    get_sound_settings,
    play_command_accepted_sound,
    play_wake_sound,
    set_sound_enabled,
)

# Lazy-import Pipecat agent (only if dependencies are available)
try:
    from .pipecat_agent import PipecatVoiceAgent  # noqa: F401
except ImportError:
    pass

from .agent_factory import (
    get_voice_agent,
    get_voice_agent_async,
    get_available_backends,
    get_backend_from_db,
    reset_voice_agent,
)

__all__ = [
    "VoiceAgentBase", "DeepgramVoiceAgent",
    "WakeWordDetector", "SpeechProcessor",
    "get_sound_settings", "play_command_accepted_sound",
    "play_wake_sound", "set_sound_enabled",
    "get_voice_agent", "get_voice_agent_async",
    "get_available_backends", "get_backend_from_db",
    "reset_voice_agent",
]
