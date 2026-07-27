"""
BARQ Memory Bus — unified memory interface for all agent memory systems.

Provides a single entry point for storing, searching, and retrieving
memories across all of BARQ's memory backends:

- Long-term JSON memory (agent_memory_manager)
- Knowledge graph (memory_knowledge)
- SQLite FTS5 for full-text search
- TTL-based automatic expiration

Usage:
    bus = get_memory_bus()
    await bus.store("user_name", "Alice", category="identity")
    results = await bus.search("Alice", limit=5)
    bus.format_for_prompt()  # Get all memories as LLM prompt context
"""

import asyncio
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ─── Defaults ───────────────────────────────────────────────────────────────

MEMORY_BUS_DB = "memory_bus.db"
DEFAULT_TTL_SECONDS = 90 * 24 * 3600  # 90 days
MEMORY_MAX_CHARS_PER_TYPE = 5000


class MemoryBus:
    """Unified memory bus with FTS5 full-text search and TTL expiration.

    All agents write and read memory through this bus, ensuring:
    - Single query interface regardless of backend
    - Full-text search via SQLite FTS5
    - Automatic expiration of stale memories
    - Consistent tagging and categorization
    """

    def __init__(self, db_path: str = ""):
        self._db_path = db_path or str(
            Path(__file__).parent.parent / "data" / MEMORY_BUS_DB
        )
        self._init_db()
        self._started = False
        self._prune_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start background TTL pruning.

        Safe to call with or without a running event loop (tests,
        production). If no loop is running, pruning is skipped until
        ``start()`` is called again from an async context.
        """
        if self._started:
            return
        self._started = True
        try:
            loop = asyncio.get_running_loop()
            self._prune_task = loop.create_task(self._prune_loop())
        except RuntimeError:
            pass
        print("[MemoryBus] OK Started")

    async def stop(self) -> None:
        """Stop background pruning."""
        self._started = False
        if self._prune_task:
            self._prune_task.cancel()
            try:
                await self._prune_task
            except asyncio.CancelledError:
                pass
            self._prune_task = None
        print("[MemoryBus] OK Stopped")

    # ── Core CRUD ────────────────────────────────────────────────────

    async def store(
        self,
        key: str,
        value: str,
        category: str = "notes",
        source: str = "agent",
        tags: Optional[list[str]] = None,
        ttl_seconds: Optional[int] = DEFAULT_TTL_SECONDS,
    ) -> str:
        """Store a memory entry.

        Args:
            key: Short identifier (e.g. 'favorite_color', 'project_barq').
            value: The memory content.
            category: Category: identity, preferences, projects, etc.
            source: Who stored this ('agent', 'user', 'system').
            tags: Optional list of searchable tags.
            ttl_seconds: Time-to-live in seconds. None = forever.

        Returns:
            The memory ID.
        """
        memory_id = str(uuid.uuid4())[:12]
        tags_json = json.dumps(tags or [])
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now(timezone.utc).timestamp() + ttl_seconds

        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO memory_entries
                       (id, key, value, category, source, tags, expires_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        memory_id, key, value, category, source, tags_json,
                        expires_at,
                        datetime.now(timezone.utc).isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
        return memory_id

    async def get(self, memory_id: str) -> Optional[dict]:
        """Retrieve a specific memory by ID."""
        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM memory_entries WHERE id = ? AND (expires_at IS NULL OR expires_at > ?)",
                    (memory_id, time.time()),
                ).fetchone()
                return dict(row) if row else None

    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search across all memories using FTS5.

        Args:
            query: Search query (supports FTS5 syntax).
            category: Optional category filter.
            tags: Optional tag filter.
            limit: Max results.

        Returns:
            List of matching memory entries.
        """
        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row

                # Build query: FTS5 search + optional filters
                where_clauses = [
                    "e.expires_at IS NULL OR e.expires_at > ?",
                ]
                params: list[Any] = [time.time()]

                if category:
                    where_clauses.append("e.category = ?")
                    params.append(category)

                if tags:
                    # Search for entries whose tags JSON contains any of the tag values
                    tag_filters = " OR ".join(
                        "e.tags LIKE ?" for _ in tags
                    )
                    where_clauses.append(f"({tag_filters})")
                    params.extend(f"%{t}%" for t in tags)

                where = " AND ".join(where_clauses)

                # FTS5 MATCH doesn't work reliably in JOIN context — use subquery
                rows = conn.execute(
                    f"""SELECT e.* FROM memory_entries e
                        WHERE e._rowid_ IN (SELECT rowid FROM memory_fts WHERE memory_fts MATCH ?)
                          AND {where}
                        ORDER BY e.updated_at DESC
                        LIMIT ?""",
                    (query, *params, limit),
                ).fetchall()

                return [dict(r) for r in rows]

    async def recall(self, key: str, category: Optional[str] = None) -> Optional[str]:
        """Quick recall of a single memory value by key.

        Args:
            key: The memory key to look up.
            category: Optional category to narrow the search.

        Returns:
            The value string, or None if not found.
        """
        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                if category:
                    row = conn.execute(
                        "SELECT value FROM memory_entries WHERE key = ? AND category = ? "
                        "AND (expires_at IS NULL OR expires_at > ?) ORDER BY updated_at DESC LIMIT 1",
                        (key, category, time.time()),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT value FROM memory_entries WHERE key = ? "
                        "AND (expires_at IS NULL OR expires_at > ?) ORDER BY updated_at DESC LIMIT 1",
                        (key, time.time()),
                    ).fetchone()
                return row[0] if row else None

    async def remember(
        self, key: str, value: str, category: str = "notes"
    ) -> str:
        """Quick store with simple interface (matches agent_memory_manager style)."""
        return await self.store(key, value, category=category, source="agent")

    async def forget(self, key: str, category: Optional[str] = None) -> bool:
        """Delete a memory by key (and optionally category)."""
        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                if category:
                    cursor = conn.execute(
                        "DELETE FROM memory_entries WHERE key = ? AND category = ?",
                        (key, category),
                    )
                else:
                    cursor = conn.execute(
                        "DELETE FROM memory_entries WHERE key = ?",
                        (key,),
                    )
                conn.commit()
                return cursor.rowcount > 0

    async def list_by_category(self, category: str, limit: int = 50) -> list[dict]:
        """List all non-expired entries in a category."""
        async with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM memory_entries
                       WHERE category = ? AND (expires_at IS NULL OR expires_at > ?)
                       ORDER BY updated_at DESC LIMIT ?""",
                    (category, time.time(), limit),
                ).fetchall()
                return [dict(r) for r in rows]

    # ── Prompt Integration ───────────────────────────────────────────

    def format_for_prompt(self, category: Optional[str] = None) -> str:
        """Format stored memories into a string for LLM prompt injection.

        Args:
            category: Optional category filter.

        Returns:
            Formatted memory string, or empty if no memories.
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row

            if category:
                rows = conn.execute(
                    "SELECT key, value, category FROM memory_entries "
                    "WHERE category = ? AND (expires_at IS NULL OR expires_at > ?) "
                    "ORDER BY updated_at DESC LIMIT 30",
                    (category, time.time()),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key, value, category FROM memory_entries "
                    "WHERE expires_at IS NULL OR expires_at > ? "
                    "ORDER BY updated_at DESC LIMIT 50",
                    (time.time(),),
                ).fetchall()

        if not rows:
            return ""

        lines = ["[Memory — facts about the user]"]
        current_cat = ""
        for r in rows:
            if r["category"] != current_cat:
                current_cat = r["category"]
                lines.append(f"\n{current_cat.upper()}:")
            lines.append(f"  - {r['key']}: {r['value'][:200]}")

        result = "\n".join(lines)
        if len(result) > MEMORY_MAX_CHARS_PER_TYPE:
            result = result[: MEMORY_MAX_CHARS_PER_TYPE - 3] + "…"

        return result

    # ─── Bridge to Legacy Systems ────────────────────────────────────

    def load_legacy_memory(self) -> dict:
        """Load from the legacy long_term.json and merge into FTS5.

        This is a one-time migration helper for existing memory.
        """
        from .agent_memory_manager import load_memory as load_json_memory

        legacy = load_json_memory()
        count = 0
        for cat, items in legacy.items():
            if not isinstance(items, dict):
                continue
            for key, entry in items.items():
                value = ""
                if isinstance(entry, dict):
                    value = entry.get("value", "")
                else:
                    value = str(entry)
                if not value:
                    continue
                try:
                    with sqlite3.connect(self._db_path) as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO memory_entries "
                            "(id, key, value, category, source, tags, expires_at, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, 'legacy', '[]', NULL, ?, ?)",
                            (
                                f"legacy-{uuid.uuid4().hex[:8]}",
                                key, value[:500], cat,
                                datetime.now(timezone.utc).isoformat(),
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                        conn.commit()
                    count += 1
                except Exception:
                    pass
        return {"migrated": count, "categories": list(legacy.keys())}

    # ─── Stats ───────────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        """Get memory bus statistics."""
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM memory_entries WHERE expires_at IS NULL OR expires_at > ?",
                (time.time(),),
            ).fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) as cnt FROM memory_entries WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (time.time(),),
            ).fetchone()[0]
            categories = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM memory_entries GROUP BY category"
            ).fetchall()

        return {
            "total_active": total,
            "total_expired": expired,
            "categories": {r[0]: r[1] for r in categories},
            "fts5_enabled": True,
        }

    # ─── Internal ────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize the SQLite database with FTS5 support."""
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            # Main memory table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'notes',
                    source TEXT NOT NULL DEFAULT 'agent',
                    tags TEXT DEFAULT '[]',
                    expires_at REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Indexes for fast lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_key ON memory_entries(key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_entries(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_expires ON memory_entries(expires_at)
            """)

            # FTS5 virtual table for full-text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    key, value, category, tags,
                    content='memory_entries',
                    content_rowid='rowid',
                    tokenize='porter unicode61'
                )
            """)

            # Triggers to keep FTS in sync
            conn.executescript("""
                CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_entries BEGIN
                    INSERT INTO memory_fts(rowid, key, value, category, tags)
                    VALUES (new.rowid, new.key, new.value, new.category, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_entries BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, key, value, category, tags)
                    VALUES ('delete', old.rowid, old.key, old.value, old.category, old.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_entries BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, key, value, category, tags)
                    VALUES ('delete', old.rowid, old.key, old.value, old.category, old.tags);
                    INSERT INTO memory_fts(rowid, key, value, category, tags)
                    VALUES (new.rowid, new.key, new.value, new.category, new.tags);
                END;
            """)

            conn.commit()

    async def _prune_loop(self) -> None:
        """Background loop that prunes expired memories."""
        while self._started:
            await asyncio.sleep(3600)  # Check every hour
            try:
                with sqlite3.connect(self._db_path) as conn:
                    cursor = conn.execute(
                        "DELETE FROM memory_entries WHERE expires_at IS NOT NULL AND expires_at <= ?",
                        (time.time(),),
                    )
                    deleted = cursor.rowcount
                    conn.commit()
                    if deleted:
                        print(f"[MemoryBus] Pruned {deleted} expired memories")
            except Exception as e:
                print(f"[MemoryBus] Prune error: {e}")


# ─── Singleton ──────────────────────────────────────────────────────────────

_bus: Optional[MemoryBus] = None


def get_memory_bus() -> MemoryBus:
    """Get or create the global MemoryBus singleton."""
    global _bus
    if _bus is None:
        _bus = MemoryBus()
        _bus.start()
    return _bus
