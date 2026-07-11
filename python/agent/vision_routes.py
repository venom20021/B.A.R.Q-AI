"""
FastAPI routes for BARQ Visual Awareness.

Provides endpoints for:
- Screenshot capture and analysis (Gemini vision)
- Webcam capture and analysis
- Gemini Live voice-based vision analysis
"""

import base64

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .vision import (
    analyze_image_with_gemini,
    analyze_image_with_gemini_live,
    capture_camera,
    capture_screen,
)

router = APIRouter()


class VisionRequest(BaseModel):
    prompt: str = "What do you see? Be concise."
    angle: str = "screen"  # "screen" or "camera"
    camera_index: int = 0
    voice_response: bool = False  # If True, returns raw PCM audio


class ScreenRequest(BaseModel):
    """Request body for the /screen quick shortcut."""
    prompt: str = "What's on my screen? Be concise."


class CameraRequest(BaseModel):
    """Request body for the /camera quick shortcut."""
    prompt: str = "What do you see? Be concise."
    camera_index: int = 0


@router.post("/analyze", summary="Capture and analyze screen or webcam")
async def analyze_vision(request: VisionRequest):
    """Capture the screen (or webcam) and analyze it using Gemini vision.

    Returns a text description of what the AI sees.
    If ``voice_response=True``, returns raw PCM audio bytes (24000 Hz, mono s16le)
    instead of text — the frontend can play this directly.
    """
    try:
        # ── Capture ──────────────────────────────────────────────────
        if request.angle.lower() == "camera":
            image_bytes, mime_type = capture_camera(
                camera_index=request.camera_index
            )
            source = "camera"
        else:
            image_bytes, mime_type = capture_screen()
            source = "screen"

        if not image_bytes:
            raise HTTPException(status_code=500, detail="Failed to capture image")

        # ── Analyze ──────────────────────────────────────────────────
        if request.voice_response:
            # Gemini Live returns audio directly — no separate TTS needed
            audio_pcm = await analyze_image_with_gemini_live(
                image_bytes, mime_type, prompt=request.prompt
            )
            return {
                "status": "success",
                "source": source,
                "voice_response": True,
                "audio_pcm_base64": base64.b64encode(audio_pcm).decode("utf-8"),
                "sample_rate": 24000,
            }
        else:
            text = await analyze_image_with_gemini(
                image_bytes, mime_type, prompt=request.prompt
            )
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            return {
                "status": "success",
                "source": source,
                "text": text,
                "mime_type": mime_type,
                "image_size_bytes": len(image_bytes),
                "image_base64": f"data:{mime_type};base64,{image_b64}",
            }

    except HTTPException:
        raise
    except ImportError as e:
        return {"status": "unavailable", "message": str(e)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screen", summary="Capture and describe the screen (quick shortcut)")
async def analyze_screen(request: ScreenRequest):
    """Quick shortcut to capture and describe the screen.

    Accepts JSON body with an optional ``prompt`` field.
    Returns a text description of what's on screen.
    """
    try:
        image_bytes, mime_type = capture_screen()
        text = await analyze_image_with_gemini(image_bytes, mime_type, prompt=request.prompt)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        return {
            "status": "success",
            "text": text,
            "source": "screen",
            "image_base64": f"data:{mime_type};base64,{image_b64}",
        }
    except ImportError as e:
        return {"status": "unavailable", "message": str(e)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/camera", summary="Capture and describe webcam view")
async def analyze_camera(request: CameraRequest):
    """Quick shortcut to capture and describe the webcam view.

    Accepts JSON body with optional ``prompt`` and ``camera_index`` fields.
    """
    try:
        image_bytes, mime_type = capture_camera(camera_index=request.camera_index)
        text = await analyze_image_with_gemini(image_bytes, mime_type, prompt=request.prompt)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        return {
            "status": "success",
            "text": text,
            "source": "camera",
            "image_base64": f"data:{mime_type};base64,{image_b64}",
        }
    except ImportError as e:
        return {"status": "unavailable", "message": str(e)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check", summary="Check vision capabilities")
async def check_vision_capabilities():
    """Check which vision-related packages are installed and available."""
    capabilities = {
        "screen_capture": False,
        "webcam": False,
        "gemini_api": False,
        "gemini_live": False,
    }

    # Check mss for screen capture
    try:
        import mss  # noqa: F401
        capabilities["screen_capture"] = True
    except ImportError:
        pass

    # Check opencv for webcam
    try:
        import cv2  # noqa: F401
        capabilities["webcam"] = True
    except ImportError:
        pass

    # Check google-genai
    try:
        from google import genai  # noqa: F401
        capabilities["gemini_api"] = True
        # Check if Live API is available
        try:
            from google.genai import types  # noqa: F401
            capabilities["gemini_live"] = True
        except ImportError:
            pass
    except ImportError:
        pass

    return {
        "capabilities": capabilities,
        "missing": [
            pkg for pkg, installed in [
                ("mss (screen capture)", capabilities["screen_capture"]),
                ("opencv-python (webcam)", capabilities["webcam"]),
                ("google-genai (Gemini)", capabilities["gemini_api"]),
            ] if not installed
        ],
    }
