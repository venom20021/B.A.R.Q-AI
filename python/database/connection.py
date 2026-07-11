"""
Database connection manager with async SQLite via aiosqlite.
Handles initialization, connection lifecycle, and transaction management.
"""

import os
from pathlib import Path
from typing import Optional

import aiosqlite

from config import get_settings


class DatabaseConnection:
    """Manages the async SQLite database connection."""

    def __init__(self):
        self.settings = get_settings()
        self._db: Optional[aiosqlite.Connection] = None
        self._db_path: str = self._resolve_db_path()

    def _resolve_db_path(self) -> str:
        """
        Resolve the database file path from the connection URL.
        Handles sqlite+aiosqlite:///path/to/db format.
        """
        url = self.settings.database_url
        if url.startswith("sqlite+aiosqlite:///"):
            path = url[len("sqlite+aiosqlite:///"):]
        elif url.startswith("sqlite:///"):
            path = url[len("sqlite:///"):]
        else:
            path = url

        # Ensure directory exists
        db_dir = os.path.dirname(path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)

        return path

    @property
    def db_path(self) -> str:
        return self._db_path

    async def connect(self) -> aiosqlite.Connection:
        """Get or create the database connection."""
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row

            # Enable WAL mode for better concurrent access
            await self._db.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys
            await self._db.execute("PRAGMA foreign_keys=ON")
            # Optimize for this application pattern
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self._db.execute("PRAGMA cache_size=-8000")  # 8MB cache
            await self._db.execute("PRAGMA busy_timeout=5000")  # 5 second timeout

        return self._db

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def execute(self, sql: str, params: tuple = ()):
        """Execute a single SQL statement."""
        db = await self.connect()
        return await db.execute(sql, params)

    async def execute_many(self, sql: str, params_list: list[tuple]):
        """Execute a SQL statement with multiple parameter sets."""
        db = await self.connect()
        return await db.executemany(sql, params_list)

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Fetch a single row as a dict."""
        db = await self.connect()
        cursor = await db.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as a list of dicts."""
        db = await self.connect()
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def insert(self, sql: str, params: tuple = ()) -> int:
        """
        Insert a row and return the last row ID.
        Automatically commits.
        """
        db = await self.connect()
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.lastrowid

    async def update(self, sql: str, params: tuple = ()) -> int:
        """
        Update rows and return the count of affected rows.
        Automatically commits.
        """
        db = await self.connect()
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount

    async def delete(self, sql: str, params: tuple = ()) -> int:
        """Delete rows and return the count of affected rows."""
        db = await self.connect()
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount


# Singleton instance
db_connection = DatabaseConnection()
