"""
Speech processing using faster-whisper for STT and Edge TTS / Piper TTS for synthesis.

Supports two TTS backends:
- "edge" (default): Microsoft Edge TTS — requires internet, high-quality natural voices
- "piper": Local Piper TTS — fully offline, uses ONNX models (en_US-lessac-medium by default)

The TTS backend can be switched at runtime via the /voice/tts-backend API.
"""

import asyncio
import io
import json
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any, AsyncIterable, Optional

import edge_tts
import numpy as np

from config import get_settings
from utils.callback_guards import SyncCallback

# ── Piper TTS Engine (offline, local) ──────────────────────────────────


class PiperTTSEngine:
    """Wrapper around Piper TTS for fully offline speech synthesis.

    Uses ONNX voice models (e.g. en_US-lessac-medium) downloaded to a local
    directory.  The model is loaded lazily on first use and cached.
    """

    DEFAULT_MODEL = "en_US-lessac-medium"
    MODELS_DIR = Path(__file__).parent.parent / "models" / "piper"

    def __init__(self, model_name: str = ""):
        self._voice: Any = None  # PiperVoice instance (lazy-loaded)
        self._model_name: str = model_name or self.DEFAULT_MODEL
        self._model_path: Path = self.MODELS_DIR / f"{self._model_name}.onnx"
        self._config_path: Path = self.MODELS_DIR / f"{self._model_name}.onnx.json"
        self._sample_rate: int = 22050  # default, updated on load
        self._load_lock = threading.Lock()  # thread safety for lazy loading

    @property
    def is_available(self) -> bool:
        """Check if the Piper voice model file exists on disk."""
        return self._model_path.exists() and self._config_path.exists()

    @property
    def model_name(self) -> str:
        return self._model_name

    @model_name.setter
    def model_name(self, name: str):
        """Switch to a different Piper voice model (lazy-loaded on next use)."""
        self._voice = None  # force re-load
        self._model_name = name
        self._model_path = self.MODELS_DIR / f"{name}.onnx"
        self._config_path = self.MODELS_DIR / f"{name}.onnx.json"

    def _load_voice(self):
        """Lazy-load the PiperVoice model (thread-safe with double-checked locking)."""
        if self._voice is not None:
            return
        with self._load_lock:
            if self._voice is not None:
                return
            if not self.is_available:
                raise RuntimeError(
                    f"Piper voice model not found at {self._model_path}. "
                    f"Download with: python -m piper.download_voices {self._model_name} "
                    f"--download-dir {self.MODELS_DIR}"
                )

            from piper.voice import PiperVoice
            print(f"[Piper] Loading voice model: {self._model_name}")
            self._voice = PiperVoice.load(
                str(self._model_path),
                config_path=str(self._config_path),
                use_cuda=False,
            )
            # Read sample rate from the onnx config json
            config_data = json.loads(self._config_path.read_text(encoding="utf-8"))
            self._sample_rate = config_data.get("audio", {}).get("sample_rate", 22050)
            print(f"[Piper] Voice model loaded (sample_rate={self._sample_rate})")

    def synthesize(self, text: str) -> bytes:
        """Convert text to speech and return WAV bytes.

        Args:
            text: The text to speak

        Returns:
            WAV bytes (16-bit PCM with proper WAV header)
        """
        self._load_voice()

        pcm_chunks: list[bytes] = []
        for chunk in self._voice.synthesize(text):
            pcm_chunks.append(chunk.audio_int16_bytes)

        if not pcm_chunks:
            raise ValueError("Piper TTS produced no audio output")

        full_pcm = b"".join(pcm_chunks)

        # Wrap in WAV header
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self._sample_rate)
            wf.writeframes(full_pcm)

        return buf.getvalue()

    def synthesize_pcm(self, text: str) -> tuple[np.ndarray, int]:
        """Convert text to speech and return PCM float32 audio.

        Args:
            text: The text to speak

        Returns:
            Tuple of (audio_float32 normalized to [-1.0, 1.0], sample_rate)
        """
        self._load_voice()

        float_chunks: list[np.ndarray] = []
        for chunk in self._voice.synthesize(text):
            float_chunks.append(chunk.audio_float_array)

        if not float_chunks:
            raise ValueError("Piper TTS produced no audio output")

        audio = np.concatenate(float_chunks)
        return audio.astype(np.float32), self._sample_rate

    def list_available_models(self) -> list[dict]:
        """List all downloaded Piper voice models in the models/piper directory."""
        if not self.MODELS_DIR.exists():
            return []
        models = []
        for f in self.MODELS_DIR.glob("*.onnx"):
            stem = f.stem  # e.g. "en_US-lessac-medium"
            json_path = self.MODELS_DIR / f"{stem}.onnx.json"
            if json_path.exists():
                models.append({
                    "id": stem,
                    "path": str(f),
                })
        return models


