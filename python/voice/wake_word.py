"""
Wake word detection using Vosk offline speech recognition.
"""

import json
import queue
import threading
from typing import Callable, Optional

from config import get_settings


class WakeWordDetector:
    """Detects the wake word "Hey BARQ" using Vosk."""

    def __init__(self, on_wake_word: Optional[Callable] = None):
        self.settings = get_settings()
        self.on_wake_word = on_wake_word
        self._running = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None

        # Initialize Vosk model (lazy import - optional dependency)
        model_path = self.settings.vosk_model_path
        try:
            import vosk
            self.model = vosk.Model(model_path)
        except ImportError:
            print(f"[WakeWord] Vosk not installed. Install with: pip install vosk")
            self.model = None
        except Exception as e:
            print(f"[WakeWord] Failed to load Vosk model from {model_path}: {e}")
            self.model = None

    def start(self):
        """Start listening for wake word in a background thread."""
        if self._running or not self.model:
            return

        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        print("[WakeWord] Listening for 'Hey BARQ'...")

    def stop(self):
        """Stop wake word detection."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        print("[WakeWord] Stopped")

    def _listen_loop(self):
        """Continuously listen to microphone and detect wake word."""
        import pyaudio
        import vosk
        p = pyaudio.PyAudio()

        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=8000,
            )
        except Exception as e:
            print(f"[WakeWord] Failed to open audio stream: {e}")
            self._running = False
            return

        rec = vosk.KaldiRecognizer(self.model, 16000)

        while self._running:
            try:
                data = stream.read(4000, exception_on_overflow=False)
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower()

                    if self.settings.wake_word in text:
                        print(f"[WakeWord] Detected: '{text}'")
                        if self.on_wake_word:
                            self.on_wake_word()
            except Exception as e:
                print(f"[WakeWord] Error: {e}")

        stream.stop_stream()
        stream.close()
        p.terminate()
