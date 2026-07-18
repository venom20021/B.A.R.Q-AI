"""
FastAPI routes for BARQ Visual Awareness.

Provides endpoints for:
- Screenshot capture and analysis (Gemini vision)
- Webcam capture and analysis
- Gemini Live voice-based vision analysis
- WebSocket real-time vision streaming
"""

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .vision import (
    analyze_image_with_gemini,
    analyze_image_with_gemini_live,
    capture_camera,
    capture_screen,
)

logger = logging.getLogger("barq.vision")

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


# ─── Helpers ───────────────────────────────────────────────────────────

def _check_gemini_api_key() -> bool:
    """Check if a Gemini API key is actually configured (not just the package)."""
    # Try config file
    config_path = Path(__file__).parent.parent / "config" / "api_keys.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if data.get("gemini_api_key", ""):
                return True
        except Exception:
            pass
    # Try env var
    if os.getenv("GEMINI_API_KEY", ""):
        return True
    return False


def _log_evolution_failure(event_type: str, metadata: dict) -> None:
    """Log a vision failure to the EvoMap evolution tracker."""
    try:
        from voice.evolution_logger import get_evolution_logger
        evo = get_evolution_logger()
        evo.record(event_type, metadata=metadata)
    except Exception:
        pass  # evolution logger is optional


# ─── REST Endpoints ────────────────────────────────────────────────────


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
    """Check which vision-related packages AND API keys are configured."""
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

    # Check google-genai AND actual API key
    try:
        from google import genai  # noqa: F401
        # Only mark gemini_api as ready if the API key is actually configured
        capabilities["gemini_api"] = _check_gemini_api_key()
        # Check if Live API is available (package + key)
        try:
            from google.genai import types  # noqa: F401
            capabilities["gemini_live"] = capabilities["gemini_api"]  # Live needs key too
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
                ("Gemini Live Audio", capabilities["gemini_live"]),
            ] if not installed
        ],
        "api_key_configured": _check_gemini_api_key(),
    }


# ─── WebSocket: Real-time Vision Streaming ─────────────────────────────

@router.websocket("/ws/vision")
async def vision_websocket(websocket: WebSocket):
    """WebSocket for real-time vision analysis streaming.

    Protocol:
    1. Server sends capability status on connect:
       ``{"type": "status", "gemini_available": true, "api_key_configured": true}``

    2. Client sends an analysis request:
       ``{"type": "analyze", "image_base64": "...", "mime_type": "image/jpeg", "prompt": "What is this?"}``

    3. Server streams response tokens:
       ``{"type": "token", "text": "I see a..."}``
       ``{"type": "done", "text": "I see a desktop with..."}``

    4. On error:
       ``{"type": "error", "message": "API key missing"}}``
    """
    await websocket.accept()
    logger.info("[Vision WS] Client connected")

    # ── Send initial capability status ───────────────────────────────
    api_key_ok = _check_gemini_api_key()
    gemini_pkg_ok = False
    try:
        from google import genai  # noqa: F401
        gemini_pkg_ok = True
    except ImportError:
        pass

    await websocket.send_json({
        "type": "status",
        "gemini_available": gemini_pkg_ok,
        "api_key_configured": api_key_ok,
        "ready": gemini_pkg_ok and api_key_ok,
    })

    if not api_key_ok:
        logger.warning("[Vision WS] Gemini API key not configured")
        await websocket.send_json({
            "type": "error",
            "component": "Gemini Vision",
            "message": "Gemini API key missing. Set GEMINI_API_KEY in config/api_keys.json or as environment variable.",
        })
        # Keep connection open so frontend can retry after user configures key
        # Wait for a potential re-configuration message or disconnect

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")

            if msg_type == "analyze":
                await _handle_vision_analyze(websocket, data, api_key_ok)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "configure":
                # Client is re-configuring (e.g. after user set API key)
                # Re-check the key
                api_key_ok = _check_gemini_api_key()
                await websocket.send_json({
                    "type": "status",
                    "gemini_available": gemini_pkg_ok,
                    "api_key_configured": api_key_ok,
                    "ready": gemini_pkg_ok and api_key_ok,
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("[Vision WS] Client disconnected")
    except Exception as e:
        logger.error(f"[Vision WS] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


async def _handle_vision_analyze(
    websocket: WebSocket,
    data: dict,
    api_key_ok: bool,
) -> None:
    """Handle an analyze request from the WebSocket client."""
    if not api_key_ok:
        await websocket.send_json({
            "type": "error",
            "message": "Gemini API key not configured. Configure it and send a 'configure' message.",
        })
        return

    image_base64 = data.get("image_base64", "")
    mime_type = data.get("mime_type", "image/jpeg")
    prompt = data.get("prompt", "What do you see in this image? Be concise.")

    if not image_base64:
        await websocket.send_json({"type": "error", "message": "No image data provided"})
        return

    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Invalid base64: {e}"})
        return

    _start = time.perf_counter()

    try:
        from google import genai
        client = genai.Client(api_key=(
            json.loads((Path(__file__).parent.parent / "config" / "api_keys.json").read_text()).get("gemini_api_key")
            if (Path(__file__).parent.parent / "config" / "api_keys.json").exists()
            else os.getenv("GEMINI_API_KEY", "")
        ))

        # Use streaming generation for real-time token delivery
        response = client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=[
                prompt,
                {"inline_data": {"mime_type": mime_type, "data": image_base64}},
            ],
        )

        full_text = ""
        for chunk in response:
            if chunk.text:
                token = chunk.text
                full_text += token
                await websocket.send_json({"type": "token", "text": token})

        elapsed = (time.perf_counter() - _start) * 1000
        logger.info(f"[Vision WS] Analysis complete in {elapsed:.0f}ms ({len(full_text)} chars)")

        # Log success to evolution tracker
        _log_evolution_failure("vision_analysis", {
            "duration_ms": round(elapsed, 1),
            "text_length": len(full_text),
            "mime_type": mime_type,
            "source": "websocket",
        })

        # Send completion signal
        await websocket.send_json({
            "type": "done",
            "text": full_text,
            "duration_ms": round(elapsed, 1),
        })

        # Optionally speak the result via TTS if requested
        if data.get("speak", False) and full_text.strip():
            try:
                from voice.speech import SpeechProcessor
                sp = SpeechProcessor()
                audio_bytes = await sp.synthesize(full_text)
                await websocket.send_json({
                    "type": "audio",
                    "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                    "sample_rate": 24000,
                })
            except Exception as tts_err:
                logger.warning(f"[Vision WS] TTS fallback failed: {tts_err}")

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"[Vision WS] Gemini error: {error_type}: {error_msg}")

        # Log to EvoMap evolution tracker
        _log_evolution_failure("vision_error", {
            "error_type": error_type,
            "error": error_msg[:200],
            "prompt": prompt[:80],
        })

        # Send user-friendly error
        if "API_KEY_INVALID" in error_msg or "API key" in error_msg or "not found" in error_msg:
            msg = "Invalid or expired Gemini API key. Please check your key in config/api_keys.json."
        elif "RATE_LIMIT" in error_msg or "rate_limit" in error_msg:
            msg = "Gemini rate limit reached. Please wait a moment and try again."
        elif "SAFETY" in error_msg or "safety" in error_msg:
            msg = "Analysis blocked by content safety filters. Try rephrasing your prompt."
        else:
            msg = f"Analysis failed: {error_msg[:120]}"

        await websocket.send_json({"type": "error", "message": msg})
