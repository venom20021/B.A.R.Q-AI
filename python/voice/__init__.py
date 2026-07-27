"""
BARQ Voice Control Module

Now powered by the Deepgram Voice Agent (managed STT → LLM → TTS pipeline).
Wake word detection (Vosk) remains for hands-free trigger.
"""

from .deepgram_agent import DeepgramVoiceAgent
from .speech import SpeechProcessor
from .wake_word import (
    WakeWordDetector,
    get_sound_settings,
    play_command_accepted_sound,
    play_wake_sound,
    set_sound_enabled,
)

__all__ = [
    "WakeWordDetector", "SpeechProcessor", "DeepgramVoiceAgent",
    "get_sound_settings", "play_command_accepted_sound",
    "play_wake_sound", "set_sound_enabled",
]
