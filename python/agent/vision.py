"""
BARQ Visual Awareness — real-time screen and webcam analysis via Gemini.

Inspired by MARK XXXIX-OR's screen_processor.py, this module captures
screenshots or webcam frames and sends them to Gemini 2.5 Flash for
analysis.  The response is spoken aloud via TTS for a seamless
hands-free experience.

Requirements (optional, for camera):
    - opencv-python (cv2)
    - Pillow (PIL)
    - mss (screen capture)
"""

import asyncio
import base64
import builtins
import io
import json
import os
import sys
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Optional, Tuple

try:
    import mss
    import mss.tools
    _MSS_OK = True
except ImportError:
    _MSS_OK = False

try:
    import PIL.Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False


def _safe_print(*args, **kwargs) -> None:
    """Console-safe print for Windows cp1252 terminals.

    Windows consoles default to the cp1252 codec, which cannot encode emoji or
    other non-Latin-1 characters.  A bare ``print()`` of such text raises
    ``UnicodeEncodeError`` ('charmap' codec error) and can kill the calling
    thread — which is exactly what crashed the vision stream thread and made
    ``vision_stream_start`` report an error.  This helper re-encodes with the
    console's own codec using ``errors="replace"`` (preserving encodable
    characters like ``°C`` or accents, replacing only emoji), so logging
    never crashes the stream.
    """
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        # First pass: re-encode with the console's actual codec (preserves
        # encodable characters like °C or accents).  If the output still
        # can't be encoded (e.g. the console is cp1252 but stdout reports
        # utf-8), fall back to ASCII replacement — never raise.
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            safe = [
                a.encode(enc, errors="replace").decode(enc)
                if isinstance(a, str) else a
                for a in args
            ]
            builtins.print(*safe, **kwargs)
        except UnicodeEncodeError:
            safe = [
                a.encode("ascii", errors="replace").decode("ascii")
                if isinstance(a, str) else a
                for a in args
            ]
            builtins.print(*safe, **kwargs)


# ─── Configuration ───────────────────────────────────────────────────────────

# Higher resolution (1280x720) matches Mark-L's quality for detailed analysis
IMG_MAX_WIDTH = 1280
IMG_MAX_HEIGHT = 720
JPEG_QUALITY = 82  # Higher quality for better Gemini vision analysis

DEFAULT_VISION_PROMPT = "What do you see in this image? Describe it concisely."

# Cache for auto-detected camera index
_camera_index_cache: int = -1


# ─── Camera Auto-Detection (like Mark-L's _probe_camera) ────────────────────

def _cv2_backend() -> int:
    """Return the best OpenCV camera backend for the current OS."""
    if not _CV2_OK:
        return 0
    import platform
    os_name = platform.system().lower()
    if os_name == "windows":
        return cv2.CAP_DSHOW
    if os_name == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:
    """Test if a camera index produces a valid frame."""
    if not _CV2_OK:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    import numpy as np
    return bool(np.mean(frame) > 8)


def auto_detect_camera() -> int:
    """Auto-detect the first working camera index.

    Probes indices 0-5 and returns the first that produces a valid frame.
    Caches the result so subsequent calls are instant.
    Matches Mark-L's approach.
    """
    global _camera_index_cache
    if _camera_index_cache >= 0:
        return _camera_index_cache

    backend = _cv2_backend()
    _safe_print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            _safe_print(f"[Vision] ✅ Camera found at index {idx}")
            _camera_index_cache = idx
            return idx

    _safe_print("[Vision] ⚠️  No camera found — defaulting to index 0")
    _camera_index_cache = 0
    return 0


# ─── Image Capture ──────────────────────────────────────────────────────────

def capture_screen() -> Tuple[bytes, str]:
    """Capture the primary monitor screen.

    Returns:
        Tuple of (image_bytes, mime_type).
        Image is resized JPEG for efficient API usage.
    """
    if not _MSS_OK:
        raise RuntimeError(
            "mss not installed. Run: pip install mss"
        )

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        png_bytes = mss.tools.to_png(shot.rgb, shot.size)

    if _PIL_OK:
        img = PIL.Image.open(io.BytesIO(png_bytes)).convert("RGB")
        img.thumbnail((IMG_MAX_WIDTH, IMG_MAX_HEIGHT), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=False)
        return buf.getvalue(), "image/jpeg"

    return png_bytes, "image/png"


