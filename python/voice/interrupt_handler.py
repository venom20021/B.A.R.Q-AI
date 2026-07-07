"""
Interrupt handler for voice interaction.
If BARQ is speaking and the user starts talking, BARQ stops
and listens to the user instead.
Supports both WAV and MP3 audio playback.

When used with the streaming pipeline, each sentence-chunk calls
``play_with_interrupt`` independently.  Pending interrupt-monitoring
tasks are cancelled between chunks to avoid resource leaks.
"""

import asyncio
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional


class InterruptHandler:
    """Detects when the user speaks over BARQ's audio response."""

    def __init__(self, energy_threshold: float = 500.0):
        self.is_playing = False
        self.should_stop = False
        self._pending_interrupt_task: Optional[asyncio.Task] = None
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
        # Cancel any lingering interrupt task from a previous call
        if self._pending_interrupt_task and not self._pending_interrupt_task.done():
            self._pending_interrupt_task.cancel()

        self.is_playing = True
        self.should_stop = False

        play_task = asyncio.create_task(self._play(audio_path))

        if listen_for_interrupt:
            interrupt_task = asyncio.create_task(self._detect_speech())
            self._pending_interrupt_task = interrupt_task

            done, pending = await asyncio.wait(
                [play_task, interrupt_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel whichever task is still pending
            for task in pending:
                task.cancel()

            if interrupt_task in done:
                self.should_stop = True
                play_task.cancel()
                print("[Interrupt] User spoke over BARQ — playback stopped")
                self.is_playing = False
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
            import sounddevice as sd
            import numpy as np

            from config import get_settings as _cfg
            from .audio_device import resolve_output_device
            output_device = resolve_output_device(_cfg().audio_output_device)

            audio_path_obj = Path(audio_path)
            if not audio_path_obj.exists():
                print(f"[Interrupt] Audio file not found: {audio_path}")
                return

            # Determine if MP3 — decode to WAV first
            wav_path_to_cleanup = None
            if audio_path.lower().endswith(".mp3"):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        wav_path = f.name
                        wav_path_to_cleanup = wav_path
                    result = subprocess.run(
                        ["ffmpeg", "-y", "-i", audio_path, "-acodec", "pcm_s16le",
                         "-ar", "22050", "-ac", "1", wav_path],
                        capture_output=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        audio_path = wav_path
                    else:
                        print(f"[Interrupt] ffmpeg decode failed")
                        return
                except FileNotFoundError:
                    print("[Interrupt] ffmpeg not found — cannot play MP3 audio")
                    return
                except Exception as e:
                    print(f"[Interrupt] MP3 decode error: {e}")
                    return

            # Read and parse WAV file
            with wave.open(str(audio_path), "rb") as wf:
                audio_data = np.frombuffer(
                    wf.readframes(wf.getnframes()), dtype=np.int16
                )
                rate = wf.getframerate()

            # Play via sounddevice
            sd.play(audio_data, rate, device=output_device)
            sd.wait()

            # Cleanup temp WAV file if it was a converted MP3
            if wav_path_to_cleanup:
                Path(wav_path_to_cleanup).unlink(missing_ok=True)

        except asyncio.CancelledError:
            sd.stop()
        except Exception as e:
            if "No default output device" not in str(e):
                print(f"[Interrupt] Playback error: {e}")
        finally:
            self.is_playing = False

    async def _detect_speech(self):
        """Monitor microphone for speech while audio is playing.

        Uses a simple energy-based detector with RMS computation.
        If mic RMS exceeds the threshold, speech is detected and this returns.
        """
        try:
            import sounddevice as sd
            import numpy as np

            from config import get_settings as _cfg
            from .audio_device import resolve_input_device
            input_device = resolve_input_device(_cfg().audio_input_device)

            stream = sd.InputStream(
                device=input_device,
                samplerate=16000,
                channels=1,
                dtype='int16',
                blocksize=1024,
            )
            stream.start()

            while self.is_playing and not self.should_stop:
                data, overflowed = stream.read(1024)
                rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                if rms > self.energy_threshold:
                    print(f"[Interrupt] Speech detected (RMS: {rms:.1f} > {self.energy_threshold:.1f})")
                    break
                await asyncio.sleep(0.05)

            stream.stop()
            stream.close()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Interrupt] Detection error: {e}")
