"""
Speech processing using Whisper for STT and Edge TTS for synthesis.
"""

import asyncio
import math
import struct
import tempfile
from pathlib import Path
from typing import Any, Optional
import edge_tts

from config import get_settings


class SpeechProcessor:
    """Handles speech-to-text and text-to-speech operations."""

    def __init__(self):
        self.settings = get_settings()
        self._whisper_model: Any = None
        self.tts_voice: str = "en-US-JennyNeural"

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

    async def transcribe_until_silence(
        self,
        max_duration: float = 15.0,
        silence_timeout: float = 1.5,
        energy_threshold: float = 300.0,
    ) -> Optional[str]:
        """Record from microphone with VAD (voice activity detection).
        Automatically stops when the user stops speaking (silence detected).
        This gives a natural Alexa/Gemini-like endpointing experience.

        Args:
            max_duration: Maximum recording duration in seconds.
            silence_timeout: Seconds of silence before auto-stopping.
            energy_threshold: RMS energy threshold for silence detection.

        Returns:
            Transcribed text, or None if no speech detected.
        """
        import pyaudio
        import wave

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024,
        )

        frames = []
        silence_chunks = 0
        silence_limit = int(silence_timeout * 16000 / 1024)
        max_chunks = int(max_duration * 16000 / 1024)
        has_speech = False

        for _ in range(max_chunks):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)

            # Compute RMS energy for VAD
            try:
                samples = struct.unpack_from("<" + "h" * (len(data) // 2), data)
                if samples:
                    sum_sq = sum(s * s for s in samples)
                    rms = math.sqrt(sum_sq / len(samples))

                    if rms < energy_threshold:
                        silence_chunks += 1
                    else:
                        silence_chunks = 0
                        has_speech = True
            except Exception:
                pass

            # If we detected speech and now silence has persisted — stop
            if has_speech and silence_chunks >= silence_limit:
                # Trim trailing silence frames
                if silence_chunks > 0:
                    frames = frames[:-silence_chunks]
                break

        stream.stop_stream()
        stream.close()
        p.terminate()

        if not has_speech or not frames:
            return None

        # Save to temp file and transcribe
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(16000)
                wf.writeframes(b"".join(frames))
            temp_path = f.name

        text = self.transcribe(temp_path)
        Path(temp_path).unlink(missing_ok=True)

        return text
