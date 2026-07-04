"""
BARQ Voice Control Module

Provides wake word detection (Vosk), speech-to-text (Whisper),
and text-to-speech (Edge TTS) capabilities.
"""

from .wake_word import WakeWordDetector
from .speech import SpeechProcessor

__all__ = ["WakeWordDetector", "SpeechProcessor"]