def capture_camera(camera_index: int = -1) -> Tuple[bytes, str]:
    """Capture a frame from the webcam.

    Uses auto-detection when camera_index is -1 (default) — probes indices 0-5
    and picks the first working camera, just like Mark-L.

    Args:
        camera_index: Camera device index. Use -1 for auto-detect (default).

    Returns:
        Tuple of (image_bytes, mime_type).

    Raises:
        RuntimeError: If OpenCV is not installed or camera cannot be opened.
    """
    if not _CV2_OK:
        raise RuntimeError(
            "OpenCV not installed. Run: pip install opencv-python"
        )

    if camera_index < 0:
        camera_index = auto_detect_camera()

    backend = _cv2_backend()
    cap = cv2.VideoCapture(camera_index, backend)
    if not cap.isOpened():
        raise RuntimeError(f"Camera could not be opened: index {camera_index}")

    # Warm up the camera by reading several frames (like Mark-L)
    for _ in range(10):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Could not capture camera frame.")

    if _PIL_OK:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((IMG_MAX_WIDTH, IMG_MAX_HEIGHT), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=False)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes(), "image/jpeg"


# ─── Gemini Vision Analysis (async-safe) ────────────────────────────────────

async def analyze_image_with_gemini(
    image_bytes: bytes,
    mime_type: str,
    prompt: str = DEFAULT_VISION_PROMPT,
    api_key: Optional[str] = None,
) -> str:
    """Send an image to Gemini for analysis and return the text description.

    Uses Google's Gemini 2.5 Flash model for fast, accurate image analysis.
    The synchronous Gemini API call is offloaded to a thread so it doesn't
    block the async event loop.

    Args:
        image_bytes: The image data bytes.
        mime_type: MIME type of the image (e.g. 'image/jpeg').
        prompt: The question or instruction about the image.
        api_key: Gemini API key. Falls back to config file if not provided.

    Returns:
        The model's text response describing the image.
    """
    if api_key is None:
        api_key = _load_gemini_api_key()

    try:
        from google import genai
    except ImportError:
        raise RuntimeError(
            "google-genai not installed. Run: pip install google-genai"
        )

    # Create client in the calling thread, but run content generation
    # via to_thread so the event loop isn't blocked by network I/O
    def _call_gemini() -> str:
        client = genai.Client(api_key=api_key)
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                prompt,
                {"inline_data": {"mime_type": mime_type, "data": img_b64}},
            ],
        )
        return response.text.strip() if response.text else "I couldn't analyze the image."

    return await asyncio.to_thread(_call_gemini)


# ─── Gemini Live Vision (Real-time Audio, fully async) ──────────────────────

async def analyze_image_with_gemini_live(
    image_bytes: bytes,
    mime_type: str,
    prompt: str = DEFAULT_VISION_PROMPT,
    api_key: Optional[str] = None,
) -> bytes:
    """Send an image to Gemini Live for analysis and return audio response.

    Uses Gemini's native audio output modality for a voice-first experience.
    The response is spoken directly — no separate TTS step needed.

    This is an async function — call with ``await`` from within an event loop.

    Args:
        image_bytes: The image data bytes.
        mime_type: MIME type of the image.
        prompt: The question about the image.
        api_key: Gemini API key.

    Returns:
        Raw PCM audio bytes (16-bit, 24000 Hz, mono) of the spoken response.
    """
    if api_key is None:
        api_key = _load_gemini_api_key()

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed")

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1beta"},
    )

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription={},
        system_instruction=(
            "You are BARQ, a voice AI assistant. "
            "Analyze images with precision. "
            "Be concise — 1-3 sentences max. "
            "Address the user naturally."
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Charon"
                )
            )
        ),
    )

    b64_url = base64.b64encode(image_bytes).decode("utf-8")
    audio_chunks: list[bytes] = []

    async with client.aio.live.connect(
        model="models/gemini-2.5-flash-native-audio-preview-12-2025",
        config=config,
    ) as session:
        await session.send_client_content(
            turns={
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": b64_url}},
                    {"text": prompt},
                ]
            },
            turn_complete=True,
        )

        async for response in session.receive():
            if response.data:
                audio_chunks.append(response.data)

    if not audio_chunks:
        raise ValueError("No audio response received from Gemini Live")

    return b"".join(audio_chunks)


