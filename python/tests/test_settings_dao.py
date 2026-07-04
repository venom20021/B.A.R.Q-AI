"""
Tests for SettingsDAO - user settings, profiles, notifications, and voice commands.
"""

import json
import pytest
from database import settings_dao


@pytest.mark.asyncio
async def test_set_and_get_setting():
    """Test setting and retrieving a setting."""
    result = await settings_dao.set_setting("test_key", "test_value", "general")
    assert result >= 0

    value = await settings_dao.get_setting("test_key")
    assert value == "test_value"


@pytest.mark.asyncio
async def test_update_setting():
    """Test updating an existing setting."""
    await settings_dao.set_setting("update_key", "old_value")
    await settings_dao.set_setting("update_key", "new_value")

    value = await settings_dao.get_setting("update_key")
    assert value == "new_value"


@pytest.mark.asyncio
async def test_get_settings_by_category():
    """Test retrieving settings filtered by category."""
    await settings_dao.set_setting("voice_setting", "true", "voice")
    await settings_dao.set_setting("voice_volume", "80", "voice")

    voice_settings = await settings_dao.get_settings_by_category("voice")
    # Should include our test entries plus any seed defaults in the voice category
    keys = [s["key"] for s in voice_settings]
    assert "voice_setting" in keys
    assert "voice_volume" in keys
    assert len(voice_settings) >= 2


@pytest.mark.asyncio
async def test_delete_setting():
    """Test deleting a setting."""
    await settings_dao.set_setting("delete_me", "value")
    await settings_dao.delete_setting("delete_me")

    value = await settings_dao.get_setting("delete_me")
    assert value is None


@pytest.mark.asyncio
async def test_api_key_storage():
    """Test storing and retrieving API keys."""
    await settings_dao.set_api_key("test_service", "sk-test-12345")

    key = await settings_dao.get_api_key("test_service")
    assert key == "sk-test-12345"


@pytest.mark.asyncio
async def test_get_configured_services():
    """Test listing configured services."""
    configured = await settings_dao.get_configured_services()
    assert isinstance(configured, list)


@pytest.mark.asyncio
async def test_profile_upsert():
    """Test creating and updating user profile."""
    profile_id = await settings_dao.upsert_profile({
        "full_name": "Test User",
        "email": "test@example.com",
        "headline": "Software Engineer",
        "skills": json.dumps(["Python", "React", "TypeScript"]),
    })
    assert profile_id >= 0

    profile = await settings_dao.get_profile()
    assert profile is not None
    assert profile["full_name"] == "Test User"
    assert profile["email"] == "test@example.com"

    # Update profile
    await settings_dao.upsert_profile({
        "full_name": "Updated User",
        "headline": "Senior Engineer",
    })

    profile = await settings_dao.get_profile()
    assert profile["full_name"] == "Updated User"
    assert profile["headline"] == "Senior Engineer"


@pytest.mark.asyncio
async def test_update_skills():
    """Test updating user skills list."""
    await settings_dao.upsert_profile({"full_name": "Skill Test"})
    await settings_dao.update_skills(["Python", "React", "Go"])

    profile = await settings_dao.get_profile()
    skills = json.loads(profile["skills"])
    assert "Python" in skills
    assert "Go" in skills


@pytest.mark.asyncio
async def test_notification_crud():
    """Test creating and reading notifications."""
    notif_id = await settings_dao.insert_notification({
        "channel": "desktop",
        "title": "Test Notification",
        "body": "This is a test",
        "priority": "high",
        "category": "general",
    })
    assert notif_id > 0

    unread = await settings_dao.get_unread_notifications()
    assert len(unread) >= 1
    assert unread[0]["title"] == "Test Notification"
    assert unread[0]["read"] == 0

    # Mark as read
    await settings_dao.mark_notification_read(notif_id)
    unread = await settings_dao.get_unread_notifications()
    assert len([n for n in unread if n["id"] == notif_id]) == 0


@pytest.mark.asyncio
async def test_notification_counts():
    """Test notification count aggregation."""
    counts = await settings_dao.get_notification_count()
    assert isinstance(counts, dict)
    for key in ("total", "unread", "urgent"):
        assert key in counts


@pytest.mark.asyncio
async def test_voice_command_logging():
    """Test logging voice commands."""
    cmd_id = await settings_dao.log_command({
        "transcript": "scan jobs",
        "confidence": 0.95,
        "action": "scan_jobs",
        "was_wake_word": True,
        "processed": True,
        "success": True,
        "duration_ms": 1200,
    })
    assert cmd_id > 0

    commands = await settings_dao.get_recent_commands(limit=10)
    assert len(commands) >= 1
    assert commands[0]["transcript"] == "scan jobs"


@pytest.mark.asyncio
async def test_priority_ordering():
    """Test that notifications are ordered by priority correctly."""
    await settings_dao.insert_notification({
        "channel": "desktop", "title": "Low", "body": "Low priority", "priority": "low", "category": "general",
    })
    await settings_dao.insert_notification({
        "channel": "desktop", "title": "Urgent", "body": "Urgent!", "priority": "urgent", "category": "general",
    })
    await settings_dao.insert_notification({
        "channel": "desktop", "title": "High", "body": "High priority", "priority": "high", "category": "general",
    })

    unread = await settings_dao.get_unread_notifications()
    # Urgent should come first
    assert unread[0]["title"] == "Urgent"
    assert unread[1]["title"] == "High"
