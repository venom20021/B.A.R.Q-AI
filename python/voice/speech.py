"""
Speech processing using Whisper for STT and Edge TTS for synthesis.
"""

import asyncio
import tempfile
import wave
from pathlib import Path
from typing import Any, AsyncIterable, Optional
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
        import sounddevice as sd
        import numpy as np

        # Resolve input device from config
        from .audio_device import resolve_input_device
        device = resolve_input_device(self.settings.audio_input_device)

        # Record audio
        data = sd.rec(
            int(16000 * duration),
            samplerate=16000,
            channels=1,
            dtype='int16',
            device=device,
            blocking=True,
        )

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(16000)
                wf.writeframes(data.tobytes())
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
        import sounddevice as sd
        import numpy as np

        from .audio_device import resolve_input_device
        device = resolve_input_device(self.settings.audio_input_device)

        stream = sd.InputStream(
            device=device,
            samplerate=16000,
            channels=1,
            dtype='int16',
            blocksize=1024,
        )
        stream.start()

        frames: list[np.ndarray] = []
        silence_chunks = 0
        silence_limit = int(silence_timeout * 16000 / 1024)
        max_chunks = int(max_duration * 16000 / 1024)
        has_speech = False

        for _ in range(max_chunks):
            data, overflowed = stream.read(1024)
            frames.append(data)

            try:
                rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))

                if rms < energy_threshold:
                    silence_chunks += 1
                else:
                    silence_chunks = 0
                    has_speech = True
            except Exception:
                pass

            if has_speech and silence_chunks >= silence_limit:
                if silence_chunks > 0:
                    frames = frames[:-silence_chunks]
                break

        stream.stop()
        stream.close()

        if not has_speech or not frames:
            return None

        audio_data = np.concatenate(frames) if len(frames) > 1 else frames[0]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data.tobytes())
            temp_path = f.name

        text = self.transcribe(temp_path)
        Path(temp_path).unlink(missing_ok=True)

        return text

    async def transcribe_streaming(
        self,
        max_duration: float = 15.0,
        silence_timeout: float = 0.4,
        energy_threshold: float = 300.0,
        interim_interval: float = 1.0,
    ) -> AsyncIterable[dict]:
        """Streaming transcription with overlapping-window interim results.

        Records from the microphone and yields partial transcripts as they
        become available — the caller does NOT need to wait for silence to
        begin processing.  Useful for live-caption-like UX or for feeding
        partial text into a streaming LLM pipeline.

        Each yielded dict has the shape:
            {"type": "interim", "text": "..."}
            {"type": "final",  "text": "..."}

        Args:
            max_duration: Maximum recording duration in seconds.
            silence_timeout: Seconds of silence before auto-stopping.
            energy_threshold: RMS energy threshold for silence detection.
            interim_interval: How often (seconds) to run Whisper on the
                              accumulated buffer for interim results.

        Yields:
            Interim dicts while the user is speaking, then one final dict.
            Yields nothing if no speech is detected.
        """
        import asyncio
        import sounddevice as sd
        import numpy as np

        from .audio_device import resolve_input_device
        device = resolve_input_device(self.settings.audio_input_device)

        stream = sd.InputStream(
            device=device,
            samplerate=16000,
            channels=1,
            dtype='int16',
            blocksize=1024,
        )
        stream.start()

        frames: list[np.ndarray] = []
        silence_chunks = 0
        silence_limit = int(silence_timeout * 16000 / 1024)
        max_chunks = int(max_duration * 16000 / 1024)
        interim_chunks = int(interim_interval * 16000 / 1024)
        has_speech = False
        last_interim_at = 0
        chunk_count = 0

        try:
            for _ in range(max_chunks):
                data, overflowed = stream.read(1024)
                frames.append(data)
                chunk_count += 1

                try:
                    rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                    if rms < energy_threshold:
                        silence_chunks += 1
                    else:
                        silence_chunks = 0
                        has_speech = True
                except Exception:
                    pass

                # Fire interim transcription at regular intervals once speech starts
                if (has_speech
                    and (chunk_count - last_interim_at) >= interim_chunks
                    and len(frames) > 1):
                    last_interim_at = chunk_count
                    result = await self._transcribe_frames(list(frames))
                    if result["text"]:
                        yield {"type": "interim", "text": result["text"], "confidence": result["confidence"]}

                # Check for end-of-speech (VAD silence timeout)
                if has_speech and silence_chunks >= silence_limit:
                    if silence_chunks > 0:
                        frames = frames[:-silence_chunks]
                    break

            # ── Final transcription ───────────────────────────────
            if has_speech and frames:
                result = await self._transcribe_frames(frames)
                if result["text"]:
                    yield {"type": "final", "text": result["text"], "confidence": result["confidence"]}
                else:
                    yield {"type": "final", "text": "", "confidence": 0.0}

        finally:
            stream.stop()
            stream.close()

    async def _transcribe_frames(self, frames: list) -> dict:
        """Helper: save audio frames to a temp WAV and return transcription + confidence.

        Returns a dict with:
            {"text": "...", "confidence": 0.0-1.0}

        Confidence is derived from Whisper's avg_logprob per segment.
        """
        import numpy as np

        audio_data = np.concatenate(frames) if len(frames) > 1 else frames[0]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data.tobytes())
            temp_path = f.name

        try:
            model = self._get_model()
            result = model.transcribe(str(temp_path), language="en")
            text = result["text"].strip()
            confidence = self._compute_confidence(result.get("segments", []))
            return {"text": text, "confidence": confidence}
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _compute_confidence(self, segments: list[dict]) -> float:
        """Compute a 0.0–1.0 confidence score from Whisper segments.

        Uses avg_logprob (converted via exp() to average token probability)
        and no_speech_prob as a penalty.  This gives a clean percentage-like
        score where higher is more confident.
        """
        if not segments:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for seg in segments:
            # avg_logprob is negative, exp() gives average token probability in [0, 1]
            token_prob = float(seg.get("avg_logprob", -5.0))
            token_prob = max(0.0, min(1.0, 2.71828 ** token_prob))  # clamp to [0,1]

            # no_speech_prob: higher → more likely not speech → penalise
            no_speech = float(seg.get("no_speech_prob", 0.0))

            # Duration available in (start, end) — use as weight
            duration = float(seg.get("end", 1.0)) - float(seg.get("start", 0.0))
            if duration <= 0:
                duration = 1.0

            score = token_prob * (1.0 - no_speech)
            weighted_sum += score * duration
            total_weight += duration

        if total_weight <= 0:
            return 0.0

        return round(min(1.0, weighted_sum / total_weight), 4)
