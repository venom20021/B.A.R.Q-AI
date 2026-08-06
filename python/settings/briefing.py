"""
Morning briefing settings (W4) — persistence + scheduled-task registration.

The Settings UI writes briefing preferences to ``user_settings`` and keeps the
``scheduled_tasks`` table in sync so the briefing shows up alongside the other
scheduled automation (and in the voice wake greeting's pending-task list).

Effective config resolution: database values (set via the Settings UI) take
precedence over the env-based defaults in ``config.Settings``.
"""

from __future__ import annotations

import json
from typing import Any

from config import get_settings
from database import settings_dao

# Task name used in the scheduled_tasks table (voice greeting reads these names)
TASK_NAME = "Morning Briefing"
# 'custom' is the only task_type in the CHECK constraint that fits a workflow
TASK_TYPE = "custom"


def time_to_cron(time_str: str) -> str:
    """Convert an HH:MM time to a daily cron expression 'M H * * *'."""
    hour, minute = (time_str or "08:00").split(":")
    return f"{int(minute)} {int(hour)} * * *"


async def get_briefing_config() -> dict[str, Any]:
    """Return effective briefing settings: DB overrides env defaults."""
    settings = get_settings()
    enabled_raw = await settings_dao.get_setting("briefing_enabled")
    time_raw = await settings_dao.get_setting("briefing_time")
    return {
        "enabled": (enabled_raw == "true") if enabled_raw is not None else settings.briefing_enabled,
        "time": time_raw or settings.briefing_time,
    }


async def upsert_briefing_task(enabled: bool, time_str: str) -> dict[str, Any]:
    """Register/refresh the Morning Briefing row in scheduled_tasks (idempotent)."""
    cron = time_to_cron(time_str)
    config = {
        "workflow": "morning_briefing",
        "notify": True,
        "time": time_str,
        "cron": cron,
    }
    task_id = await settings_dao.upsert_scheduled_task(
        name=TASK_NAME,
        task_type=TASK_TYPE,
        cron_expression=cron,
        config=config,
        enabled=enabled,
    )
    return {"task_id": task_id, "enabled": enabled, "time": time_str, "cron": cron}


async def save_briefing_config(enabled: bool, time_str: str) -> dict[str, Any]:
    """Persist briefing settings to user_settings and register the task."""
    await settings_dao.set_setting("briefing_enabled", str(enabled).lower(), "briefing")
    await settings_dao.set_setting("briefing_time", time_str, "briefing")
    return await upsert_briefing_task(enabled, time_str)


def briefing_task_config_json(task: dict[str, Any]) -> dict[str, Any]:
    """Parse the JSON config of a scheduled-task row safely."""
    try:
        return json.loads(task.get("config") or "{}")
    except (ValueError, TypeError):
        return {}