class SpeechProcessor:
    """Handles speech-to-text and text-to-speech operations.

    Supports two TTS backends:
    - "edge" (default): Microsoft Edge TTS — natural voices, requires internet
    - "piper": Local Piper TTS — fully offline, uses local ONNX models

    .. note::

        ``on_language_detected`` is called synchronously during transcription.
        It **must** be a regular (non-async) function — passing an ``async def``
        will raise ``TypeError`` at assignment.
    """

    # Sync-only callback slots — assigning an async function raises TypeError
    on_language_detected = SyncCallback()

    def __init__(self):
        self.settings = get_settings()
        self._whisper_model: Any = None
        self.tts_voice: str = "en-US-JennyNeural"
        # TTS backend: "edge" or "piper"
        self.tts_backend: str = "edge"
        # Lazy-loaded Piper engine (created on-demand when switching to piper backend)
        self._piper_engine: Optional[PiperTTSEngine] = None
        # STT language: "en" or "hi" — defaults to English, auto-detected from speech
        self.stt_language: str = "en"
        self.on_language_detected = None  # Initialise as None (valid for SyncCallback)
        # Live mic level tracking — updated by transcribe_streaming() every chunk
        # and by the background mic monitor between turns, so the sphere always
        # shows audio reactivity even when STT is idle.
        self._current_mic_level: float = 0.0
        # Background mic monitor (persistent, between STT turns)
        self._mic_monitor_running: bool = False
        self._mic_monitor_thread: Optional[threading.Thread] = None

    def get_mic_level(self) -> float:
        """Get the current microphone audio level (0.0–1.0).

        Returns the live RMS-based mic level, updated continuously by:
        - The background mic monitor (between STT turns, during conversations)
        - ``transcribe_streaming()`` (during active STT)

        Returns 0.0 when no mic stream is open (e.g. before first conversation).
        """
        return self._current_mic_level

    # ── Audio Buffer Flush ──────────────────────────────────────────────

    async def flush_audio_buffer(self, duration: float = 0.15) -> None:
        """Flush/discard stale audio from the input buffer.

        Opens a temporary ``sounddevice.InputStream``, reads and discards
        audio frames for *duration* seconds, then closes it.  This clears
        any residual audio that was captured during TTS playback, preventing
        the echo feedback spiral where BARQ hears its own voice.

        Call this AFTER TTS finishes and BEFORE the next listen cycle.

        Args:
            duration: How many seconds of audio to discard (default 0.15).
                      Should be enough to clear the OS audio buffer.
        """
        import numpy as np
        import sounddevice as sd

        from .audio_device import resolve_input_device

        try:
            device = resolve_input_device(self.settings.audio_input_device)

            # Open a throwaway stream, read frames and discard them
            chunk_count = int(duration * 16000 / 1024)
            stream = sd.InputStream(
                device=device,
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=1024,
            )
            stream.start()
            for _ in range(chunk_count):
                stream.read(1024)
            stream.stop()
            stream.close()
            print(f"[Speech] Flushed {chunk_count} audio chunks from input buffer")
        except Exception as e:
            # Non-fatal — buffer flush is a best-effort operation
            if "No default input device" not in str(e):
                print(f"[Speech] Buffer flush skipped: {e}")

    # ── Background Mic Level Monitor ────────────────────────────────
    # A lightweight background thread that continuously reads the microphone
    # RMS level when no STT stream is active.  This keeps the WebSocket mic_level
    # alive so the 3D sphere shows audio wave reactivity even between turns.
    #
    # Lifecycle:
    #   - Started by ConversationListener when conversation mode begins
    #   - Stopped by transcribe_streaming() before opening its own stream
    #   - Restarted by transcribe_streaming() after releasing its stream
    #   - Stopped by ConversationListener when conversation mode ends

    def start_mic_monitor(self):
        """Start the background mic level monitor thread.

        Opens its own lightweight InputStream (blocksize=1024, no processing)
        and updates ``_current_mic_level`` on every chunk.  Call when
        conversation mode starts (between turns) to keep the sphere alive.
        """
        if self._mic_monitor_running:
            return
        self._mic_monitor_running = True
        self._mic_monitor_thread = threading.Thread(
            target=self._mic_monitor_loop, daemon=True,
        )
        self._mic_monitor_thread.start()
        print("[Speech] Background mic monitor started")

    def stop_mic_monitor(self):
        """Stop the background mic level monitor thread.

        The thread's stream is closed and the thread joins (up to 1 s).
        Call before ``transcribe_streaming()`` opens its own stream, and
        when conversation mode ends.
        """
        self._mic_monitor_running = False
        if self._mic_monitor_thread and self._mic_monitor_thread.is_alive():
            self._mic_monitor_thread.join(timeout=1)
            self._mic_monitor_thread = None
        print("[Speech] Background mic monitor stopped")

    def _mic_monitor_loop(self):
        """Background loop: lightweight mic stream for RMS level reading only.

        Opens a separate ``sd.InputStream`` with minimal blocksize, reads
        each chunk, computes RMS, and updates ``_current_mic_level``.
        If the stream fails (e.g. device disconnected) it retries every 500 ms.

        When ``is_speaking_event`` is set (BARQ is playing TTS audio), incoming
        audio frames are still read (to drain the buffer) but their RMS level
        is NOT updated — effectively ignoring audio captured during TTS playback
        to prevent echo feedback (the "mute switch" requirement).
        """
        import numpy as np
        import sounddevice as sd

        from .audio_device import resolve_input_device

        device = resolve_input_device(self.settings.audio_input_device)

        # Import the module-level speaking event for cross-module echo prevention.
        # Avoids circular imports — responder.py defines the event and imports
        # speech.py, so we import responder lazily inside the loop function.
        from ai.responder import _speaking_event as _speaking_event_local

        while self._mic_monitor_running:
            try:
                stream = sd.InputStream(
                    device=device,
                    samplerate=16000,
                    channels=1,
                    dtype="int16",
                    blocksize=1024,
                )
                stream.start()

                while self._mic_monitor_running:
                    data, _ = stream.read(1024)

                    # If BARQ is speaking (TTS playback), discard audio frames
                    # by skipping RMS computation.  The stream is still read to
                    # drain the OS audio buffer (prevents stale data buildup).
                    if _speaking_event_local.is_set():
                        self._current_mic_level = 0.0
                        continue

                    try:
                        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                        self._current_mic_level = min(1.0, rms / 10000.0)
                    except Exception:
                        self._current_mic_level = 0.0

            except Exception as e:
                err_str = str(e)
                # Ignore benign "stream closed" or "input overflowed" errors
                if "Stream closed" not in err_str and "Input overflowed" not in err_str:
                    print(f"[Speech] Mic monitor error: {e}")
                self._current_mic_level = 0.0

            # Wait before retrying if the stream failed
            import time
            time.sleep(0.5)

    def _get_model(self):
        """Lazy-load the faster-whisper model (~4x faster than OpenAI Whisper)."""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            model_size = self.settings.whisper_model
            print(f"[Speech] Loading faster-whisper model '{model_size}' (CPU int8)...")
            self._whisper_model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
            )
            print("[Speech] faster-whisper model loaded")
        return self._whisper_model

    def transcribe(self, audio_path: str | Path) -> str:
        """
        Transcribe an audio file to text using faster-whisper.

        Auto-detects the spoken language from the audio (language=None)
        and switches the system language + TTS voice accordingly.

        Args:
            audio_path: Path to the audio file (WAV/MP3/OGG)

        Returns:
            Transcribed text
        """
        model = self._get_model()
        # language=None → faster-whisper auto-detects the language
        segments, info = model.transcribe(str(audio_path), language=None, beam_size=3, vad_filter=True)
        # Build segments list once for both text and confidence
        segments_list = list(segments)
        text = " ".join(seg.text.strip() for seg in segments_list)
        confidence = self._compute_confidence(segments_list)

        # ── Auto-detect and switch language ────────────────────────
        self._handle_detected_language(info, text, confidence)

        return text

    def get_piper_engine(self) -> PiperTTSEngine:
        """Get or create the lazy-loaded Piper TTS engine."""
        if self._piper_engine is None:
            self._piper_engine = PiperTTSEngine()
        return self._piper_engine

    async def synthesize(self, text: str, voice: str = "en-US-JennyNeural") -> bytes:
        """
        Convert text to speech using the currently active TTS backend.

        Args:
            text: The text to speak
            voice: Edge TTS voice name (only used by "edge" backend)

        Returns:
            Audio bytes (MP3 format for "edge", WAV format for "piper")
        """
        if self.tts_backend == "piper":
            return await asyncio.to_thread(self.get_piper_engine().synthesize, text)

        # Default: Edge TTS
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

    async def synthesize_pcm(self, text: str, voice: str = "") -> tuple[np.ndarray, int]:
        """
        Convert text to speech and return decoded PCM audio for in-memory playback.

        Uses the currently active TTS backend:
        - "edge": Uses PyAV to decode MP3 bytes on-the-fly
        - "piper": Returns float32 PCM directly from Piper (no decode needed)

        Args:
            text: The text to speak
            voice: Edge TTS voice name (only used by "edge" backend)

        Returns:
            Tuple of (audio_float32 normalized to [-1.0, 1.0], sample_rate)
        """
        if self.tts_backend == "piper":
            return await asyncio.to_thread(self.get_piper_engine().synthesize_pcm, text)

        # Default: Edge TTS → decode MP3 to PCM via PyAV
        import av

        mp3_bytes = await self.synthesize(text, voice or self.tts_voice)

        container = av.open(io.BytesIO(mp3_bytes), format="mp3")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)

        pcm_chunks: list[np.ndarray] = []
        for frame in container.decode(audio=0):
            resampled = resampler.resample(frame)
            for r in resampled:
                pcm_chunks.append(r.to_ndarray().flatten())

        container.close()

        if not pcm_chunks:
            raise ValueError("No audio frames decoded from TTS output")

        audio = np.concatenate(pcm_chunks).astype(np.float32) / 32768.0
        return audio, 24000

    async def transcribe_microphone(self, duration: float = 5.0) -> str:
        """
        Record from microphone and transcribe.

        Args:
            duration: Recording duration in seconds

        Returns:
            Transcribed text
        """
        import sounddevice as sd

        # Resolve input device from config
        from .audio_device import resolve_input_device
        device = resolve_input_device(self.settings.audio_input_device)

        # Record audio
        data = sd.rec(
            int(16000 * duration),
            samplerate=16000,
            channels=1,
            dtype="int16",
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
        import numpy as np
        import sounddevice as sd

        from .audio_device import resolve_input_device
        device = resolve_input_device(self.settings.audio_input_device)

        stream = sd.InputStream(
            device=device,
            samplerate=16000,
            channels=1,
            dtype="int16",
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
        import numpy as np
        import sounddevice as sd

        from .audio_device import resolve_input_device
        device = resolve_input_device(self.settings.audio_input_device)

        stream = sd.InputStream(
            device=device,
            samplerate=16000,
            channels=1,
            dtype="int16",
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

        # Stop the background mic monitor BEFORE opening our stream to avoid
        # resource contention (two streams on the same device).
        self.stop_mic_monitor()

        try:
            for _ in range(max_chunks):
                data, overflowed = stream.read(1024)
                frames.append(data)
                chunk_count += 1

                try:
                    rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                    # Update live mic level (used by WebSocket for sphere reactivity)
                    self._current_mic_level = min(1.0, rms / 10000.0)
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
            # Restart the background mic monitor so level readings continue
            # (sphere stays reactive between turns).
            self.start_mic_monitor()

    async def _transcribe_frames(self, frames: list) -> dict:
        """Helper: save audio frames to a temp WAV and return transcription + confidence.

        Auto-detects language from the audio (language=None) and switches
        the system language + TTS voice if a different language is detected.

        Returns a dict with:
            {"text": "...", "confidence": 0.0-1.0, "language": "en"|"hi"}

        Confidence is derived from faster-whisper's avg_logprob per segment.
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
            # language=None → faster-whisper auto-detects the language from audio
            segments, info = model.transcribe(str(temp_path), language=None, beam_size=3, vad_filter=True)
            segments_list = list(segments)
            text = " ".join(seg.text.strip() for seg in segments_list)
            confidence = self._compute_confidence(segments_list)

            # ── Auto-detect and switch language ────────────────────
            self._handle_detected_language(info, text, confidence)
            detected_lang = getattr(info, "language", None) or "en"

            return {
                "text": text,
                "confidence": confidence,
                "language": detected_lang,
            }
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _handle_detected_language(self, info, text: str, confidence: float):
        """Check the detected language and switch system language if needed.

        Used by the file-based ``transcribe()`` path.

        Args:
            info: faster-whisper info object (has .language attribute).
            text: Transcribed text (must be non-empty to avoid noise-triggered switches).
            confidence: Confidence score (0.0–1.0) from ``_compute_confidence()``.
        """
        detected_lang = getattr(info, "language", None) or "en"
        if self._should_switch_language(detected_lang, text, confidence):
            self.stt_language = detected_lang
            if self.on_language_detected:
                try:
                    self.on_language_detected(detected_lang)
                except Exception as e:
                    print(f"[Speech] Language change callback error: {e}")

    def _should_switch_language(self, detected_lang: str, text: str, confidence: float | None) -> bool:
        """Decide whether to switch the active language based on detection.

        Only auto-switches between "en" and "hi".  Requires non-empty text
        to avoid switching on noise.  If a confidence score is available,
        also requires it to be >= 0.3 to avoid false positives from noisy audio.
        """
        if detected_lang not in ("en", "hi"):
            return False
        if detected_lang == self.stt_language:
            return False
        if not text or not text.strip():
            return False
        if confidence is not None and confidence < 0.3:
            return False
        return True

    def _compute_confidence(self, segments: list) -> float:
        """Compute a 0.0–1.0 confidence score from faster-whisper segments.

        Uses avg_logprob (converted via exp() to average token probability)
        and no_speech_prob as a penalty.  Supports both dict-style and
        attribute-style segment access (faster-whisper vs openai-whisper).
        """
        if not segments:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for seg in segments:
            # Handle both dict-style (openai-whisper) and attribute-style (faster-whisper)
            if isinstance(seg, dict):
                token_prob = float(seg.get("avg_logprob", -5.0))
                no_speech = float(seg.get("no_speech_prob", 0.0))
                duration = float(seg.get("end", 1.0)) - float(seg.get("start", 0.0))
            else:
                token_prob = float(getattr(seg, "avg_logprob", -5.0))
                no_speech = float(getattr(seg, "no_speech_prob", 0.0))
                duration = float(getattr(seg, "end", 1.0)) - float(getattr(seg, "start", 0.0))

            # avg_logprob is negative, exp() gives average token probability in [0, 1]
            token_prob = max(0.0, min(1.0, 2.71828 ** token_prob))

            # no_speech_prob: higher → more likely not speech → penalise
            score = token_prob * (1.0 - no_speech)
            weighted_sum += score * duration
            total_weight += duration

        if total_weight <= 0:
            return 0.0

        return round(min(1.0, weighted_sum / total_weight), 4)
