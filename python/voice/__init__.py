"""
BARQ Voice Control Module

Provides wake word detection (Vosk), speech-to-text (Whisper),
text-to-speech (Edge TTS), conversation listener, and interrupt handling.
"""

from .wake_word import WakeWordDetector, play_wake_sound, play_command_accepted_sound, set_sound_enabled, get_sound_settings, HINDI_WAKE_PHRASES
from .speech import SpeechProcessor
from .interrupt_handler import InterruptHandler

__all__ = ["WakeWordDetector", "SpeechProcessor", "InterruptHandler"]
