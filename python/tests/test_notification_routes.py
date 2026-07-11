"""
Tests for notification FastAPI routes: send, pending, read, digest, settings, status, test.
Uses the notification_manager singleton which gracefully handles unconfigured channels.
"""


import pytest


@pytest.fixture
def router():
    from notifications import routes
    return routes.router


# ─── Send ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_notification(client):
    """POST /send should dispatch a notification through available channels."""
    response = await client.post(
        "/send",
        json={
            "title": "Test Alert",
            "body": "This is a test notification",
            "priority": "normal",
            "category": "general",
            "channel": "desktop",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "results" in data
    # Desktop channel should succeed (stores in DB)
    assert "desktop" in data["results"]


@pytest.mark.asyncio
async def test_send_urgent_notification(client):
    """POST /send with urgent priority should attempt all channels."""
    response = await client.post(
        "/send",
        json={
            "title": "Urgent Alert",
            "body": "Critical system issue",
            "priority": "urgent",
            "category": "system",
            "channel": "all",
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Desktop should succeed; telegram/email may be unconfigured
    assert "desktop" in data["results"]


@pytest.mark.asyncio
async def test_send_notification_validation(client):
    """POST /send with invalid priority should return 422."""
    response = await client.post(
        "/send",
        json={
            "title": "Bad",
            "body": "Invalid priority",
            "priority": "super_urgent",
        },
    )
    assert response.status_code == 422


# ─── Pending ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pending_empty(client):
    """GET /pending should return empty list when no notifications exist."""
    response = await client.get("/pending")
    assert response.status_code == 200
    data = response.json()
    assert "notifications" in data
    assert "counts" in data
    assert isinstance(data["notifications"], list)


@pytest.mark.asyncio
async def test_get_pending_with_unread(client):
    """GET /pending should return unread notifications."""
    # Send a notification to create one
    await client.post(
        "/send",
        json={
            "title": "Unread Test",
            "body": "Read me later",
            "priority": "high",
            "category": "general",
            "channel": "desktop",
        },
    )

    response = await client.get("/pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) >= 1
    assert data["counts"]["unread"] >= 1


# ─── Mark Read ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_read_success(client):
    """POST /{id}/read should mark notification as read."""
    # Create a notification first
    send_resp = await client.post(
        "/send",
        json={
            "title": "Mark Me",
            "body": "Will be read",
            "priority": "normal",
            "channel": "desktop",
        },
    )
    assert send_resp.status_code == 200

    # Get pending to find the ID
    pending = await client.get("/pending")
    notifs = pending.json()["notifications"]
    assert len(notifs) >= 1
    notif_id = notifs[0]["id"]

    # Mark as read
    read_resp = await client.post(f"/{notif_id}/read")
    assert read_resp.status_code == 200
    assert read_resp.json()["status"] == "read"
    assert read_resp.json()["id"] == notif_id


@pytest.mark.asyncio
async def test_mark_read_not_found(client):
    """POST /{id}/read with non-existent id should return 404."""
    response = await client.post("/99999/read")
    assert response.status_code == 404


# ─── Digest ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trigger_digest(client):
    """POST /digest should trigger daily digest (succeeds even if empty/not configured)."""
    response = await client.post("/digest")
    # Digest may succeed or return empty results if not configured
    assert response.status_code == 200
    data = response.json()
    assert "success" in data


# ─── Status ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_notification_status(client):
    """GET /status should return channel status and pending counts."""
    response = await client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "channels" in data
    assert "pending" in data
    assert "desktop" in data["channels"]
    assert isinstance(data["channels"]["desktop"], bool)


# ─── Settings ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_notification_settings(client):
    """GET /settings should return notification preferences."""
    response = await client.get("/settings")
    assert response.status_code == 200
    data = response.json()
    # Seed defaults include notification settings
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_update_notification_settings(client):
    """POST /settings should update notification preferences."""
    response = await client.post(
        "/settings",
        json={"desktop_enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "updated"

    # Verify
    settings_resp = await client.get("/settings")
    assert settings_resp.json()["desktop_notifications"] == "false"


# ─── Test Channel ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_test_channel_desktop(client):
    """POST /test/desktop should send a test notification to desktop."""
    response = await client.post("/test/desktop")
    assert response.status_code == 200
    data = response.json()
    assert data["channel"] == "desktop"
    assert "success" in data


@pytest.mark.asyncio
async def test_test_channel_unknown(client):
    """POST /test/{channel} with unknown channel should return 400."""
    response = await client.post("/test/slack")
    assert response.status_code == 400
    assert "unknown channel" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_test_channel_telegram(client):
    """POST /test/telegram should attempt to send (may fail if not configured)."""
    response = await client.post("/test/telegram")
    assert response.status_code == 200
    data = response.json()
    assert data["channel"] == "telegram"


@pytest.mark.asyncio
async def test_test_channel_email(client):
    """POST /test/email should attempt to send (may fail if not configured)."""
    response = await client.post("/test/email")
    assert response.status_code == 200
    data = response.json()
    assert data["channel"] == "email"
