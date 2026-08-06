"""
Tests for in-place schema migrations.

CREATE TABLE IF NOT EXISTS never adds columns to databases created before a
schema change, so older installs rely on the ALTER TABLE migrations run inside
``initialize_schema``. These tests simulate an old database and verify the new
W7 quality-gate columns are added — and that the migration is idempotent.
"""

import pytest

from database.connection import db_connection
from database.schema import initialize_schema


@pytest.mark.asyncio
async def test_migration_adds_gate_columns_to_old_table():
    """A content_scripts table created before the gate columns gets ALTERed."""
    db_connection._db_path = ":memory:"
    db_connection._turso_mode = False
    db_connection._turso = None
    db_connection._db = None

    db = await db_connection.connect()
    # Simulate an OLD install: content_scripts without the W7 columns
    await db.execute(
        "CREATE TABLE content_scripts ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  score INTEGER DEFAULT 0"
        ")"
    )
    await db.commit()

    # Existing rows must survive with the new columns defaulting to 0
    await db_connection.execute(
        "INSERT INTO content_scripts (score) VALUES (88)"
    )
    await db.commit()

    await initialize_schema(db_connection)

    cols = [r["name"] for r in await db_connection.fetch_all("PRAGMA table_info(content_scripts)")]
    assert "revised" in cols, cols
    assert "gate_iterations" in cols, cols

    row = await db_connection.fetch_one(
        "SELECT revised, gate_iterations FROM content_scripts LIMIT 1"
    )
    assert row["revised"] == 0
    assert row["gate_iterations"] == 0

    await db_connection.close()


@pytest.mark.asyncio
async def test_migration_is_idempotent():
    """Running initialize_schema twice on an old table must not fail."""
    db_connection._db_path = ":memory:"
    db_connection._turso_mode = False
    db_connection._turso = None
    db_connection._db = None

    db = await db_connection.connect()
    await db.execute(
        "CREATE TABLE content_scripts ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  score INTEGER DEFAULT 0"
        ")"
    )
    await db.commit()

    await initialize_schema(db_connection)
    await initialize_schema(db_connection)

    cols = [r["name"] for r in await db_connection.fetch_all("PRAGMA table_info(content_scripts)")]
    assert cols.count("revised") == 1
    assert cols.count("gate_iterations") == 1

    await db_connection.close()
