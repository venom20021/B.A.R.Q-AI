"""
Function executor for Deepgram Voice Agent desktop control.

Maps function names from Deepgram's FunctionCallRequest frames to
local OS operations. All synchronous OS calls are wrapped in
asyncio.to_thread() to avoid blocking the voice audio stream.
"""

import asyncio
import os
import platform
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

# ─── Platform helpers ──────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


# ─── OS Operation Implementations (blocking — called via to_thread) ────

def _minimize_window(window_name: str | None = None) -> dict[str, Any]:
    """Minimize the active window or a named window."""
    if IS_WINDOWS:
        import pygetwindow as gw
        if window_name:
            wins = gw.getWindowsWithTitle(window_name)
            if wins:
                wins[0].minimize()
                return {"status": "success", "detail": f"Minimized '{window_name}'"}
            return {"status": "error", "detail": f"No window found with title '{window_name}'"}
        else:
            import ctypes
            user32 = ctypes.windll.user32
            user32.ShowWindow(user32.GetForegroundWindow(), 6)  # SW_MINIMIZE
            return {"status": "success", "detail": "Active window minimized"}
    elif IS_MACOS:
        if window_name:
            subprocess.run(["osascript", "-e",
                f'tell application "{window_name}" to set minimized of windows to true'],
                capture_output=True)
        else:
            subprocess.run(["osascript", "-e",
                'tell application "System Events" to keystroke "m" using command down'],
                capture_output=True)
        return {"status": "success", "detail": "Window minimized"}
    else:
        # Linux — use wmctrl
        if window_name:
            subprocess.run(["wmctrl", "-r", window_name, "-b", "add,hidden"],
                           capture_output=True)
        else:
            subprocess.run(["xdotool", "getactivewindow", "windowminimize"],
                           capture_output=True)
        return {"status": "success", "detail": "Window minimized"}


def _maximize_window(window_name: str | None = None) -> dict[str, Any]:
    """Maximize the active window or a named window."""
    if IS_WINDOWS:
        import pygetwindow as gw
        if window_name:
            wins = gw.getWindowsWithTitle(window_name)
            if wins:
                wins[0].maximize()
                return {"status": "success", "detail": f"Maximized '{window_name}'"}
            return {"status": "error", "detail": f"No window found with title '{window_name}'"}
        else:
            import ctypes
            user32 = ctypes.windll.user32
            user32.ShowWindow(user32.GetForegroundWindow(), 3)  # SW_MAXIMIZE
            return {"status": "success", "detail": "Active window maximized"}
    elif IS_MACOS:
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to keystroke "m" using {command down, option down}'],
            capture_output=True)
        return {"status": "success", "detail": "Window maximized"}
    else:
        if window_name:
            subprocess.run(["wmctrl", "-r", window_name, "-b", "remove,hidden"],
                           capture_output=True)
        subprocess.run(["xdotool", "getactivewindow", "windowmaximize"],
                       capture_output=True)
        return {"status": "success", "detail": "Window maximized"}


