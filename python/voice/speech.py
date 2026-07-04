"""
Speech processing using Whisper for STT and Edge TTS for synthesis.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any
import edge_tts

from config import get_settings


class SpeechProcessor:
    """Handles speech-to-text and text-to-speech operations."""

    def __init__(self):
        self.settings = get_settings()
        self._whisper_model: Any = None

    def _get_model(self):
        """Lazy-load the Whisper model."""
        if self._whisper_model is None:
            import whisper
            print(f"[Speech] Loading Whisper model '{self.settings.whisper_model}'...")
            self._whisper_model = whisper.load_model(self.settings.whisper_model)
            print("[Speech] Whisper model loaded")
        return self._whisper_model

    def transcribe(self, audio_path: str | Path) -> str:
        """
        Transcribe an audio file to text using Whisper.

        Args:
            audio_path: Path to the audio file (WAV/MP3/OGG)

        Returns:
            Transcribed text
        """
        model = self._get_model()
        result = model.transcribe(str(audio_path), language="en")
        return result["text"].strip()

    async def synthesize(self, text: str, voice: str = "en-US-JennyNeural") -> bytes:
        """
        Convert text to speech using Edge TTS.

        Args:
            text: The text to speak
            voice: Edge TTS voice name

        Returns:
            Audio bytes (MP3 format)
        """
        communicate = edge_tts.Communicate(text, voice)
        audio_bytes = b""

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]

        return audio_bytes

    async def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        """
        Convert text to speech and save to file.

        Args:
            text: The text to speak
            output_path: Path to save the audio file

        Returns:
            Path to the saved audio file
        """
        audio_bytes = await self.synthesize(text)

        output_path = Path(output_path)
        output_path.write_bytes(audio_bytes)

        return output_path

    async def transcribe_microphone(self, duration: float = 5.0) -> str:
        """
        Record from microphone and transcribe.

        Args:
            duration: Recording duration in seconds

        Returns:
            Transcribed text
        """
        import pyaudio
        import wave

        # Record audio
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024,
        )

        frames = []
        for _ in range(0, int(16000 / 1024 * duration)):
            data = stream.read(1024)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(16000)
                wf.writeframes(b"".join(frames))
            temp_path = f.name

        # Transcribe
        text = self.transcribe(temp_path)
        Path(temp_path).unlink(missing_ok=True)

        return text
