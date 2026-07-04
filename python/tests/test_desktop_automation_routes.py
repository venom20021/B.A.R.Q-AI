"""
Tests for desktop_automation FastAPI routes: OCR, keyboard, mouse, wallpaper, protocols.
Most hardware-dependent endpoints return 'unavailable' since optional deps aren't installed.
"""

import pytest


@pytest.fixture
def router():
    from desktop_automation import routes
    return routes.router


# ─── OCR ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocr_capture_unavailable(client):
    """POST /ocr/capture should return unavailable when OCR libs not installed."""
    response = await client.post("/ocr/capture", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    # Message mentions either mss or OCR libraries depending on which import fails first
    assert "mss" in data["message"].lower() or "ocr" in data["message"].lower()


@pytest.mark.asyncio
async def test_ocr_capture_with_region(client):
    """POST /ocr/capture with region should also return unavailable."""
    response = await client.post("/ocr/capture", json={"region": [0, 0, 100, 100]})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable" or data["status"] == "success"


# ─── Keyboard ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_keyboard_type_unavailable(client):
    """POST /keyboard should execute or return available message."""
    response = await client.post(
        "/keyboard",
        json={"text": "Hello", "action": "type"},
    )
    assert response.status_code == 200
    data = response.json()
    # pyautogui may or may not be installed
    assert data["status"] in ("executed", "unavailable")


@pytest.mark.asyncio
async def test_keyboard_press_key(client):
    """POST /keyboard with press_key action."""
    response = await client.post(
        "/keyboard",
        json={"text": "", "action": "press_key", "key": "enter"},
    )
    assert response.status_code == 200
    assert response.json()["status"] in ("executed", "unavailable")


@pytest.mark.asyncio
async def test_keyboard_hotkey(client):
    """POST /keyboard with hotkey action."""
    response = await client.post(
        "/keyboard",
        json={"text": "ctrl+c", "action": "hotkey"},
    )
    assert response.status_code == 200
    assert response.json()["status"] in ("executed", "unavailable")


# ─── Mouse ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mouse_click_unavailable(client):
    """POST /mouse should execute or return unavailable."""
    response = await client.post("/mouse?action=click&x=100&y=200")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("executed", "unavailable")


@pytest.mark.asyncio
async def test_mouse_scroll(client):
    """POST /mouse with scroll action."""
    response = await client.post("/mouse?action=scroll_down")
    assert response.status_code == 200
    assert response.json()["status"] in ("executed", "unavailable")


@pytest.mark.asyncio
async def test_mouse_move(client):
    """POST /mouse with move action."""
    response = await client.post("/mouse?action=move&x=500&y=500")
    assert response.status_code == 200
    assert response.json()["status"] in ("executed", "unavailable")


# ─── Wallpaper ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wallpaper_set(client):
    """POST /wallpaper/set should return unavailable when httpx not installed
    or gracefully handle API errors."""
    response = await client.post(
        "/wallpaper/set",
        json={"description": "sunset mountains", "source": "auto"},
    )
    # Should handle missing httpx gracefully or return an error
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "status" in data


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
    # Create one first
    await client.post(
        "/protocols/create",
        json={
            "name": "my_workflow",
            "steps": [{"action": "open_app", "target": "notepad"}],
        },
    )

    response = await client.get("/protocols")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    names = [p["name"] for p in data["protocols"]]
    assert "my_workflow" in names


@pytest.mark.asyncio
async def test_activate_protocol_not_found(client):
    """POST /protocols/activate/{name} with non-existent name should return 404."""
    response = await client.post("/protocols/activate/nonexistent_protocol")
    assert response.status_code == 404
    assert "Protocol not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_activate_protocol_success(client):
    """POST /protocols/activate/{name} should execute protocol steps."""
    # Create a protocol with safe test steps (no actual app launches)
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


@pytest.mark.asyncio
async def test_delete_protocol(client):
    """DELETE /protocols/{name} should delete a protocol."""
    # Create first
    await client.post(
        "/protocols/create",
        json={
            "name": "temp_protocol",
            "steps": [{"action": "open_app", "target": "calc"}],
        },
    )

    # Delete
    response = await client.delete("/protocols/temp_protocol")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    # Verify gone
    list_resp = await client.get("/protocols")
    names = [p["name"] for p in list_resp.json()["protocols"]]
    assert "temp_protocol" not in names
