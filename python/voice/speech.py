"""
BARQ Speech Processing — now powered by Deepgram Voice Agent.

The old local pipeline (Whisper STT, Edge TTS, Piper TTS, mic monitoring,
streaming transcription) has been replaced by Deepgram's managed
Voice Agent pipeline.

A minimal SpeechProcessor class is retained for backward compatibility
with vision_routes.py (which uses synthesize() for TTS).
"""

from typing import Optional


class SpeechProcessor:
    """Minimal SpeechProcessor — delegates all TTS to Deepgram's REST API.

    The full local pipeline has been replaced by the Deepgram Voice Agent
    (see deepgram_agent.py). This stub only retains synthesize() for
    vision_routes.py compatibility.
    """

    def __init__(self):
        self.tts_voice: str = "aura-2-odysseus-en"
        self.tts_backend: str = "deepgram_agent"
        self.stt_backend: str = "deepgram_agent"
        self.stt_language: str = "en"
        self._whisper_model = None

    # ── Method stubs for backward compatibility ────────────────────

    def get_mic_level(self) -> float:
        return 0.0

    def start_mic_monitor(self):
        pass

    def stop_mic_monitor(self):
        pass

    async def flush_audio_buffer(self, duration: float = 0.15):
        pass

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        """Synthesize speech via Deepgram TTS REST API.

        Calls the Deepgram TTS endpoint directly with httpx.
        Returns WAV bytes, or empty bytes on failure.
        """
        import os
        import httpx

        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        if not api_key:
            print("[Speech] No DEEPGRAM_API_KEY configured — cannot synthesize")
            return b""

        model = voice or self.tts_voice or "aura-2-odysseus-en"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.deepgram.com/v1/speak",
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model": model,
                        "container": "wav",
                        "encoding": "linear16",
                        "sample_rate": 24000,
                    },
                )
                if resp.status_code == 200:
                    return resp.content
                else:
                    print(f"[Speech] Deepgram TTS error {resp.status_code}: {resp.text[:200]}")
                    return b""
        except Exception as e:
            print(f"[Speech] Deepgram TTS request failed: {e}")
            return b""

    async def synthesize_pcm(self, text: str, voice: str = "") -> tuple:
        """Synthesize speech and return (float32 PCM, sample_rate).

        Uses Deepgram TTS REST API.
        """
        import io
        import wave
        import numpy as np

        wav_bytes = await self.synthesize(text, voice)
        if not wav_bytes:
            return np.array([], dtype=np.float32), 24000

        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                rate = wf.getframerate()
                pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                return pcm, rate
        except Exception as e:
            print(f"[Speech] WAV decode error: {e}")
            return np.array([], dtype=np.float32), 24000

    async def transcribe(self, audio_path: str) -> str:
        """Transcribe audio via Deepgram REST API."""
        import os
        import httpx

        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        if not api_key:
            return ""

        try:
            with open(audio_path, "rb") as f:
                audio_data = f.read()

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": "audio/wav",
                    },
                    params={"model": "nova-2", "version": "v2"},
                    content=audio_data,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
                return ""
        except Exception as e:
            print(f"[Speech] Deepgram STT error: {e}")
            return ""

    async def transcribe_microphone(self, duration: float = 5.0) -> str:
        print("[Speech] transcribe_microphone unavailable (use Voice Agent)")
        return ""

    async def transcribe_until_silence(self, **kwargs) -> Optional[str]:
        print("[Speech] transcribe_until_silence unavailable (use Voice Agent)")
        return None

    async def transcribe_streaming(self, **kwargs):
        print("[Speech] transcribe_streaming unavailable (use Voice Agent)")
        return
        yield  # make it a generator
