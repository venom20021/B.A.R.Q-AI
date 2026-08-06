"""
Knowledge-graph re-import settings — persistence + scheduled-task registration.

The periodic re-import keeps the multi-brain knowledge graphs fresh by pulling
new notes / memory / jobs into ``general`` and ``career`` brains on an
interval.  This module mirrors ``settings/briefing.py``:

- The Settings layer writes preferences to ``user_settings`` (DB overrides the
  env-based defaults in ``config.Settings``).
- ``upsert_brain_sync_task`` keeps the ``scheduled_tasks`` table in sync so the
  job shows up alongside the other scheduled automation.
"""

from __future__ import annotations

import json
from typing import Any

from config import get_settings
from database import settings_dao

# Task name used in the scheduled_tasks table
TASK_NAME = "Knowledge Graph Re-Import"
# 'custom' is the only task_type in the CHECK constraint that fits a workflow
TASK_TYPE = "custom"


def interval_to_cron(hours: int) -> str:
    """Convert an hourly interval to a cron expression 'M */H * * *'."""
    hours = max(1, int(hours))
    return f"0 */{hours} * * *"


async def get_brain_sync_config() -> dict[str, Any]:
    """Return effective re-import settings: DB overrides env defaults.

    The interval is clamped to >= 1 hour here — not just inside
    ``interval_to_cron`` — because the scheduler builds an
    ``IntervalTrigger(hours=...)`` from this value directly, and APScheduler
    raises on ``hours=0``.
    """
    settings = get_settings()
    enabled_raw = await settings_dao.get_setting("brain_reimport_enabled")
    interval_raw = await settings_dao.get_setting("brain_reimport_interval_hours")
    return {
        "enabled": (enabled_raw == "true") if enabled_raw is not None else settings.brain_reimport_enabled,
        "interval_hours": max(1, int(interval_raw)) if interval_raw else max(1, settings.brain_reimport_interval_hours),
    }


async def upsert_brain_sync_task(enabled: bool, interval_hours: int) -> dict[str, Any]:
    """Register/refresh the Knowledge Graph Re-Import row in scheduled_tasks (idempotent)."""
    clamped = max(1, int(interval_hours))
    cron = interval_to_cron(clamped)
    config = {
        "workflow": "brain_reimport",
        "interval_hours": clamped,
        "cron": cron,
    }
    task_id = await settings_dao.upsert_scheduled_task(
        name=TASK_NAME,
        task_type=TASK_TYPE,
        cron_expression=cron,
        config=config,
        enabled=enabled,
    )
    return {"task_id": task_id, "enabled": enabled, "interval_hours": clamped, "cron": cron}


async def save_brain_sync_config(enabled: bool, interval_hours: int) -> dict[str, Any]:
    """Persist re-import settings to user_settings and register the task."""
    await settings_dao.set_setting(
        "brain_reimport_enabled", str(enabled).lower(), "knowledge"
    )
    await settings_dao.set_setting(
        "brain_reimport_interval_hours", str(int(interval_hours)), "knowledge"
    )
    return await upsert_brain_sync_task(enabled, interval_hours)


def brain_sync_task_config_json(task: dict[str, Any]) -> dict[str, Any]:
    """Parse the JSON config of a scheduled-task row safely."""
    try:
        return json.loads(task.get("config") or "{}")
    except (ValueError, TypeError):
        return {}
