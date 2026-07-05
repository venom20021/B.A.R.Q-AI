"""
Interrupt handler for voice interaction.
If BARQ is speaking and the user starts talking, BARQ stops
and listens to the user instead.
Supports both WAV and MP3 audio playback.
"""

import asyncio
import math
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class InterruptHandler:
    """Detects when the user speaks over BARQ's audio response."""

    def __init__(self, energy_threshold: float = 500.0):
        self.is_playing = False
        self.should_stop = False
        self.energy_threshold = energy_threshold  # RMS threshold for speech detection

    async def play_with_interrupt(
        self, audio_path: str, listen_for_interrupt: bool = True
    ) -> bool:
        """Play audio but stop if user starts speaking.

        Args:
            audio_path: Path to the audio file to play (WAV or MP3).
            listen_for_interrupt: Whether to monitor mic for interruption.

        Returns:
            True if playback was interrupted, False if it completed naturally.
        """
        self.is_playing = True
        self.should_stop = False

        play_task = asyncio.create_task(self._play(audio_path))

        if listen_for_interrupt:
            interrupt_task = asyncio.create_task(self._detect_speech())

            done, pending = await asyncio.wait(
                [play_task, interrupt_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if interrupt_task in done:
                self.should_stop = True
                play_task.cancel()
                print("[Interrupt] User spoke over BARQ — playback stopped")
                return True  # Interrupted
        else:
            await play_task

        self.is_playing = False
        return False  # Completed naturally

    async def _play(self, audio_path: str):
        """Play audio file through speakers. Supports WAV and MP3.

        MP3 files are decoded to WAV via ffplay/ffmpeg before playback.
        """
        try:
            import pyaudio

            audio_path_obj = Path(audio_path)
            if not audio_path_obj.exists():
                print(f"[Interrupt] Audio file not found: {audio_path}")
                return

            audio_bytes = audio_path_obj.read_bytes()

            # Determine if MP3 — decode to WAV first
            if audio_path.lower().endswith(".mp3"):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        wav_path = f.name
                    result = subprocess.run(
                        ["ffmpeg", "-y", "-i", audio_path, "-acodec", "pcm_s16le",
                         "-ar", "22050", "-ac", "1", wav_path],
                        capture_output=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        audio_bytes = Path(wav_path).read_bytes()
                    Path(wav_path).unlink(missing_ok=True)
                except FileNotFoundError:
                    print("[Interrupt] ffmpeg not found — cannot play MP3 audio")
                    return
                except Exception as e:
                    print(f"[Interrupt] MP3 decode error: {e}")
                    return

            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=22050,
                output=True,
            )
            stream.write(audio_bytes)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except asyncio.CancelledError:
            pass  # Expected when interrupted
        except Exception as e:
            print(f"[Interrupt] Playback error: {e}")
        finally:
            self.is_playing = False

    async def _detect_speech(self):
        """Monitor microphone for speech while audio is playing.

        Uses a simple energy-based detector with RMS computation.
        If mic RMS exceeds the threshold, speech is detected and this returns.
        """
        try:
            import pyaudio
            import math

            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024,
            )

            while self.is_playing and not self.should_stop:
                data = stream.read(1024, exception_on_overflow=False)
                # Compute RMS manually to avoid deprecated audioop
                samples = struct.unpack_from("<" + "h" * (len(data) // 2), data)
                if samples:
                    sum_sq = sum(s * s for s in samples)
                    rms = math.sqrt(sum_sq / len(samples))
                    if rms > self.energy_threshold:
                        print(f"[Interrupt] Speech detected (RMS: {rms:.1f} > {self.energy_threshold:.1f})")
                        break
                await asyncio.sleep(0.05)

            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            print(f"[Interrupt] Detection error: {e}")
