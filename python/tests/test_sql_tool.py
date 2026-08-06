"""
Tests for the SQL Tool-Use skill (Feature 1) — agent.sql_tool.

Covers:
- Statement validation (read-only gate, multi-statement rejection)
- Write/DDL blocking
- Async execution with blocking sqlite3 I/O via asyncio.to_thread
"""

import asyncio
import sqlite3

import pytest

from agent.sql_tool import (
    _execute_sql_blocking,
    _validate_query,
    run_sql_query,
)


# ─── Validation tests ────────────────────────────────────────────────────


class TestValidateQuery:
    def test_accepts_select(self):
        q = _validate_query("SELECT * FROM memory_entries LIMIT 5", readonly=True)
        assert q.startswith("SELECT")

    def test_accepts_with(self):
        q = _validate_query("WITH x AS (SELECT 1) SELECT * FROM x", readonly=True)
        assert q.startswith("WITH")

    def test_accepts_readonly_pragma(self):
        _validate_query("PRAGMA table_info(memory_entries)", readonly=True)

    def test_rejects_insert(self):
        with pytest.raises(ValueError, match="blocked"):
            _validate_query("INSERT INTO memory_entries (key) VALUES ('x')", readonly=True)

    def test_rejects_update(self):
        with pytest.raises(ValueError, match="blocked"):
            _validate_query("UPDATE memory_entries SET value='x'", readonly=True)

    def test_rejects_drop(self):
        with pytest.raises(ValueError, match="blocked"):
            _validate_query("DROP TABLE memory_entries", readonly=True)

    def test_rejects_multi_statement_injection(self):
        with pytest.raises(ValueError, match="Multi-statement"):
            _validate_query("SELECT 1; DROP TABLE memory_entries", readonly=True)

    def test_rejects_non_readonly_pragma(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_query("PRAGMA journal_mode=WAL", readonly=True)

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            _validate_query("   ", readonly=True)

    def test_readonly_off_allows_insert(self):
        q = _validate_query("INSERT INTO memory_entries (id, key, value) VALUES ('1','k','v')", readonly=False)
        assert q.startswith("INSERT")


# ─── Execution tests ─────────────────────────────────────────────────────


@pytest.fixture
def sample_db(tmp_path):
    """Create a temp sqlite db with a memory_entries-like table."""
    db = tmp_path / "test_memory.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE memory_entries (id TEXT, key TEXT, value TEXT, category TEXT)"
    )
    conn.executemany(
        "INSERT INTO memory_entries VALUES (?, ?, ?, ?)",
        [
            ("1", "name", "Alice", "identity"),
            ("2", "goal", "Ship BARQ v2", "projects"),
            ("3", "color", "cyan", "preferences"),
        ],
    )
    conn.commit()
    conn.close()
    return str(db)


@pytest.mark.asyncio
async def test_run_sql_query_selects_rows(sample_db, monkeypatch):
    monkeypatch.setattr("agent.sql_tool._resolve_memory_db_path", lambda: sample_db)
    result = await run_sql_query("SELECT key, value FROM memory_entries ORDER BY key")
    assert "name" in result
    assert "Alice" in result
    assert "color" in result


@pytest.mark.asyncio
async def test_run_sql_query_rejects_writes(sample_db, monkeypatch):
    monkeypatch.setattr("agent.sql_tool._resolve_memory_db_path", lambda: sample_db)
    with pytest.raises(ValueError, match="blocked"):
        await run_sql_query("DELETE FROM memory_entries")


@pytest.mark.asyncio
async def test_run_sql_query_honors_limit(sample_db, monkeypatch):
    monkeypatch.setattr("agent.sql_tool._resolve_memory_db_path", lambda: sample_db)
    result = await run_sql_query("SELECT * FROM memory_entries", limit=2)
    assert "truncated" in result


@pytest.mark.asyncio
async def test_execute_blocking_runs_in_thread(sample_db, monkeypatch):
    """Verify _execute_sql_blocking works when invoked via asyncio.to_thread."""
    monkeypatch.setattr("agent.sql_tool._resolve_memory_db_path", lambda: sample_db)
    result = await asyncio.to_thread(
        _execute_sql_blocking, "SELECT COUNT(*) as c FROM memory_entries", 50
    )
    assert "3" in result


def test_validate_runs_purely(sample_db, monkeypatch):
    """Sanity check that validation does not touch the DB."""
    monkeypatch.setattr("agent.sql_tool._resolve_memory_db_path", lambda: sample_db)
    assert _validate_query("SELECT 1", readonly=True) == "SELECT 1"
