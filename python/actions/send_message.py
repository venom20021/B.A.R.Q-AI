"""
Desktop-based messaging via PyAutoGUI automation.

Opens the native messaging app, searches for the contact/group,
pastes the message text, and presses Enter to send.

Supports: WhatsApp, Telegram, Signal, Discord, Messenger, Instagram, Slack

Requires:
    - pyautogui (desktop automation)
    - pyperclip (clipboard paste for long messages)
"""

import platform
import subprocess
import time
from typing import Any

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# ─── Helpers ───────────────────────────────────────────────────────────

def _has_pyautogui() -> bool:
    try:
        import pyautogui  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pyperclip() -> bool:
    try:
        import pyperclip  # noqa: F401
        return True
    except ImportError:
        return False


def _paste_text(text: str) -> None:
    """Paste text at the current cursor position using clipboard (faster) or keystrokes."""
    import pyautogui
    modifier = "command" if IS_MACOS else "ctrl"

    if _has_pyperclip():
        import pyperclip
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(modifier, "v")
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)


def _search_in_app(query: str) -> None:
    """Open the search/find function in the active app and type a query."""
    import pyautogui
    modifier = "command" if IS_MACOS else "ctrl"
    pyautogui.hotkey(modifier, "f")
    time.sleep(0.5)
    pyautogui.hotkey(modifier, "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(query)
    time.sleep(1.0)


def _open_app(app_name: str) -> bool:
    """Launch a desktop application by name."""
    import pyautogui

    try:
        if IS_WINDOWS:
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text(app_name)
            time.sleep(0.7)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True

        elif IS_MACOS:
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, timeout=10,
                )
            time.sleep(2.5)
            return result.returncode == 0

        else:
            # Linux — try a few launchers
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    time.sleep(2.5)
                    return True
                except FileNotFoundError:
                    continue
            return False

    except Exception as e:
        print(f"[SendMessage] Could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    """Open a URL in the default browser and wait for it to load."""
    import webbrowser
    try:
        webbrowser.open(url)
        time.sleep(4.0)
        return True
    except Exception as e:
        print(f"[SendMessage] Could not open browser: {e}")
        return False


def _desktop_send(app_name: str, receiver: str, message: str) -> dict[str, Any]:
    """Generic desktop-messaging flow: open app, search contact, paste message, send."""
    if not _has_pyautogui():
        return {
            "status": "error",
            "detail": "PyAutoGUI not installed. Install with: pip install pyautogui",
        }

    if not _open_app(app_name):
        return {"status": "error", "detail": f"Could not open {app_name}"}

    time.sleep(1.0)
    _search_in_app(receiver)
    import pyautogui
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    truncated = message[:50] + ("..." if len(message) > 50 else "")
    return {
        "status": "success",
        "detail": f"Message sent to {receiver} via {app_name}: \"{truncated}\"",
        "platform": app_name.lower(),
        "receiver": receiver,
        "message_length": len(message),
    }


def _send_whatsapp(receiver: str, message: str) -> dict[str, Any]:
    """Send a WhatsApp message via the desktop app."""
    if not _has_pyautogui():
        return {"status": "error", "detail": "PyAutoGUI not installed. Install with: pip install pyautogui"}
    import pyautogui

    if not _open_app("WhatsApp"):
        return {"status": "error", "detail": "Could not open WhatsApp"}

    time.sleep(1.0)
    _search_in_app(receiver)

    # WhatsApp search: select the first search result
    pyautogui.press("down")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    truncated = message[:50] + ("..." if len(message) > 50 else "")
    return {
        "status": "success",
        "detail": f"Message sent to {receiver} via WhatsApp: \"{truncated}\"",
        "platform": "whatsapp",
        "receiver": receiver,
    }


def _send_telegram(receiver: str, message: str) -> dict[str, Any]:
    """Send a Telegram message via the desktop app."""
    return _desktop_send("Telegram", receiver, message)


def _send_signal(receiver: str, message: str) -> dict[str, Any]:
    """Send a Signal message via the desktop app."""
    return _desktop_send("Signal", receiver, message)


def _send_discord(receiver: str, message: str) -> dict[str, Any]:
    """Send a Discord message via the desktop app."""
    if not _has_pyautogui():
        return {"status": "error", "detail": "PyAutoGUI not installed. Install with: pip install pyautogui"}
    import pyautogui

    if not _open_app("Discord"):
        return {"status": "error", "detail": "Could not open Discord"}

    time.sleep(1.0)

    # Discord: Ctrl+K to open quick switcher, then search contact/DM
    import pyautogui
    modifier = "command" if IS_MACOS else "ctrl"
    pyautogui.hotkey(modifier, "k")
    time.sleep(0.5)
    _paste_text(receiver)
    time.sleep(1.0)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    truncated = message[:50] + ("..." if len(message) > 50 else "")
    return {
        "status": "success",
        "detail": f"Message sent to {receiver} via Discord: \"{truncated}\"",
        "platform": "discord",
        "receiver": receiver,
    }


def _send_messenger(receiver: str, message: str) -> dict[str, Any]:
    """Send a Facebook Messenger message via the web interface."""
    if not _has_pyautogui():
        return {"status": "error", "detail": "PyAutoGUI not installed. Install with: pip install pyautogui"}

    if not _open_browser_url("https://www.messenger.com/"):
        return {"status": "error", "detail": "Could not open Messenger"}

    import pyautogui

    # Search for the contact
    _search_in_app(receiver)
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    truncated = message[:50] + ("..." if len(message) > 50 else "")
    return {
        "status": "success",
        "detail": f"Message sent to {receiver} via Messenger: \"{truncated}\"",
        "platform": "messenger",
        "receiver": receiver,
    }


def _send_instagram(receiver: str, message: str) -> dict[str, Any]:
    """Send an Instagram DM via the web interface."""
    if not _has_pyautogui():
        return {"status": "error", "detail": "PyAutoGUI not installed. Install with: pip install pyautogui"}
    import pyautogui

    if not _open_browser_url("https://www.instagram.com/direct/new/"):
        return {"status": "error", "detail": "Could not open Instagram"}

    import pyautogui

    # Type the receiver name
    _paste_text(receiver)
    time.sleep(1.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.4)

    # Tab to the message input
    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    truncated = message[:50] + ("..." if len(message) > 50 else "")
    return {
        "status": "success",
        "detail": f"Message sent to {receiver} via Instagram: \"{truncated}\"",
        "platform": "instagram",
        "receiver": receiver,
    }


def _send_slack(receiver: str, message: str) -> dict[str, Any]:
    """Send a Slack message via the desktop app."""
    if not _has_pyautogui():
        return {"status": "error", "detail": "PyAutoGUI not installed. Install with: pip install pyautogui"}
    import pyautogui

    if not _open_app("Slack"):
        return {"status": "error", "detail": "Could not open Slack"}

    time.sleep(1.0)

    # Slack: Ctrl+K to open quick switcher
    import pyautogui
    modifier = "command" if IS_MACOS else "ctrl"
    pyautogui.hotkey(modifier, "k")
    time.sleep(0.7)
    _paste_text(receiver)
    time.sleep(1.0)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    truncated = message[:50] + ("..." if len(message) > 50 else "")
    return {
        "status": "success",
        "detail": f"Message sent to {receiver} via Slack: \"{truncated}\"",
        "platform": "slack",
        "receiver": receiver,
    }


# ─── Platform Dispatch ─────────────────────────────────────────────────

_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"}, _send_whatsapp),
    ({"telegram", "tg"}, _send_telegram),
    ({"signal"}, _send_signal),
    ({"discord"}, _send_discord),
    ({"messenger", "facebook", "fb", "messen"}, _send_messenger),
    ({"instagram", "ig", "insta"}, _send_instagram),
    ({"slack"}, _send_slack),
]


def _resolve_platform(platform_str: str):
    """Find the handler for a given platform name (fuzzy match)."""
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    # Fallback: treat the platform name as the app name
    return lambda r, m: _desktop_send(platform_str.strip().title(), r, m)


# ─── Public API ────────────────────────────────────────────────────────

def send_message(
    platform: str = "whatsapp",
    receiver: str = "",
    message_text: str = "",
) -> dict[str, Any]:
    """Send a message to a contact via a messaging platform.

    Uses desktop automation (PyAutoGUI) to open the native messaging app,
    search for the contact, and send the message.

    Args:
        platform: Messaging platform name.
                  Supported: whatsapp, telegram, signal, discord, messenger,
                             instagram, slack (case-insensitive, fuzzy match).
        receiver: Contact name, phone number, or username to send to.
        message_text: The message content to send.

    Returns:
        Dict with status and detail.
    """
    if not receiver:
        return {"status": "error", "detail": "Please specify a recipient (name, phone, or username)."}

    if not message_text:
        return {"status": "error", "detail": "Please specify the message content."}

    if not _has_pyautogui():
        return {
            "status": "error",
            "detail": "PyAutoGUI is not installed. Desktop messaging requires PyAutoGUI. Install with: pip install pyautogui",
        }

    preview = message_text[:50] + ("..." if len(message_text) > 50 else "")
    print(f"[SendMessage] {platform} -> {receiver}: \"{preview}\"")

    try:
        handler = _resolve_platform(platform)
        result = handler(receiver, message_text)
        return result
    except Exception as e:
        return {"status": "error", "detail": f"Could not send message: {e}"}
