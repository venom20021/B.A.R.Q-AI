"""
Tests for database schema - verify all tables are created with correct structure.
"""

import pytest
from database.connection import db_connection
from database.schema import ALL_TABLES


@pytest.mark.asyncio
async def test_all_tables_created():
    """Verify that all expected tables exist after schema initialization."""
    db = await db_connection.connect()
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    # Filter out sqlite_sequence
    tables = [t for t in tables if not t.startswith("sqlite_")]

    expected_tables = [name for name, _ in ALL_TABLES]
    for table in expected_tables:
        assert table in tables, f"Table '{table}' was not created"

    assert len(tables) == len(expected_tables)


@pytest.mark.asyncio
async def test_table_columns():
    """Verify key tables have expected columns."""
    db = await db_connection.connect()

    # Check job_listings columns
    cursor = await db.execute("PRAGMA table_info(job_listings)")
    columns = {row[1] for row in await cursor.fetchall()}
    for col in ("id", "title", "company", "location", "source_board", "source_url"):
        assert col in columns, f"job_listings missing column: {col}"

    # Check user_settings columns
    cursor = await db.execute("PRAGMA table_info(user_settings)")
    columns = {row[1] for row in await cursor.fetchall()}
    for col in ("key", "value", "category"):
        assert col in columns, f"user_settings missing column: {col}"

    # Check notifications columns
    cursor = await db.execute("PRAGMA table_info(notifications)")
    columns = {row[1] for row in await cursor.fetchall()}
    for col in ("title", "body", "priority", "category", "channel"):
        assert col in columns, f"notifications missing column: {col}"


@pytest.mark.asyncio
async def test_foreign_keys_enabled():
    """Verify foreign key constraints are enabled."""
    db = await db_connection.connect()
    cursor = await db.execute("PRAGMA foreign_keys")
    row = await cursor.fetchone()
    assert row[0] == 1, "Foreign keys should be enabled"


@pytest.mark.asyncio
async def test_wal_mode_enabled():
    """Verify WAL journal mode is enabled (or memory for in-memory DB)."""
    db = await db_connection.connect()
    cursor = await db.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    # :memory: databases always use 'memory'; file-based databases use 'wal'
    assert row[0] in ("wal", "memory"), f"Expected WAL or memory mode, got {row[0]}"


@pytest.mark.asyncio
async def test_can_create_and_drop():
    """Test that we can create tables, insert, and query."""
    db = await db_connection.connect()

    # Insert a test job listing
    await db.execute("""
        INSERT INTO job_listings (title, company, source_board)
        VALUES (?, ?, ?)
    """, ("Test Engineer", "Test Corp", "linkedin"))

    # Read it back by named column to avoid fragile positional indices
    cursor = await db.execute(
        "SELECT id, external_id, title, company FROM job_listings WHERE title = ?",
        ("Test Engineer",),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[2] == "Test Engineer"  # title column
    assert row[3] == "Test Corp"      # company column
