"""
BARQ Voice Control Module

Provides wake word detection (Vosk), speech-to-text (Whisper),
text-to-speech (Edge TTS), conversation listener, and interrupt handling.
Also exports the pipecat-inspired frame-based voice pipeline.
"""

from .interrupt_handler import InterruptHandler
from .pipeline import (
                       AudioFrame,
                       EndFrame,
                       InterruptFrame,
                       LLMProcessor,
                       LLMResponseFrame,
                       MicLevelFrame,
                       StartFrame,
                       STTProcessor,
                       TranscriptionFrame,
                       TTSAudioFrame,
                       TTSProcessor,
                       VoicePipeline,
                       build_conversation_pipeline,
)
from .speech import SpeechProcessor
from .wake_word import (
    WakeWordDetector,
    get_sound_settings,
    play_command_accepted_sound,
    play_wake_sound,
    set_sound_enabled,
)

__all__ = [
    "WakeWordDetector", "SpeechProcessor", "InterruptHandler",
    "VoicePipeline", "build_conversation_pipeline",
    "STTProcessor", "LLMProcessor", "TTSProcessor",
    "AudioFrame", "TTSAudioFrame", "InterruptFrame",
    "TranscriptionFrame", "LLMResponseFrame",
    "MicLevelFrame", "StartFrame", "EndFrame",
    "get_sound_settings", "play_command_accepted_sound",
    "play_wake_sound", "set_sound_enabled",
]
