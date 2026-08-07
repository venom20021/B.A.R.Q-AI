"""
FastAPI routes for desktop automation: Screen OCR, Ghost Keyboard,
AI Wallpaper, and custom protocols/workflows.
"""

import asyncio
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import analytics_dao, settings_dao

router = APIRouter()


# ─── Models ───────────────────────────────────────────────────────────────────

class OCRRequest(BaseModel):
    region: Optional[list[int]] = None  # [x, y, width, height] or None for full screen

class KeyboardRequest(BaseModel):
    text: str
    action: str = "type"  # type, press_key, hotkey
    key: Optional[str] = None

class DesktopActionRequest(BaseModel):
    action: str
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"
    clicks: int = 1
    text: str = ""
    key: Optional[str] = None
    keys: Optional[list[str]] = None
    window_name: Optional[str] = None
    app_name: Optional[str] = None
    direction: str = "down"
    amount: int = 3
    duration: float = 0.3
    confirm: bool = False

class WallpaperRequest(BaseModel):
    description: str
    source: str = "auto"  # auto, pollinations, unsplash

class ProtocolRequest(BaseModel):
    name: str
    steps: list[dict]
    trigger_phrase: Optional[str] = None


# ─── Screen OCR (ScreenPeeler) ────────────────────────────────────────────────

