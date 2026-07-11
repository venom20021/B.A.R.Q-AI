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
import io
import json
import os
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


# ─── Configuration ───────────────────────────────────────────────────────────

IMG_MAX_WIDTH = 640
IMG_MAX_HEIGHT = 360
JPEG_QUALITY = 55

DEFAULT_VISION_PROMPT = "What do you see in this image? Describe it concisely."


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


def capture_camera(camera_index: int = 0) -> Tuple[bytes, str]:
    """Capture a frame from the webcam.

    Args:
        camera_index: Camera device index (default: 0).

    Returns:
        Tuple of (image_bytes, mime_type).

    Raises:
        RuntimeError: If OpenCV is not installed or camera cannot be opened.
    """
    if not _CV2_OK:
        raise RuntimeError(
            "OpenCV not installed. Run: pip install opencv-python"
        )

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Camera could not be opened: index {camera_index}")

    # Warm up the camera by reading a few frames
    for _ in range(5):
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
    """Load the Gemini API key from the config file.

    Looks for the key in the same config file used by the rest of BARQ.
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

    # Fall back to environment variable
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        return key

    raise RuntimeError(
        "Gemini API key not found. "
        "Set it in config/api_keys.json or as GEMINI_API_KEY environment variable."
    )
