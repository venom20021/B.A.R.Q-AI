"""
Tests for the periodic knowledge-graph re-import (scheduled job):
  - settings/brain_sync.py helpers (interval_to_cron, config resolution, task upsert)
  - memory_knowledge/brain_api.run_brain_reimport core (used by the scheduler)
"""

import json

import pytest

from database import settings_dao


# ─── interval_to_cron ────────────────────────────────────────────────────────

def test_interval_to_cron():
    """Hourly intervals convert to 'M */H * * *' cron expressions."""
    from settings.brain_sync import interval_to_cron
    assert interval_to_cron(6) == "0 */6 * * *"
    assert interval_to_cron(1) == "0 */1 * * *"
    assert interval_to_cron(24) == "0 */24 * * *"


def test_interval_to_cron_clamps_below_one():
    """Intervals below 1 hour clamp to 1 (never schedule more than hourly)."""
    from settings.brain_sync import interval_to_cron
    assert interval_to_cron(0) == "0 */1 * * *"
    assert interval_to_cron(-3) == "0 */1 * * *"


# ─── get_brain_sync_config ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_brain_sync_config_env_defaults():
    """With no DB values, env defaults (enabled=true, 6h) win."""
    from settings.brain_sync import get_brain_sync_config
    cfg = await get_brain_sync_config()
    assert cfg["enabled"] is True
    assert cfg["interval_hours"] == 6


@pytest.mark.asyncio
async def test_get_brain_sync_config_db_overrides_env():
    """DB values set via the Settings UI take precedence over env defaults."""
    await settings_dao.set_setting("brain_reimport_enabled", "false", "knowledge")
    await settings_dao.set_setting("brain_reimport_interval_hours", "12", "knowledge")

    from settings.brain_sync import get_brain_sync_config
    cfg = await get_brain_sync_config()
    assert cfg["enabled"] is False
    assert cfg["interval_hours"] == 12


@pytest.mark.asyncio
async def test_get_brain_sync_config_clamps_zero_interval():
    """A 0/negative DB interval clamps to 1h so IntervalTrigger never raises."""
    await settings_dao.set_setting("brain_reimport_interval_hours", "0", "knowledge")

    from settings.brain_sync import get_brain_sync_config
    cfg = await get_brain_sync_config()
    assert cfg["interval_hours"] == 1


# ─── upsert_brain_sync_task ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_brain_sync_task_registers_row():
    """Registering the re-import creates its scheduled_tasks row."""
    from settings.brain_sync import TASK_NAME, upsert_brain_sync_task
    result = await upsert_brain_sync_task(enabled=True, interval_hours=6)
    assert result["task_id"] > 0
    assert result["cron"] == "0 */6 * * *"

    row = await settings_dao.get_scheduled_task(TASK_NAME)
    assert row is not None
    assert row["task_type"] == "custom"
    assert row["enabled"] == 1
    assert json.loads(row["config"])["workflow"] == "brain_reimport"


@pytest.mark.asyncio
async def test_upsert_brain_sync_task_idempotent():
    """Re-registering keeps the same row id and updates cron/enabled."""
    from settings.brain_sync import upsert_brain_sync_task
    first = await upsert_brain_sync_task(enabled=True, interval_hours=6)
    second = await upsert_brain_sync_task(enabled=False, interval_hours=12)
    assert second["task_id"] == first["task_id"]
    assert second["cron"] == "0 */12 * * *"

    row = await settings_dao.get_scheduled_task("Knowledge Graph Re-Import")
    assert row["enabled"] == 0
    assert row["cron_expression"] == "0 */12 * * *"


# ─── save_brain_sync_config ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_brain_sync_config_persists_and_registers():
    """Saving persists user_settings AND registers the scheduled task."""
    from settings.brain_sync import save_brain_sync_config
    result = await save_brain_sync_config(enabled=True, interval_hours=4)
    assert result["enabled"] is True
    assert result["cron"] == "0 */4 * * *"

    assert await settings_dao.get_setting("brain_reimport_enabled") == "true"
    assert await settings_dao.get_setting("brain_reimport_interval_hours") == "4"
    assert await settings_dao.get_scheduled_task("Knowledge Graph Re-Import") is not None


# ─── brain_sync_task_config_json ──────────────────────────────────────────────

def test_brain_sync_task_config_json_parses():
    """A stored row's config JSON string parses back to a dict."""
    from settings.brain_sync import brain_sync_task_config_json
    parsed = brain_sync_task_config_json(
        {"config": '{"workflow": "brain_reimport", "cron": "0 */6 * * *"}'}
    )
    assert parsed["workflow"] == "brain_reimport"


def test_brain_sync_task_config_json_invalid_is_safe():
    """Malformed or missing config never raises."""
    from settings.brain_sync import brain_sync_task_config_json
    assert brain_sync_task_config_json({"config": "not json"}) == {}
    assert brain_sync_task_config_json({"config": None}) == {}
    assert brain_sync_task_config_json({}) == {}


# ─── run_brain_reimport core (scheduler job body) ─────────────────────────────

@pytest.mark.asyncio
async def test_run_brain_reimport_imports_notes_into_general():
    """The scheduler core pulls notes into the general brain without the LLM."""
    import tempfile

    from database.connection import db_connection
    from memory_knowledge import brain_api
    from memory_knowledge.multi_brain import multi_brain_manager

    with tempfile.TemporaryDirectory() as td:
        multi_brain_manager.clear_brain("general")
        multi_brain_manager.clear_brain("career")

        await db_connection.insert(
            "INSERT INTO notes (title, content) VALUES (?, ?)",
            ("scheduled reimport note", "barq syncs this note into the graph"),
        )

        # Isolate persistence to a temp dir (auto-restored on exit so the
        # singleton never keeps a torn-down path) + force the direct path.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(multi_brain_manager, "_data_dir", td)

            async def _no_llm(_text):
                return [], "none"
            mp.setattr(brain_api, "extract_triplets_with_provider", _no_llm)

            result = await brain_api.run_brain_reimport()

        assert result["status"] == "imported"
        # Direct fallback still lands the note triplet in the general brain.
        general = multi_brain_manager.get_brain("general")
        assert "scheduled reimport note" in general.nodes
        assert len(list(general.neighbors("scheduled reimport note"))) >= 1


@pytest.mark.asyncio
async def test_run_brain_reimport_reports_provider_and_direct():
    """LLM provider + direct-import counters are reported in the result dict."""
    import tempfile

    from database.connection import db_connection
    from memory_knowledge import brain_api
    from memory_knowledge.multi_brain import multi_brain_manager

    with tempfile.TemporaryDirectory() as td:
        multi_brain_manager.clear_brain("general")
        multi_brain_manager.clear_brain("career")

        # Seed a note so the notes→general LLM pass actually runs.
        await db_connection.insert(
            "INSERT INTO notes (title, content) VALUES (?, ?)",
            ("provider test note", "something to extract"),
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(multi_brain_manager, "_data_dir", td)

            async def _fake_llm(_text):
                return [("python", "USED_FOR", "automation")], "gemini"
            mp.setattr(brain_api, "extract_triplets_with_provider", _fake_llm)

            result = await brain_api.run_brain_reimport()

        assert result["status"] == "imported"
        results = result["results"]
        assert results.get("notes_provider") == "gemini"
        assert results.get("memory_provider") == "gemini"
        assert "direct_triplets" in results
        assert "general" in results["direct_triplets"]