@router.post("/ocr/capture")
async def capture_screen_ocr(request: OCRRequest):
    """Capture screen region and extract text using OCR."""
    try:
        # Take screenshot using mss
        import mss
        import mss.tools

        with mss.mss() as sct:
            if request.region:
                monitor = {"top": request.region[1], "left": request.region[0],
                           "width": request.region[2], "height": request.region[3]}
            else:
                monitor = sct.monitors[1]  # Primary monitor

            screenshot = sct.grab(monitor)
            screenshot_path = Path(os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "temp_screenshot.png"
            ))
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(screenshot_path))

        # OCR using pytesseract or easyocr
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(screenshot_path)
            text = pytesseract.image_to_string(image)

            await analytics_dao.log_activity(
                "desktop", "ocr", f"OCR extracted {len(text)} characters"
            )

            # Clean up temp file
            screenshot_path.unlink(missing_ok=True)

            return {
                "status": "success",
                "text": text.strip(),
                "char_count": len(text.strip()),
                "engine": "pytesseract",
                "region": request.region or "fullscreen",
            }
        except ImportError:
            # Try easyocr as fallback
            try:
                import easyocr

                reader = easyocr.Reader(["en"])
                results = reader.readtext(str(screenshot_path))
                text = " ".join([r[1] for r in results])

                await analytics_dao.log_activity(
                    "desktop", "ocr", f"OCR (easyocr) extracted {len(text)} characters"
                )

                screenshot_path.unlink(missing_ok=True)
                return {"status": "success", "text": text.strip(), "engine": "easyocr"}
            except ImportError:
                return {"status": "unavailable",
                        "message": "OCR libraries not installed. Run: pip install pytesseract pillow (or easyocr)"}

    except ImportError:
        return {"status": "unavailable", "message": "mss not installed. Run: pip install mss"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Ghost Keyboard ───────────────────────────────────────────────────────────

@router.post("/keyboard")
async def keyboard_control(request: KeyboardRequest):
    """Inject keyboard input."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True

        if request.action == "type":
            pyautogui.write(request.text, interval=0.01)
        elif request.action == "press_key":
            pyautogui.press(request.key or "enter")
        elif request.action == "hotkey":
            keys = request.text.split("+")
            pyautogui.hotkey(*[k.strip() for k in keys])

        await analytics_dao.log_activity(
            "desktop", "keyboard", f"Keyboard action: {request.action}"
        )
        return {"status": "executed", "action": request.action}
    except ImportError:
        return {"status": "unavailable", "message": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mouse")
async def mouse_control(action: str, x: Optional[int] = None, y: Optional[int] = None):
    """Control mouse: click, scroll, move."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True

        if action == "click":
            if x is not None and y is not None:
                pyautogui.click(x, y)
            else:
                pyautogui.click()
        elif action == "double_click":
            pyautogui.doubleClick(x, y)
        elif action == "scroll_down":
            pyautogui.scroll(-3)
        elif action == "scroll_up":
            pyautogui.scroll(3)
        elif action == "move":
            if x is not None and y is not None:
                pyautogui.moveTo(x, y, duration=0.3)

        return {"status": "executed", "action": action}
    except ImportError:
        return {"status": "unavailable", "message": "pyautogui not installed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Unified Desktop Action (agent + voice skill) ─────────────────────────────

# Safety tiers: which actions are destructive and therefore require confirm=true
_CONFIRM_REQUIRED_ACTIONS = {"close_app"}


@router.post("/action")
async def desktop_action(request: DesktopActionRequest):
    """Unified desktop control endpoint used by the agent's ``desktop_action`` skill.

    Dispatches to mouse / keyboard / window / app operations.  Destructive
    actions (e.g. ``close_app``) are gated behind ``confirm=true`` so an
    autonomous agent can never kill a process without an explicit go-ahead
    (mirrors the ``command_whitelist`` warn/dangerous approval flow).

    Actions:
        mouse_click    — click at (x, y) or current cursor (button, clicks)
        mouse_move     — move cursor to (x, y)
        mouse_scroll   — scroll up/down by amount
        keyboard_type  — type text at the focused field
        keyboard_press — press a key (enter, tab, escape, ...)
        keyboard_hotkey— press a combo (keys list e.g. ['ctrl', 'c'])
        focus_window   — bring a window (by title) to the foreground
        close_app      — close an app by name (requires confirm=true)
        screenshot     — save a screenshot to path
    """
    action = request.action

    # ── Safety gate (before any import so responses are deterministic) ──
    if action in _CONFIRM_REQUIRED_ACTIONS and not request.confirm:
        return {
            "status": "confirmation_required",
            "message": (
                f"'{action}' is a destructive desktop action and needs explicit approval. "
                "Re-send with confirm=true to allow it."
            ),
        }

    # ── Input validation (before importing pyautogui — a missing optional
    #    dependency must not turn a validation error into 'unavailable'.)
    _VALID_ACTIONS = {
        "mouse_click", "mouse_move", "mouse_scroll", "keyboard_type",
        "keyboard_press", "keyboard_hotkey", "focus_window", "close_app",
        "screenshot",
    }
    if action not in _VALID_ACTIONS:
        return {"status": "error", "message": f"Unknown desktop action: '{action}'"}

    if action == "mouse_move" and (request.x is None or request.y is None):
        return {"status": "error", "message": "mouse_move requires x and y coordinates"}
    if action == "keyboard_type" and not request.text:
        return {"status": "error", "message": "keyboard_type requires text"}
    if action == "keyboard_hotkey" and not request.keys:
        return {"status": "error", "message": "keyboard_hotkey requires a keys list e.g. ['ctrl', 'c']"}
    if action == "focus_window" and not request.window_name:
        return {"status": "error", "message": "focus_window requires window_name"}
    if action == "close_app" and not request.app_name:
        return {"status": "error", "message": "close_app requires app_name"}

    try:
        import pyautogui
        pyautogui.FAILSAFE = True

        if action == "mouse_click":
            if request.x is not None and request.y is not None:
                pyautogui.click(request.x, request.y, button=request.button, clicks=request.clicks)
            else:
                pyautogui.click(button=request.button, clicks=request.clicks)
            result = f"Clicked ({request.button}) at ({request.x or 'cursor'}, {request.y or 'cursor'})"

        elif action == "mouse_move":
            pyautogui.moveTo(request.x, request.y, duration=request.duration)
            result = f"Mouse moved to ({request.x}, {request.y})"

        elif action == "mouse_scroll":
            amount = abs(request.amount) * (-1 if request.direction == "down" else 1)
            pyautogui.scroll(amount)
            result = f"Scrolled {request.direction} by {request.amount}"

        elif action == "keyboard_type":
            pyautogui.write(request.text, interval=0.02)
            result = f"Typed {len(request.text)} characters"

        elif action == "keyboard_press":
            pyautogui.press(request.key or "enter")
            result = f"Pressed key '{request.key or 'enter'}'"

        elif action == "keyboard_hotkey":
            pyautogui.hotkey(*[k.strip() for k in request.keys])
            result = f"Pressed hotkey {'+'.join(request.keys)}"

        elif action == "focus_window":
            try:
                import pygetwindow as gw
                wins = gw.getWindowsWithTitle(request.window_name)
                if not wins:
                    return {"status": "error", "message": f"No window found with title containing '{request.window_name}'"}
                wins[0].activate()
                result = f"Focused window '{request.window_name}'"
            except ImportError:
                return {"status": "unavailable", "message": "pygetwindow not installed. Run: pip install pygetwindow"}

        elif action == "close_app":
            if platform.system().lower() == "windows":
                subprocess.run(["taskkill", "/f", "/im", f"{request.app_name}.exe"],
                               capture_output=True, timeout=5)
            else:
                subprocess.run(["pkill", "-f", request.app_name], capture_output=True, timeout=5)
            result = f"Closed app '{request.app_name}'"

        elif action == "screenshot":
            path = request.text or str(Path.home() / "Desktop" / "barq_desktop_screenshot.png")
            try:
                img = pyautogui.screenshot()
                img.save(path)
                result = f"Screenshot saved to {path}"
            except ImportError:
                return {"status": "unavailable", "message": "Pillow not installed. Run: pip install pillow"}

        await analytics_dao.log_activity(
            "desktop", f"action:{action}", result
        )
        return {"status": "executed", "message": result}
    except ImportError:
        return {"status": "unavailable", "message": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── AI Wallpaper Engine ──────────────────────────────────────────────────────

@router.post("/wallpaper/set")
async def set_wallpaper(request: WallpaperRequest):
    """Change desktop wallpaper to an AI-generated or searched image."""
    try:
        import httpx

        if request.source == "pollinations":
            # Generate using Pollinations.ai
            encoded = request.description.replace(" ", "%20")
            image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1080"
        else:
            # Search Unsplash for matching image
            # Free tier, no key needed for basic searches
            async with httpx.AsyncClient() as client:
                search_resp = await client.get(
                    "https://api.unsplash.com/search/photos",
                    params={
                        "query": request.description,
                        "per_page": 1,
                        "orientation": "landscape",
                    },
                    headers={"Accept-Version": "v1"},
                )
                search_data = search_resp.json()
                if search_data.get("results"):
                    image_url = search_data["results"][0]["urls"]["full"]
                else:
                    image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1080"

        system = platform.system().lower()

        # Download image
        async with httpx.AsyncClient() as client:
            img_resp = await client.get(image_url)
            wallpaper_dir = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "wallpapers"))
            wallpaper_dir.mkdir(exist_ok=True)
            wallpaper_path = wallpaper_dir / f"wallpaper_{int(asyncio.get_running_loop().time())}.jpg"
            wallpaper_path.write_bytes(img_resp.content)

            # Set wallpaper
            if "windows" in system:
                import ctypes
                ctypes.windll.user32.SystemParametersInfoW(20, 0, str(wallpaper_path), 0)
            elif "darwin" in system:
                subprocess.run([
                    "osascript", "-e",
                    f'tell application "Finder" to set desktop picture to POSIX file "{wallpaper_path}"'
                ])
            else:
                # Linux: try gsettings
                subprocess.run([
                    "gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri", f"file://{wallpaper_path}"
                ], capture_output=True)

        await analytics_dao.log_activity(
            "desktop", "wallpaper", f"Set wallpaper: {request.description[:50]}"
        )
        return {
            "status": "set",
            "description": request.description,
            "image_url": image_url,
            "file_path": str(wallpaper_path),
        }
    except ImportError:
        return {"status": "unavailable", "message": "httpx not installed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Custom Protocols (Workflows) ─────────────────────────────────────────────

@router.post("/protocols/create")
async def create_protocol(request: ProtocolRequest):
    """Create a custom protocol/workflow."""
    try:
        protocol = {
            "name": request.name,
            "trigger_phrase": request.trigger_phrase or request.name.lower(),
            "steps": request.steps,
            "enabled": True,
            "created_at": str(datetime_now()),
        }

        await settings_dao.set_setting(
            f"protocol_{request.name}",
            json.dumps(protocol),
            category="workflow"
        )

        await analytics_dao.log_activity(
            "desktop", "create_protocol", f"Created protocol: {request.name}"
        )
        return {"status": "created", "protocol": protocol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/protocols")
async def list_protocols():
    """List all saved protocols/workflows."""
    try:
        protocols = await settings_dao.get_settings_by_category("workflow")
        result = []
        for p in protocols:
            try:
                data = json.loads(p["value"])
                result.append(data)
            except (json.JSONDecodeError, KeyError):
                continue
        return {"protocols": result, "count": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/protocols/activate/{name}")
async def activate_protocol(name: str):
    """Activate/run a protocol by name."""
    try:
        data = await settings_dao.get_setting(f"protocol_{name}")
        if not data:
            raise HTTPException(status_code=404, detail=f"Protocol not found: {name}")

        # get_setting returns the value string directly (not a dict)
        protocol = json.loads(data)
        steps = protocol.get("steps", [])

        results = []
        for step in steps:
            action = step.get("action", "")
            target = step.get("target", "")

            try:
                if action == "open_app":
                    import subprocess
                    subprocess.Popen([target], shell=True)
                    results.append({"step": action, "target": target, "status": "executed"})

                elif action == "window_snap":
                    side = step.get("side", "left")
                    try:
                        import pygetwindow as gw
                        active = gw.getActiveWindow()
                        if active:
                            screen_w = 1920
                            screen_h = 1080
                            if side == "left":
                                active.resizeTo(screen_w // 2, screen_h)
                                active.moveTo(0, 0)
                            else:
                                active.resizeTo(screen_w // 2, screen_h)
                                active.moveTo(screen_w // 2, 0)
                        results.append({"step": action, "side": side, "status": "executed"})
                    except ImportError:
                        results.append({"step": action, "side": side, "status": "unavailable", "error": "pygetwindow not installed"})

                elif action == "set_wallpaper":
                    theme = step.get("theme", "dark")
                    # Trigger wallpaper change via our own endpoint
                    import httpx
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://127.0.0.1:8970/desktop/wallpaper/set",
                            json={"description": f"{theme} aesthetic wallpaper", "source": "unsplash"},
                            timeout=10,
                        )
                    results.append({"step": action, "theme": theme, "status": "executed"})

                elif action == "open_url":
                    import webbrowser
                    webbrowser.open(target)
                    results.append({"step": action, "target": target, "status": "executed"})

                elif action == "wait":
                    await asyncio.sleep(int(target))
                    results.append({"step": action, "duration": target, "status": "executed"})

                else:
                    results.append({"step": action, "status": "unknown_action"})

            except Exception as step_err:
                results.append({"step": action, "status": "error", "error": str(step_err)})

        await analytics_dao.log_activity(
            "desktop", "activate_protocol", f"Activated protocol: {name} ({len(steps)} steps)"
        )
        return {"status": "completed", "protocol": name, "steps_completed": len(steps), "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/protocols/{name}")
async def delete_protocol(name: str):
    """Delete a protocol by name."""
    try:
        await settings_dao.delete_setting(f"protocol_{name}")
        return {"status": "deleted", "protocol": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helper ───────────────────────────────────────────────────────────────────

def datetime_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
