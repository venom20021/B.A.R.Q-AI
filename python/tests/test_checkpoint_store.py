"""
Tests for the Checkpoint Store (W2) — agent.checkpoint_store.

Uses the conftest in-memory SQLite DB (initialized with the full schema,
including the new agent_checkpoints table).
"""

import pytest

from agent.checkpoint_store import get_checkpoint_store


@pytest.fixture
async def store():
    return get_checkpoint_store()


@pytest.mark.asyncio
async def test_save_and_load_roundtrip(store):
    await store.save("agent:test1", {"goal": "test goal", "plan": {"steps": []}, "completed_steps": []})
    state = await store.load("agent:test1")
    assert state is not None
    assert state["goal"] == "test goal"
    assert state["_status"] == "active"
    assert state["_checkpoint_key"] == "agent:test1"


@pytest.mark.asyncio
async def test_load_missing_returns_none(store):
    assert await store.load("agent:nope") is None


@pytest.mark.asyncio
async def test_upsert_updates_existing(store):
    await store.save("agent:test2", {"goal": "v1"})
    await store.save("agent:test2", {"goal": "v2", "extra": True})
    state = await store.load("agent:test2")
    assert state["goal"] == "v2"
    assert state["extra"] is True


@pytest.mark.asyncio
async def test_delete_removes(store):
    await store.save("agent:test3", {"goal": "x"})
    assert await store.delete("agent:test3") is True
    assert await store.load("agent:test3") is None
    assert await store.delete("agent:test3") is False


@pytest.mark.asyncio
async def test_list_filters_by_agent_type(store):
    await store.save("agent:list1", {"goal": "a"}, agent_type="agent")
    await store.save("workflow:list1", {"workflow": "w"}, agent_type="workflow")
    rows = await store.list_checkpoints(agent_type="workflow")
    assert any(r["checkpoint_key"] == "workflow:list1" for r in rows)
    rows = await store.list_checkpoints(agent_type="agent")
    assert any(r["checkpoint_key"] == "agent:list1" for r in rows)


@pytest.mark.asyncio
async def test_mark_complete(store):
    await store.save("agent:done1", {"goal": "y"})
    await store.mark_complete("agent:done1")
    state = await store.load("agent:done1")
    assert state["_status"] == "complete"


@pytest.mark.asyncio
async def test_list_with_parsed_data(store):
    """list_with_parsed_data decodes each row's data JSON into a dict."""
    await store.save("agent:parsed1", {"goal": "g", "plan": {"steps": [1, 2]}}, agent_type="agent")
    rows = await store.list_with_parsed_data(limit=10)
    row = next(r for r in rows if r["checkpoint_key"] == "agent:parsed1")
    assert isinstance(row["data"], dict)
    assert row["data"]["goal"] == "g"


@pytest.mark.asyncio
async def test_list_with_parsed_data_bad_json_is_safe(store):
    """Corrupt data JSON decodes to {} instead of raising."""
    import json
    from database import db_connection
    await db_connection.execute(
        "INSERT INTO agent_checkpoints (checkpoint_key, agent_type, data) VALUES (?, ?, ?)",
        ("agent:badjson", "agent", "{not valid json"),
    )
    await db_connection.commit()
    rows = await store.list_with_parsed_data(limit=10)
    row = next(r for r in rows if r["checkpoint_key"] == "agent:badjson")
    assert row["data"] == {}
