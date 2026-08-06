"""
Tests for the W4 morning briefing settings:
  - settings/briefing.py helpers (time_to_cron, config resolution, task upsert)
  - GET/POST /settings/briefing routes (via the conftest client fixture)
"""

import json

import pytest

from database import settings_dao


# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def router():
    """The settings router for the shared FastAPI client fixture."""
    from settings import routes
    return routes.router


# ─── time_to_cron ─────────────────────────────────────────────────────────────

def test_time_to_cron():
    """HH:MM converts to a daily cron 'M H * * *'."""
    from settings.briefing import time_to_cron
    assert time_to_cron("08:00") == "0 8 * * *"
    assert time_to_cron("23:59") == "59 23 * * *"
    assert time_to_cron("") == "0 8 * * *"  # empty falls back to 08:00


# ─── get_briefing_config ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_briefing_config_env_defaults():
    """With no DB values, env defaults (enabled=true, 08:00) win."""
    from settings.briefing import get_briefing_config
    cfg = await get_briefing_config()
    assert cfg["enabled"] is True
    assert cfg["time"] == "08:00"


@pytest.mark.asyncio
async def test_get_briefing_config_db_overrides_env():
    """DB values set via the Settings UI take precedence over env defaults."""
    await settings_dao.set_setting("briefing_enabled", "false", "briefing")
    await settings_dao.set_setting("briefing_time", "06:30", "briefing")

    from settings.briefing import get_briefing_config
    cfg = await get_briefing_config()
    assert cfg["enabled"] is False
    assert cfg["time"] == "06:30"


# ─── upsert_briefing_task ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_briefing_task_registers_row():
    """Registering the briefing creates/refreshes its scheduled_tasks row."""
    from settings.briefing import TASK_NAME, upsert_briefing_task
    result = await upsert_briefing_task(enabled=True, time_str="08:00")
    assert result["task_id"] > 0
    assert result["cron"] == "0 8 * * *"

    row = await settings_dao.get_scheduled_task(TASK_NAME)
    assert row is not None
    assert row["task_type"] == "custom"
    assert row["enabled"] == 1
    assert json.loads(row["config"])["workflow"] == "morning_briefing"


@pytest.mark.asyncio
async def test_upsert_briefing_task_idempotent():
    """Re-registering keeps the same row id and updates cron/enabled."""
    from settings.briefing import upsert_briefing_task
    first = await upsert_briefing_task(enabled=True, time_str="08:00")
    second = await upsert_briefing_task(enabled=False, time_str="09:15")
    assert second["task_id"] == first["task_id"]
    assert second["cron"] == "15 9 * * *"

    row = await settings_dao.get_scheduled_task("Morning Briefing")
    assert row["enabled"] == 0
    assert row["cron_expression"] == "15 9 * * *"


# ─── save_briefing_config ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_briefing_config_persists_and_registers():
    """Saving persists user_settings AND registers the scheduled task."""
    from settings.briefing import save_briefing_config
    result = await save_briefing_config(enabled=True, time_str="07:45")
    assert result["enabled"] is True
    assert result["cron"] == "45 7 * * *"

    assert await settings_dao.get_setting("briefing_enabled") == "true"
    assert await settings_dao.get_setting("briefing_time") == "07:45"
    assert await settings_dao.get_scheduled_task("Morning Briefing") is not None


# ─── briefing_task_config_json ────────────────────────────────────────────────

def test_briefing_task_config_json_parses():
    """A stored row's config JSON string parses back to a dict."""
    from settings.briefing import briefing_task_config_json
    parsed = briefing_task_config_json({"config": '{"workflow": "morning_briefing", "cron": "0 8 * * *"}'})
    assert parsed["workflow"] == "morning_briefing"


def test_briefing_task_config_json_invalid_is_safe():
    """Malformed or missing config never raises."""
    from settings.briefing import briefing_task_config_json
    assert briefing_task_config_json({"config": "not json"}) == {}
    assert briefing_task_config_json({"config": None}) == {}
    assert briefing_task_config_json({}) == {}


# ─── Routes ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_briefing_route(client):
    """GET /settings/briefing returns effective config + registration status."""
    response = await client.get("/settings/briefing")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "time" in data
    assert "scheduled" in data
    assert data["scheduled"] is False  # not registered yet in this fresh DB


@pytest.mark.asyncio
async def test_post_briefing_route_registers(client):
    """POST /settings/briefing persists settings and registers the task."""
    response = await client.post(
        "/settings/briefing",
        json={"enabled": True, "time": "07:30"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"
    assert data["task_id"] > 0
    assert data["cron"] == "30 7 * * *"

    # Follow-up GET reflects the persisted state
    get_resp = await client.get("/settings/briefing")
    get_data = get_resp.json()
    assert get_data["scheduled"] is True
    assert get_data["time"] == "07:30"
    assert get_data["cron"] == "30 7 * * *"