def _open_file(file_path: str) -> dict[str, Any]:
    """Open a file or application using the default OS handler."""
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        return {"status": "error", "detail": f"Path not found: {path}"}
    try:
        if IS_WINDOWS:
            os.startfile(str(path))
        elif IS_MACOS:
            subprocess.run(["open", str(path)], check=True)
        else:
            subprocess.run(["xdg-open", str(path)], check=True)
        return {"status": "success", "detail": f"Opened {path.name}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _launch_app(app_name_or_path: str) -> dict[str, Any]:
    """Launch an application by name or path."""
    try:
        if IS_WINDOWS:
            subprocess.Popen(["cmd", "/c", "start", "", app_name_or_path],
                             shell=False)
        elif IS_MACOS:
            subprocess.run(["open", "-a", app_name_or_path], check=True)
        else:
            subprocess.Popen([app_name_or_path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return {"status": "success", "detail": f"Launched {app_name_or_path}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _close_app(app_name: str) -> dict[str, Any]:
    """Close an application by name."""
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/f", "/im", f"{app_name}.exe"],
                           capture_output=True, timeout=5)
        elif IS_MACOS:
            subprocess.run(["pkill", "-f", app_name], capture_output=True, timeout=5)
        else:
            subprocess.run(["pkill", "-f", app_name], capture_output=True, timeout=5)
        return {"status": "success", "detail": f"Closed {app_name}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": f"Timed out closing {app_name}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _get_system_status() -> dict[str, Any]:
    """Get current system status (CPU, memory, disk)."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "status": "success",
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_used_gb": round(mem.used / (1024**3), 1),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / (1024**3), 1),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _list_files(directory: str, pattern: str = "*") -> dict[str, Any]:
    """List files in a directory with optional glob pattern."""
    path = Path(directory).expanduser().resolve()
    if not path.is_dir():
        return {"status": "error", "detail": f"Directory not found: {path}"}
    try:
        files = list(path.glob(pattern))
        entries = []
        for f in sorted(files):
            entries.append({
                "name": f.name,
                "is_dir": f.is_dir(),
                "size_bytes": f.stat().st_size if f.is_file() else 0,
            })
        return {
            "status": "success",
            "directory": str(path),
            "total": len(entries),
            "files": entries[:50],  # limit to first 50
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _run_shell_command(command: str) -> dict[str, Any]:
    """Run a shell command and return output. SAFE: uses shlex.split, no shell=True."""
    try:
        args = shlex.split(command)
        # Use errors='replace' to handle non-ASCII characters (weather symbols,
        # emoji, etc.) that can't be decoded with the system's cp1252 codec
        result = subprocess.run(
            args, capture_output=True, text=True,
            errors='replace', timeout=30
        )
        return {
            "status": "success",
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
            "return_code": result.returncode,
        }
    except FileNotFoundError:
        return {"status": "error", "detail": f"Command not found: {args[0] if args else command}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": "Command timed out (30s limit)"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _take_screenshot(file_path: str = "") -> dict[str, Any]:
    """Take a screenshot and save it to a file.

    Args:
        file_path: Optional path to save the screenshot. If empty, saves to a temp file.

    Returns:
        Dict with path to saved screenshot.
    """
    try:
        from PIL import ImageGrab

        save_path = file_path.strip() if file_path.strip() else ""
        if not save_path:
            timestamp = int(time.time())
            save_path = str(Path(tempfile.gettempdir()) / f"barq_screenshot_{timestamp}.png")
        else:
            save_path = str(Path(save_path).expanduser().resolve())

        # Ensure parent directory exists
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        # Grab the full screen
        screenshot = ImageGrab.grab(all_screens=True)
        screenshot.save(save_path, "PNG")

        width, height = screenshot.size
        return {
            "status": "success",
            "file_path": save_path,
            "width": width,
            "height": height,
            "detail": f"Screenshot saved to {save_path} ({width}x{height})",
        }
    except ImportError:
        return {"status": "error", "detail": "Pillow (PIL) is not installed. Install with: pip install Pillow"}
    except Exception as e:
        return {"status": "error", "detail": f"Screenshot failed: {e}"}


def _clipboard_op(action: str = "read", text: str = "") -> dict[str, Any]:
    """Read from or write to the system clipboard.

    Args:
        action: "read" to get clipboard contents, "write" to set clipboard contents.
        text: Text to write to clipboard (only used when action="write").

    Returns:
        Dict with clipboard content (on read) or confirmation (on write).
    """
    try:
        import pyperclip

        if action == "write":
            if not text:
                return {"status": "error", "detail": "No text provided for clipboard write"}
            pyperclip.copy(text)
            return {"status": "success", "detail": f"Copied '{text[:50]}{'...' if len(text) > 50 else ''}' to clipboard"}

        # Default: read clipboard
        content = pyperclip.paste()
        truncated = len(content) > 1000
        return {
            "status": "success",
            "action": "read",
            "content": content[:1000] if truncated else content,
            "truncated": truncated,
            "length": len(content),
            "detail": f"Clipboard contains {len(content)} characters" if content else "Clipboard is empty",
        }
    except ImportError:
        return {"status": "error", "detail": "pyperclip is not installed. Install with: pip install pyperclip"}
    except Exception as e:
        return {"status": "error", "detail": f"Clipboard operation failed: {e}"}


def _focus_window(window_name: str) -> dict[str, Any]:
    """Bring a specific window to the foreground / give it focus.

    Args:
        window_name: Name or title substring of the window to focus.

    Returns:
        Dict with focus result.
    """
    if not window_name:
        return {"status": "error", "detail": "window_name is required"}

    if IS_WINDOWS:
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(window_name)
            if not wins:
                return {"status": "error", "detail": f"No window found with title containing '{window_name}'"}
            wins[0].activate()
            return {"status": "success", "detail": f"Focused '{window_name}'"}
        except ImportError:
            # Fallback: use ctypes to enumerate windows
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # Find window by title using FindWindowW
                handle = user32.FindWindowW(None, window_name)
                if handle:
                    user32.SetForegroundWindow(handle)
                    return {"status": "success", "detail": f"Focused '{window_name}'"}
                else:
                    return {"status": "error", "detail": f"No window found with title '{window_name}'"}
            except Exception as e2:
                return {"status": "error", "detail": f"Focus window failed: {e2}"}
        except Exception as e:
            return {"status": "error", "detail": f"Focus window failed: {e}"}
    elif IS_MACOS:
        try:
            subprocess.run(["osascript", "-e",
                f'tell application "{window_name}" to activate'],
                capture_output=True, timeout=5, check=False)
            return {"status": "success", "detail": f"Focused '{window_name}'"}
        except Exception as e:
            return {"status": "error", "detail": f"Focus window failed: {e}"}
    else:
        # Linux — use wmctrl
        try:
            result = subprocess.run(["wmctrl", "-a", window_name],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return {"status": "success", "detail": f"Focused '{window_name}'"}
            else:
                return {"status": "error", "detail": f"Window not found: {result.stderr.strip()}"}
        except FileNotFoundError:
            return {"status": "error", "detail": "wmctrl not installed. Install with: apt install wmctrl"}
        except Exception as e:
            return {"status": "error", "detail": f"Focus window failed: {e}"}


def _set_app_volume(app_name: str = "", level: int = 50) -> dict[str, Any]:
    """Set the volume level for a specific application or the system master volume.

    Args:
        app_name: Name of the application. If empty, sets master/system volume.
        level: Volume level from 0 (mute) to 100 (max). Default 50.

    Returns:
        Dict with volume change result.
    """
    # Clamp level to 0-100
    level = max(0, min(100, level))

    if IS_WINDOWS:
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

            if app_name:
                # Get all audio sessions and find the matching app
                sessions = AudioUtilities.GetAllSessions()
                for session in sessions:
                    if session.Process and session.Process.name().lower() == app_name.lower():
                        session.SimpleAudioVolume.SetMasterVolume(level / 100.0, None)
                        return {"status": "success", "detail": f"Set '{app_name}' volume to {level}%"}
                return {"status": "error", "detail": f"No audio session found for '{app_name}'"}
            else:
                # Set master volume
                volume.SetMasterVolumeLevelScalar(level / 100.0, None)
                return {"status": "success", "detail": f"Master volume set to {level}%"}

        except ImportError:
            # Fallback: use powershell
            if app_name:
                # Per-app volume via powershell requires more complex handling
                return {"status": "error", "detail": "Per-app volume control requires pycaw. Install: pip install pycaw"}
            else:
                subprocess.run([
                    "powershell", "-c",
                    "(New-Object -ComObject WScript.Shell).SendKeys([char]174)"
                ], capture_output=True, timeout=5)
                return {"status": "success", "detail": "Master volume set approximately"}
        except Exception as e:
            return {"status": "error", "detail": f"Volume control failed: {e}"}

    elif IS_MACOS:
        try:
            # macOS uses 0-100 range for volume
            subprocess.run(["osascript", "-e",
                f'set volume output volume {level}'],
                capture_output=True, timeout=5)
            return {"status": "success", "detail": f"Volume set to {level}%"}
        except Exception as e:
            return {"status": "error", "detail": f"Volume control failed: {e}"}
    else:
        # Linux — use amixer or pactl
        try:
            # Convert 0-100 to 0-65535 for amixer
            amixer_level = int(level / 100 * 65535)
            subprocess.run(["amixer", "sset", "Master", f"{amixer_level}"],
                           capture_output=True, timeout=5)
            return {"status": "success", "detail": f"Volume set to {level}%"}
        except FileNotFoundError:
            try:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                               capture_output=True, timeout=5)
                return {"status": "success", "detail": f"Volume set to {level}%"}
            except Exception as e2:
                return {"status": "error", "detail": f"Volume control failed: {e2}"}
        except Exception as e:
            return {"status": "error", "detail": f"Volume control failed: {e}"}


def _mute_volume(mute: bool = True) -> dict[str, Any]:
    """Mute or unmute the system volume.

    Args:
        mute: True to mute, False to unmute.

    Returns:
        Dict with mute result.
    """
    if IS_WINDOWS:
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

            volume.SetMute(1 if mute else 0, None)
            state = "muted" if mute else "unmuted"
            return {"status": "success", "detail": f"System volume {state}"}

        except ImportError:
            # Fallback: VK_VOLUME_MUTE virtual key
            import ctypes
            user32 = ctypes.windll.user32
            # Simulate mute key press
            VK_VOLUME_MUTE = 0xAD
            user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)  # Key down
            user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)  # Key up
            return {"status": "success", "detail": "Volume toggled mute"}
        except Exception as e:
            return {"status": "error", "detail": f"Mute failed: {e}"}
    elif IS_MACOS:
        try:
            muted_str = "true" if mute else "false"
            subprocess.run(["osascript", "-e",
                f'set volume output muted {muted_str}'],
                capture_output=True, timeout=5)
            state = "muted" if mute else "unmuted"
            return {"status": "success", "detail": f"System volume {state}"}
        except Exception as e:
            return {"status": "error", "detail": f"Mute failed: {e}"}
    else:
        # Linux — use amixer
        try:
            if mute:
                subprocess.run(["amixer", "sset", "Master", "mute"],
                               capture_output=True, timeout=5)
            else:
                subprocess.run(["amixer", "sset", "Master", "unmute"],
                               capture_output=True, timeout=5)
            state = "muted" if mute else "unmuted"
            return {"status": "success", "detail": f"System volume {state}"}
        except FileNotFoundError:
            try:
                if mute:
                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"],
                                   capture_output=True, timeout=5)
                else:
                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
                                   capture_output=True, timeout=5)
                state = "muted" if mute else "unmuted"
                return {"status": "success", "detail": f"System volume {state}"}
            except Exception as e2:
                return {"status": "error", "detail": f"Mute failed: {e2}"}
        except Exception as e:
            return {"status": "error", "detail": f"Mute failed: {e}"}


def _media_control(action: str = "play_pause") -> dict[str, Any]:
    """Control media playback (play/pause, next, previous).

    Args:
        action: One of "play_pause", "next", "previous".

    Returns:
        Dict with media control result.
    """
    valid_actions = {"play_pause", "next", "previous"}
    if action not in valid_actions:
        return {"status": "error", "detail": f"Invalid action '{action}'. Must be one of: {', '.join(sorted(valid_actions))}"}

    if IS_WINDOWS:
        import ctypes
        user32 = ctypes.windll.user32

        # Virtual key codes for media controls
        VK_MEDIA_PLAY_PAUSE = 0xB3
        VK_MEDIA_NEXT_TRACK = 0xB0
        VK_MEDIA_PREV_TRACK = 0xB1

        key_map = {
            "play_pause": VK_MEDIA_PLAY_PAUSE,
            "next": VK_MEDIA_NEXT_TRACK,
            "previous": VK_MEDIA_PREV_TRACK,
        }

        vk_code = key_map[action]
        user32.keybd_event(vk_code, 0, 0, 0)  # Key down
        user32.keybd_event(vk_code, 0, 2, 0)  # Key up

        action_labels = {
            "play_pause": "Play/Pause toggled",
            "next": "Next track",
            "previous": "Previous track",
        }
        return {"status": "success", "detail": action_labels[action]}

    elif IS_MACOS:
        # AppleScript keystroke uses key names, not numeric codes
        key_map = {
            "play_pause": ("space",),
            "next": ("right", "command"),
            "previous": ("left", "command"),
        }
        key, *mods = key_map[action]
        mods_clause = f" using {{{', '.join(mods)} down}}" if mods else ""
        subprocess.run(["osascript", "-e",
            f'tell application "System Events" to keystroke "{key}"{mods_clause}'],
            capture_output=True, timeout=5)
        return {"status": "success", "detail": f"Media: {action}"}

    else:
        # Linux — use playerctl (most media players support it)
        try:
            cmd_map = {
                "play_pause": "play-pause",
                "next": "next",
                "previous": "previous",
            }
            subprocess.run(["playerctl", cmd_map[action]],
                           capture_output=True, timeout=5)
            return {"status": "success", "detail": f"Media: {action}"}
        except FileNotFoundError:
            return {"status": "error", "detail": "playerctl not installed. Install with: apt install playerctl"}
        except Exception as e:
            return {"status": "error", "detail": f"Media control failed: {e}"}


def _empty_trash() -> dict[str, Any]:
    """Empty the system trash / recycle bin.

    Returns:
        Dict with trash result.
    """
    if IS_WINDOWS:
        try:
            # Use SHEmptyRecycleBinW via ctypes
            import ctypes
            shell32 = ctypes.windll.shell32
            # SHERB_NOCONFIRMATION = 0x1, SHERB_NOPROGRESSUI = 0x2, SHERB_NOSOUND = 0x4
            flags = 0x1 | 0x2 | 0x4  # No confirmation, no progress UI, no sound
            result = shell32.SHEmptyRecycleBinW(None, None, flags)
            if result == 0:  # S_OK
                return {"status": "success", "detail": "Recycle bin emptied"}
            else:
                return {"status": "error", "detail": f"Failed to empty recycle bin (code: {result})"}
        except Exception as e:
            return {"status": "error", "detail": f"Empty trash failed: {e}"}
    elif IS_MACOS:
        try:
            subprocess.run(["osascript", "-e",
                'tell application "Finder" to empty trash'],
                capture_output=True, timeout=30)
            return {"status": "success", "detail": "Trash emptied"}
        except Exception as e:
            return {"status": "error", "detail": f"Empty trash failed: {e}"}
    else:
        # Linux — trash-cli
        try:
            subprocess.run(["trash-empty"], capture_output=True, timeout=30)
            return {"status": "success", "detail": "Trash emptied"}
        except FileNotFoundError:
            return {"status": "error", "detail": "trash-cli not installed. Install with: apt install trash-cli"}
        except Exception as e:
            return {"status": "error", "detail": f"Empty trash failed: {e}"}


def _lock_screen() -> dict[str, Any]:
    """Lock the computer screen.

    Returns:
        Dict with lock screen result.
    """
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # LockWorkStation locks the screen
            result = user32.LockWorkStation()
            if result:
                return {"status": "success", "detail": "Screen locked"}
            else:
                return {"status": "error", "detail": "Failed to lock screen"}
        except Exception as e:
            return {"status": "error", "detail": f"Lock screen failed: {e}"}
    elif IS_MACOS:
        try:
            # Use the login window to lock the screen
            subprocess.run(["osascript", "-e",
                'tell application "System Events" to keystroke "q" using {command down, control down}'],
                capture_output=True, timeout=5)
            return {"status": "success", "detail": "Screen locked"}
        except Exception as e:
            return {"status": "error", "detail": f"Lock screen failed: {e}"}
    else:
        # Linux — use gnome-screensaver-command, xscreensaver, or loginctl
        try:
            # Try loginctl (systemd) first
            result = subprocess.run(["loginctl", "lock-session"],
                                    capture_output=True, timeout=5)
            if result.returncode == 0:
                return {"status": "success", "detail": "Screen locked"}
        except FileNotFoundError:
            pass

        try:
            subprocess.run(["gnome-screensaver-command", "-l"],
                           capture_output=True, timeout=5)
            return {"status": "success", "detail": "Screen locked"}
        except FileNotFoundError:
            pass

        try:
            subprocess.run(["xdg-screensaver", "lock"],
                           capture_output=True, timeout=5)
            return {"status": "success", "detail": "Screen locked"}
        except Exception:
            return {"status": "error", "detail": "Screen lock tools not found. Install: gnome-screensaver, xscreensaver, or xdg-utils"}


# ─── Function Registry ─────────────────────────────────────────────────

FUNCTION_REGISTRY: dict[str, Any] = {
    "minimize_window": _minimize_window,
    "maximize_window": _maximize_window,
    "open_file": _open_file,
    "launch_app": _launch_app,
    "close_app": _close_app,
    "get_system_status": _get_system_status,
    "list_files": _list_files,
    "run_shell_command": _run_shell_command,
    "take_screenshot": _take_screenshot,
    "clipboard": _clipboard_op,
    "focus_window": _focus_window,
    "set_app_volume": _set_app_volume,
    "mute_volume": _mute_volume,
    "media_control": _media_control,
    "empty_trash": _empty_trash,
    "lock_screen": _lock_screen,
}


def get_function_schemas() -> list[dict]:
    """Return the function schemas to inject into think.functions.

    These are the tool definitions sent in the Settings payload so Deepgram's
    Gemini Flash knows which local functions are available.
    """
    return [
        {
            "name": "minimize_window",
            "description": "Minimizes the currently active window or a target application window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_name": {
                        "type": "string",
                        "description": "Optional name of the specific window to minimize (e.g. 'Chrome', 'VS Code'). If omitted, minimizes active.",
                    },
                },
            },
        },
        {
            "name": "maximize_window",
            "description": "Maximizes the currently active window or a target application window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_name": {
                        "type": "string",
                        "description": "Optional name of the specific window to maximize.",
                    },
                },
            },
        },
        {
            "name": "open_file",
            "description": "Opens a local file or application using the default OS handler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The exact absolute path or relative file name to open.",
                    },
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "launch_app",
            "description": "Launches an application by name or path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name_or_path": {
                        "type": "string",
                        "description": "Name of the app to launch (e.g. 'notepad', 'code', '/usr/bin/firefox').",
                    },
                },
                "required": ["app_name_or_path"],
            },
        },
        {
            "name": "close_app",
            "description": "Closes an application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the application process to close (e.g. 'chrome', 'notepad').",
                    },
                },
                "required": ["app_name"],
            },
        },
        {
            "name": "get_system_status",
            "description": "Returns current system status including CPU, memory, and disk usage.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "list_files",
            "description": "Lists files in a directory with optional glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path to list files from.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern (e.g. '*.txt', '**/*.py'). Defaults to '*'.",
                    },
                },
                "required": ["directory"],
            },
        },
        {
            "name": "run_shell_command",
            "description": "Runs a shell command and returns its output. For quick terminal tasks like checking disk space, listing processes, or git status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute. Must be a single command (no pipes/shell features).",
                    },
                },
                "required": ["command"],
            },
        },
        {
            "name": "take_screenshot",
            "description": "Takes a screenshot of the entire screen and saves it to a file. Optionally specify a file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Optional path to save the screenshot. If omitted, saves to a temporary file with a timestamp.",
                    },
                },
            },
        },
        {
            "name": "clipboard",
            "description": "Reads from or writes to the system clipboard. Use action='read' to get clipboard contents, action='write' with 'text' to set clipboard contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write"],
                        "description": "'read' to get clipboard contents, 'write' to set clipboard contents.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to write to clipboard (required when action='write').",
                    },
                },
            },
        },
        {
            "name": "focus_window",
            "description": "Brings a specific application window to the foreground by name or title substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_name": {
                        "type": "string",
                        "description": "Name or title substring of the window to bring to front (e.g. 'Chrome', 'VS Code', 'Notepad').",
                    },
                },
                "required": ["window_name"],
            },
        },
        {
            "name": "set_app_volume",
            "description": "Sets the volume level for a specific application or the system master volume. Level ranges from 0 (mute) to 100 (max).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Optional name of the application (e.g. 'chrome.exe', 'spotify.exe'). If empty, sets the system master volume.",
                    },
                    "level": {
                        "type": "integer",
                        "description": "Volume level from 0 (mute) to 100 (max). Default 50.",
                    },
                },
            },
        },
        {
            "name": "mute_volume",
            "description": "Mutes or unmutes the system volume. Set mute=true to mute, mute=false to unmute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mute": {
                        "type": "boolean",
                        "description": "True to mute, False to unmute. Default is True.",
                    },
                },
            },
        },
        {
            "name": "media_control",
            "description": "Controls media playback: play/pause, next track, or previous track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play_pause", "next", "previous"],
                        "description": "Action to perform: 'play_pause', 'next', or 'previous'.",
                    },
                },
            },
        },
        {
            "name": "empty_trash",
            "description": "Empties the system trash/recycle bin.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "lock_screen",
            "description": "Locks the computer screen immediately.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    ]


async def execute_function(function_name: str, arguments: dict) -> dict[str, Any]:
    """Execute a function by name and return its result.

    All synchronous OS calls are wrapped in asyncio.to_thread() to
    prevent blocking the voice audio stream.

    Args:
        function_name: The name of the function to execute.
        arguments: Dict of keyword arguments to pass to the function.

    Returns:
        Dict with function execution result (always has 'status' key).
    """
    func = FUNCTION_REGISTRY.get(function_name)
    if not func:
        return {"status": "error", "detail": f"Unknown function: {function_name}"}

    try:
        # Run the blocking OS function in a thread pool
        result = await asyncio.to_thread(func, **arguments)
        return result
    except TypeError as e:
        return {"status": "error", "detail": f"Invalid arguments for {function_name}: {e}"}
    except Exception as e:
        return {"status": "error", "detail": f"Execution error: {e}"}