# ─── API Key Loading ────────────────────────────────────────────────────────

def _load_gemini_api_key() -> str:
    """Load the Gemini API key from config file, env var, or .env file.

    Checks in order:
    1. config/api_keys.json
    2. GEMINI_API_KEY environment variable
    3. .env file direct read (in case load_dotenv didn't load the var)

    Returns:
        The API key string.

    Raises:
        RuntimeError: If the key cannot be found in any source.
    """
    config_path = Path(os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "api_keys.json"
    ))

    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            key = data.get("gemini_api_key", "")
            if key:
                return key
        except Exception:
            pass

    # Environment variable
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        return key

    # Fallback: read .env file directly
    try:
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            text = env_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY=") or line.startswith("export GEMINI_API_KEY="):
                    raw = line.split("=", 1)[1].strip()
                    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
                        raw = raw[1:-1]
                    if raw:
                        return raw
    except Exception:
        pass

    raise RuntimeError(
        "Gemini API key not found. "
        "Set it in config/api_keys.json or as GEMINI_API_KEY environment variable."
    )


# ═══════════════════════════════════════════════════════════════════════
# Persistent Gemini Live Streaming Session (like Mark-L's _VisionSession)
# ═══════════════════════════════════════════════════════════════════════

_GEMINI_LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
_LIVE_SAMPLE_RATE = 24000
_LIVE_CHANNELS = 1
_LIVE_CHUNK_SIZE = 1024

_LIVE_SYSTEM_PROMPT = (
    "You are BARQ, a voice AI assistant. "
    "You are given an image from the user's screen or webcam. "
    "Analyze what you see with precision. "
    "Describe objects, text, and context clearly. "
    "Be concise — 1-3 sentences — unless the question demands more detail. "
    "Speak directly to the user."
)


