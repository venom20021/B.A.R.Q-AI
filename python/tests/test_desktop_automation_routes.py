"""
Tests for desktop_automation FastAPI routes: OCR, keyboard, mouse, wallpaper, protocols.

Deterministic by design: every OS-level dependency (``pyautogui``,
``pygetwindow``, ``mss``, ``httpx``, ``webbrowser``) is mocked at fixture
level, so NO test moves the real mouse, types real keystrokes, takes a real
screenshot, opens a browser, or hits the network.  This keeps the suite fast
(<2s) and safe to run on any machine — with or without the optional deps
installed.

Fast invocation (scoped to this file so pytest doesn't collect the whole
suite — bare `pytest -k desktop` also matches tests in other files):

    pytest tests/test_desktop_automation_routes.py -k desktop --tb=short -q
"""

import builtins
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def router():
    from desktop_automation import routes
    return routes.router


# ─── Mock helpers ─────────────────────────────────────────────────────────────

def _block_import(monkeypatch, name: str):
    """Simulate ``name`` not being installed: any ``import name`` raises ImportError.

    The route modules do ``import pyautogui`` / ``import mss`` / ... *inside*
    the endpoint function, so patching ``builtins.__import__`` + removing the
    module from ``sys.modules`` is what actually forces the ImportError path.
    """
    monkeypatch.delitem(sys.modules, name, raising=False)
    real_import = builtins.__import__

    def _fake_import(mod_name, *args, **kwargs):
        if mod_name == name or mod_name.startswith(name + "."):
            raise ImportError(f"No module named '{name}'")
        return real_import(mod_name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


@pytest.fixture
def mock_pyautogui(monkeypatch):
    """Replace the ``pyautogui`` module so routes call a mock, never the OS."""
    fake = MagicMock()
    fake.FAILSAFE = True
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    return fake


@pytest.fixture
def missing_pyautogui(monkeypatch):
    """Simulate pyautogui not being installed (ImportError on import)."""
    _block_import(monkeypatch, "pyautogui")


@pytest.fixture
def mock_pygetwindow(monkeypatch):
    """Fake ``pygetwindow`` with one matching window so focus_window succeeds."""
    fake = MagicMock()
    fake.getWindowsWithTitle.return_value = [MagicMock()]
    monkeypatch.setitem(sys.modules, "pygetwindow", fake)
    return fake


@pytest.fixture
def missing_mss(monkeypatch):
    """Simulate mss not being installed so OCR returns unavailable."""
    _block_import(monkeypatch, "mss")


@pytest.fixture
def missing_httpx(monkeypatch):
    """Simulate httpx not being installed so wallpaper returns unavailable."""
    _block_import(monkeypatch, "httpx")


@pytest.fixture
def mock_webbrowser(monkeypatch):
    """Fake ``webbrowser`` so protocol activation never opens a real browser."""
    fake = MagicMock()
    monkeypatch.setitem(sys.modules, "webbrowser", fake)
    return fake


# ─── Screen OCR ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocr_capture_unavailable(client, missing_mss):
    """POST /ocr/capture returns unavailable when mss is not installed."""
    response = await client.post("/ocr/capture", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert "mss" in data["message"].lower()


@pytest.mark.asyncio
async def test_ocr_capture_with_region_unavailable(client, missing_mss):
    """POST /ocr/capture with region also returns unavailable without mss."""
    response = await client.post("/ocr/capture", json={"region": [0, 0, 100, 100]})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"


# ─── Legacy Keyboard endpoint ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_keyboard_type_calls_pyautogui(client, mock_pyautogui):
    """POST /keyboard type action writes through mocked pyautogui."""
    response = await client.post("/keyboard", json={"text": "Hello", "action": "type"})
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.write.assert_called_once_with("Hello", interval=0.01)


@pytest.mark.asyncio
async def test_keyboard_press_key(client, mock_pyautogui):
    """POST /keyboard press_key presses through mocked pyautogui."""
    response = await client.post(
        "/keyboard", json={"text": "", "action": "press_key", "key": "enter"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.press.assert_called_once_with("enter")


@pytest.mark.asyncio
async def test_keyboard_hotkey(client, mock_pyautogui):
    """POST /keyboard hotkey fires the combo through mocked pyautogui."""
    response = await client.post("/keyboard", json={"text": "ctrl+c", "action": "hotkey"})
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")


# ─── Legacy Mouse endpoint ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mouse_click_calls_pyautogui(client, mock_pyautogui):
    """POST /mouse click action clicks through mocked pyautogui."""
    response = await client.post("/mouse?action=click&x=100&y=200")
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.click.assert_called_once_with(100, 200)


@pytest.mark.asyncio
async def test_mouse_scroll(client, mock_pyautogui):
    """POST /mouse scroll action scrolls through mocked pyautogui."""
    response = await client.post("/mouse?action=scroll_down")
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.scroll.assert_called_once_with(-3)


@pytest.mark.asyncio
async def test_mouse_move(client, mock_pyautogui):
    """POST /mouse move action moves through mocked pyautogui."""
    response = await client.post("/mouse?action=move&x=500&y=500")
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.moveTo.assert_called_once_with(500, 500, duration=0.3)


# ─── Unified Desktop Action ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_desktop_action_unknown(client, missing_pyautogui):
    """Unknown action returns 'error' BEFORE any pyautogui import attempt."""
    response = await client.post("/action", json={"action": "fly_to_the_moon"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "unknown" in data["message"].lower()


@pytest.mark.asyncio
async def test_desktop_action_close_app_requires_confirm(client, missing_pyautogui):
    """close_app without confirm=true is blocked by the safety gate, no OS call."""
    response = await client.post(
        "/action", json={"action": "close_app", "app_name": "notepad"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmation_required"
    assert "confirm=true" in data["message"]


@pytest.mark.asyncio
async def test_desktop_action_mouse_move_requires_coords(client, missing_pyautogui):
    """Validation error happens before any pyautogui import/call."""
    response = await client.post("/action", json={"action": "mouse_move"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "x and y" in data["message"]


@pytest.mark.asyncio
async def test_desktop_action_hotkey_requires_keys(client, missing_pyautogui):
    """keyboard_hotkey without keys is a validation error, not unavailable."""
    response = await client.post("/action", json={"action": "keyboard_hotkey"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "keys" in data["message"]


@pytest.mark.asyncio
async def test_desktop_action_pyautogui_missing_returns_unavailable(client, missing_pyautogui):
    """Valid action with pyautogui absent → 'unavailable', never an OS call."""
    response = await client.post(
        "/action", json={"action": "mouse_move", "x": 100, "y": 200}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert "pyautogui" in data["message"].lower()


@pytest.mark.asyncio
async def test_desktop_action_mouse_click_calls_pyautogui(client, mock_pyautogui):
    """Valid mouse_click calls mocked pyautogui.click with the right args."""
    response = await client.post(
        "/action", json={"action": "mouse_click", "x": 100, "y": 200, "button": "left"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "executed"
    mock_pyautogui.click.assert_called_once_with(100, 200, button="left", clicks=1)


@pytest.mark.asyncio
async def test_desktop_action_mouse_click_at_cursor(client, mock_pyautogui):
    """mouse_click without coordinates clicks at the current cursor."""
    response = await client.post(
        "/action", json={"action": "mouse_click", "button": "right", "clicks": 2}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.click.assert_called_once_with(button="right", clicks=2)


@pytest.mark.asyncio
async def test_desktop_action_mouse_move_calls_pyautogui(client, mock_pyautogui):
    """Valid mouse_move calls mocked pyautogui.moveTo with the right args."""
    response = await client.post(
        "/action", json={"action": "mouse_move", "x": 100, "y": 200}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "executed"
    mock_pyautogui.moveTo.assert_called_once_with(100, 200, duration=0.3)


@pytest.mark.asyncio
async def test_desktop_action_mouse_scroll_calls_pyautogui(client, mock_pyautogui):
    """mouse_scroll down calls mocked pyautogui.scroll with a negative amount."""
    response = await client.post(
        "/action", json={"action": "mouse_scroll", "direction": "down", "amount": 3}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.scroll.assert_called_once_with(-3)


@pytest.mark.asyncio
async def test_desktop_action_keyboard_type_calls_pyautogui(client, mock_pyautogui):
    """keyboard_type calls mocked pyautogui.write with the text."""
    response = await client.post(
        "/action", json={"action": "keyboard_type", "text": "hello world"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.write.assert_called_once_with("hello world", interval=0.02)


@pytest.mark.asyncio
async def test_desktop_action_keyboard_press_calls_pyautogui(client, mock_pyautogui):
    """keyboard_press calls mocked pyautogui.press with the key."""
    response = await client.post("/action", json={"action": "keyboard_press", "key": "enter"})
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.press.assert_called_once_with("enter")


@pytest.mark.asyncio
async def test_desktop_action_keyboard_hotkey_calls_pyautogui(client, mock_pyautogui):
    """keyboard_hotkey calls mocked pyautogui.hotkey with stripped keys."""
    response = await client.post(
        "/action", json={"action": "keyboard_hotkey", "keys": ["ctrl", " c "]}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")


@pytest.mark.asyncio
async def test_desktop_action_focus_window(client, mock_pyautogui, mock_pygetwindow):
    """focus_window activates the mocked window, no real window manager call."""
    response = await client.post(
        "/action", json={"action": "focus_window", "window_name": "notepad"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pygetwindow.getWindowsWithTitle.assert_called_once_with("notepad")


@pytest.mark.asyncio
async def test_desktop_action_close_app_with_confirm(client, mock_pyautogui, monkeypatch):
    """close_app with confirm=true calls subprocess.run (mocked, never a real kill)."""
    from desktop_automation import routes

    fake_run = MagicMock()
    monkeypatch.setattr(routes.subprocess, "run", fake_run)

    response = await client.post(
        "/action", json={"action": "close_app", "app_name": "notepad", "confirm": True}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    assert fake_run.called


@pytest.mark.asyncio
async def test_desktop_action_screenshot_calls_pyautogui(client, mock_pyautogui):
    """screenshot saves through mocked pyautogui.screenshot, no display grab."""
    response = await client.post(
        "/action", json={"action": "screenshot", "text": "/tmp/barq_test_shot.png"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
    mock_pyautogui.screenshot.assert_called_once()


# ─── Wallpaper ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wallpaper_set_unavailable(client, missing_httpx):
    """POST /wallpaper/set returns unavailable when httpx is missing (no network)."""
    response = await client.post(
        "/wallpaper/set", json={"description": "sunset mountains", "source": "auto"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert "httpx" in data["message"].lower()


# ─── Protocols ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_protocol(client):
    """POST /protocols/create should create a new protocol."""
    response = await client.post(
        "/protocols/create",
        json={
            "name": "dev_setup",
            "steps": [
                {"action": "open_app", "target": "vscode"},
                {"action": "open_url", "target": "https://github.com"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["protocol"]["name"] == "dev_setup"
    assert len(data["protocol"]["steps"]) == 2


@pytest.mark.asyncio
async def test_list_protocols(client):
    """GET /protocols should list saved protocols."""
    await client.post(
        "/protocols/create",
        json={"name": "my_workflow", "steps": [{"action": "open_app", "target": "notepad"}]},
    )

    response = await client.get("/protocols")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    names = [p["name"] for p in data["protocols"]]
    assert "my_workflow" in names


@pytest.mark.asyncio
async def test_activate_protocol_not_found(client):
    """POST /protocols/activate/{name} with non-existent name returns 404."""
    response = await client.post("/protocols/activate/nonexistent_protocol")
    assert response.status_code == 404
    assert "Protocol not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_activate_protocol_success(client, mock_webbrowser):
    """Activating a protocol executes steps without launching a real browser."""
    await client.post(
        "/protocols/create",
        json={
            "name": "quick_test",
            "steps": [
                {"action": "open_url", "target": "https://example.com"},
                {"action": "wait", "target": "0"},
            ],
        },
    )

    response = await client.post("/protocols/activate/quick_test")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["steps_completed"] == 2
    assert len(data["results"]) == 2
    mock_webbrowser.open.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
async def test_delete_protocol(client):
    """DELETE /protocols/{name} should delete a protocol."""
    await client.post(
        "/protocols/create",
        json={"name": "temp_protocol", "steps": [{"action": "open_app", "target": "calc"}]},
    )

    response = await client.delete("/protocols/temp_protocol")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    list_resp = await client.get("/protocols")
    names = [p["name"] for p in list_resp.json()["protocols"]]
    assert "temp_protocol" not in names
