"""
BARQ Voice Control Module

Provides wake word detection (Vosk), speech-to-text (Whisper),
text-to-speech (Edge TTS), conversation listener, and interrupt handling.
Also exports the pipecat-inspired frame-based voice pipeline.
"""

from .wake_word import WakeWordDetector, play_wake_sound, play_command_accepted_sound, set_sound_enabled, get_sound_settings, HINDI_WAKE_PHRASES
from .speech import SpeechProcessor
from .interrupt_handler import InterruptHandler
from .pipeline import (VoicePipeline, build_conversation_pipeline,
                       STTProcessor, LLMProcessor, TTSProcessor,
                       AudioFrame, TTSAudioFrame, InterruptFrame,
                       TranscriptionFrame, LLMResponseFrame,
                       MicLevelFrame, StartFrame, EndFrame)

__all__ = [
    "WakeWordDetector", "SpeechProcessor", "InterruptHandler",
    "VoicePipeline", "build_conversation_pipeline",
    "STTProcessor", "LLMProcessor", "TTSProcessor",
    "AudioFrame", "TTSAudioFrame", "InterruptFrame",
    "TranscriptionFrame", "LLMResponseFrame",
    "MicLevelFrame", "StartFrame", "EndFrame",
]