class VisionStreamSession:
    """Persistent Gemini Live vision session in a background thread.

    Maintains a long-lived WebSocket connection to Gemini Live so that
    images can be sent and analysed with zero connection latency.
    Audio responses are collected and returned via a callback.

    Like Mark-L's ``_VisionSession``, this runs its own asyncio event
    loop in a daemon thread and auto-reconnects on failure.

    Usage:
        session = VisionStreamSession()
        session.start()
        session.analyze(image_bytes, mime_type, "What do you see?")
        session.stop()
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session = None  # Gemini Live session
        self._out_queue: Optional[asyncio.Queue] = None  # (image, mime, prompt)
        self._audio_callback: Optional[callable] = None  # called with PCM chunks
        self._transcript_callback: Optional[callable] = None  # called with text
        self._ready_evt = threading.Event()
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        self._connected = False
        self._backoff = 2.0

        # Synchronous analysis support (used by the voice function executor):
        # a single pending future that the transcript loop resolves with the
        # text response for the image currently being analysed.
        self._sync_lock = threading.Lock()
        self._sync_future: Optional[Future] = None

        # Completed transcripts queue, drained by non-synchronous producers
        # (e.g. ``POST /vision/stream/analyze``) so the FIFO stays aligned
        # for synchronous consumers like the voice agent.
        self._transcript_queue: Optional[asyncio.Queue] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_ready(self) -> bool:
        return self._ready_evt.is_set() and self._connected

    def start(self, audio_callback=None, transcript_callback=None,
              timeout: float = 25.0) -> bool:
        """Start the persistent session in a background thread.

        Args:
            audio_callback: Called with PCM audio chunks (bytes).
            transcript_callback: Called with transcript text (str).
            timeout: Max seconds to wait for initial connection.

        Returns:
            True if session connected within timeout.
        """
        with self._lock:
            if self._thread and self._thread.is_alive():
                if audio_callback:
                    self._audio_callback = audio_callback
                if transcript_callback:
                    self._transcript_callback = transcript_callback
                return self._ready_evt.is_set()

            self._audio_callback = audio_callback
            self._transcript_callback = transcript_callback
            self._stop_evt.clear()
            self._thread = threading.Thread(
                target=self._run_event_loop,
                daemon=True,
                name="VisionStreamThread",
            )
            self._thread.start()

        ok = self._ready_evt.wait(timeout=timeout)
        if ok:
            _safe_print("[VisionStream] ✅ Session ready")
        else:
            _safe_print(f"[VisionStream] ⚠️  Session did not connect within {timeout}s")
        return ok

    def stop(self):
        """Stop the session and background thread."""
        self._stop_evt.set()
        self._ready_evt.clear()
        self._connected = False
        if self._loop and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._close_session(), self._loop
                )
            except Exception:
                pass

    def analyze(self, image_bytes: bytes, mime_type: str, user_text: str):
        """Queue an image for analysis via the persistent Gemini Live session.

        This is non-blocking — returns immediately. The response comes
        back via the ``audio_callback`` and ``transcript_callback``.
        """
        if not self._loop or not self._out_queue or not self._connected:
            _safe_print("[VisionStream] ⚠️  Session not ready — dropping request")
            return False
        try:
            asyncio.run_coroutine_threadsafe(
                self._out_queue.put((image_bytes, mime_type, user_text)),
                self._loop,
            )
            return True
        except Exception as e:
            _safe_print(f"[VisionStream] Queue error: {e}")
            return False

    def analyze_and_wait(
        self,
        image_bytes: bytes,
        mime_type: str,
        user_text: str,
        timeout: float = 30.0,
    ) -> str:
        """Queue an image and block until the text transcript comes back.

        This is the synchronous counterpart to ``analyze()`` — it returns the
        model's text description instead of delivering it via callbacks.
        Used by the voice function executor so the Gemini voice agent can see
        the screen mid-conversation through the warm persistent stream.

        Only one synchronous analysis runs at a time (serialized by a lock).
        Because the send loop processes queued images strictly in FIFO order,
        the first transcript delivered while this request is pending is the
        response to the image we just queued.

        Args:
            image_bytes: The image data bytes.
            mime_type: MIME type of the image.
            user_text: The prompt/question about the image.
            timeout: Max seconds to wait for the transcript.

        Returns:
            The model's text description.

        Raises:
            RuntimeError: If the stream is not ready (request dropped).
            TimeoutError: If no transcript arrives within ``timeout``.
        """
        with self._sync_lock:
            fut: Future = Future()
            self._sync_future = fut
            try:
                queued = self.analyze(image_bytes, mime_type, user_text)
                if not queued:
                    raise RuntimeError(
                        "Vision stream not ready — request dropped"
                    )
                try:
                    return fut.result(timeout=timeout)
                except FutureTimeoutError:
                    raise TimeoutError(
                        f"Vision stream analysis timed out after {timeout}s"
                    )
            finally:
                self._sync_future = None

    def _deliver_transcript(self, full: str) -> None:
        """Deliver a completed transcript to callbacks and/or the sync future.

        Runs on the vision stream's event-loop thread. The user callback (if
        any) is called first so audio/captions flows are unaffected, then any
        pending synchronous analysis future is resolved, and finally the
        transcript is queued for non-synchronous consumers to drain.
        """
        if self._transcript_callback:
            try:
                self._transcript_callback(full)
            except Exception as e:
                _safe_print(f"[VisionStream] ⚠️  Transcript callback error: {e}")
        fut = self._sync_future
        if fut is not None and not fut.done():
            fut.set_result(full)
        if self._transcript_queue is not None:
            try:
                self._transcript_queue.put_nowait(full)
            except asyncio.QueueFull:
                pass

    async def await_next_transcript(self, timeout: float = 1.5) -> Optional[str]:
        """Consume the next completed transcript (non-blocking best-effort).

        Used by non-synchronous producers (e.g. ``POST /vision/stream/analyze``)
        to drain their own response from the stream, keeping the FIFO aligned
        for synchronous consumers like the Gemini voice agent.

        Returns:
            The transcript text, or None if none arrived within ``timeout``.
        """
        if self._transcript_queue is None:
            return None
        try:
            return await asyncio.wait_for(
                self._transcript_queue.get(), timeout=timeout
            )
        except Exception:
            return None

    # ── Internal: thread loop ────────────────────────────────────────

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session_loop())
        except Exception as e:
            _safe_print(f"[VisionStream] Thread error: {e}")
        finally:
            self._loop.close()

    async def _close_session(self):
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    async def _session_loop(self):
        self._out_queue = asyncio.Queue(maxsize=30)
        self._transcript_queue = asyncio.Queue(maxsize=100)

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            _safe_print("[VisionStream] google-genai not installed")
            return

        api_key = _load_gemini_api_key()

        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            system_instruction=_LIVE_SYSTEM_PROMPT,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

        self._backoff = 2.0

        while not self._stop_evt.is_set():
            try:
                _safe_print("[VisionStream] 🔌 Connecting to Gemini Live...")
                async with client.aio.live.connect(
                    model=_GEMINI_LIVE_MODEL, config=config
                ) as session:
                    self._session = session
                    self._connected = True
                    self._ready_evt.set()
                    self._backoff = 2.0
                    _safe_print("[VisionStream] ✅ Connected to Gemini Live")

                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._send_loop())
                        tg.create_task(self._recv_loop())
                        # Keep alive until stopped or disconnected
                        while not self._stop_evt.is_set():
                            await asyncio.sleep(0.5)

            except Exception as eg:
                _safe_print(f"[VisionStream] ⚠️  Session error: {eg}")
            finally:
                self._session = None
                self._connected = False
                self._ready_evt.clear()

            if self._stop_evt.is_set():
                break

            _safe_print(f"[VisionStream] 🔄 Reconnecting in {self._backoff:.0f}s...")
            await asyncio.sleep(self._backoff)
            self._backoff = min(self._backoff * 1.5, 30.0)

    async def _send_loop(self):
        """Send images from the out queue to Gemini Live."""
        while not self._stop_evt.is_set():
            try:
                image_bytes, mime_type, user_text = (
                    await asyncio.wait_for(self._out_queue.get(), timeout=1.0)
                )
            except asyncio.TimeoutError:
                continue

            if not self._session:
                _safe_print("[VisionStream] ⚠️  No session — dropping image")
                continue

            try:
                b64 = base64.b64encode(image_bytes).decode("ascii")
                await self._session.send_client_content(
                    turns={
                        "parts": [
                            {"inline_data": {"mime_type": mime_type, "data": b64}},
                            {"text": user_text},
                        ]
                    },
                    turn_complete=True,
                )
                _safe_print(f"[VisionStream] 📤 Sent {len(image_bytes):,}B — '{user_text[:50]}'")
            except Exception as e:
                _safe_print(f"[VisionStream] ⚠️  Send error: {e}")
                raise  # triggers session reconnect

    async def _recv_loop(self):
        """Receive audio and transcript from Gemini Live."""
        transcript: list[str] = []
        try:
            async for response in self._session.receive():
                # Audio data
                if response.data and self._audio_callback:
                    self._audio_callback(response.data)

                # Transcription
                sc = response.server_content
                if not sc:
                    continue

                if sc.output_transcription and sc.output_transcription.text:
                    chunk = sc.output_transcription.text.strip()
                    if chunk:
                        transcript.append(chunk)

                if sc.turn_complete:
                    if transcript:
                        full = " ".join(transcript).strip()
                        _safe_print(f"[VisionStream] 💬 '{full[:80]}'")
                        self._deliver_transcript(full)
                    transcript = []

        except Exception as e:
            _safe_print(f"[VisionStream] ⚠️  Recv error: {e}")
            raise  # triggers session reconnect


# ── Singleton factory ─────────────────────────────────────────────────

_vision_stream_session: Optional[VisionStreamSession] = None


def get_vision_stream_session() -> Optional[VisionStreamSession]:
    """Get or create the VisionStreamSession singleton."""
    global _vision_stream_session
    if _vision_stream_session is None:
        _vision_stream_session = VisionStreamSession()
    return _vision_stream_session


def ensure_vision_stream(audio_callback=None, transcript_callback=None,
                         timeout: float = 25.0) -> bool:
    """Ensure the persistent vision stream session is running.

    Returns True if the session is connected and ready.
    """
    session = get_vision_stream_session()
    if session.is_ready:
        return True
    return session.start(
        audio_callback=audio_callback,
        transcript_callback=transcript_callback,
        timeout=timeout,
    )


def stop_vision_stream():
    """Stop the persistent vision stream session."""
    global _vision_stream_session
    if _vision_stream_session is not None:
        _vision_stream_session.stop()
        _vision_stream_session = None
