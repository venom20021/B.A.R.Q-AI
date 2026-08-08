"""
BARQ SQL Tool-Use Skill (Tool-Use Pattern, execution-focused).

Gives the agent the ability to query BARQ's local SQLite memory bus
(``python/data/memory_bus.db``) for real-time state before responding:
stored memories, categories, recent entries, stats, etc.

Safety:
- READ-ONLY by default (``SQL_TOOL_READONLY=true``): only SELECT / WITH /
  EXPLAIN / PRAGMA (read-only pragmas) are allowed.
- Multi-statement injection is rejected.
- Blocking ``sqlite3`` I/O runs via ``asyncio.to_thread`` so the event
  loop is never blocked.

Usage:
    from agent.sql_tool import run_sql_query
    result = await run_sql_query("SELECT key, value FROM memory_entries LIMIT 5")
"""

import asyncio
import re
from pathlib import Path
from typing import Optional

# Statements that are allowed by default (read-only)
_READ_ONLY_PREFIXES = ("select", "with", "explain", "pragma", "values")
# Read-only PRAGMAs (database_info, table_info, index_list, etc.)
_READ_ONLY_PRAGMAS = {
    "database_list", "database_info", "table_info", "table_list", "index_info",
    "index_list", "index_xinfo", "foreign_key_list", "foreign_key_check",
    "collation_list", "function_list", "module_list", "pragma_list", "journal_mode",
    "page_size", "page_count", "freelist_count", "schema_version", "user_version",
    "application_id", "integrity_check", "quick_check", "compile_options",
    "optimize", "writable_schema", "mmap_size", "soft_heap_limit", "threads",
}
# The first token decides intent — anything else is rejected when read-only.
_BLOCKED_PREFIXES = ("insert", "update", "delete", "drop", "alter", "create",
                     "attach", "detach", "replace", "vacuum", "reindex", "grant", "revoke")

_QUERY_MAX_ROWS = 50


def _resolve_memory_db_path() -> str:
    """Locate the memory bus SQLite database file."""
    try:
        from memory.memory_bus import MEMORY_BUS_DB, get_memory_bus
        bus = get_memory_bus()
        return bus._db_path or str(Path(__file__).parent.parent / "data" / MEMORY_BUS_DB)
    except Exception:
        return str(Path(__file__).parent.parent / "data" / "memory_bus.db")


def _validate_query(query: str, readonly: bool = True) -> str:
    """Validate a SQL statement. Returns the normalized statement.

    Raises:
        ValueError: If the statement is unsafe or not read-only.
    """
    if not query or not query.strip():
        raise ValueError("Empty SQL query")

    # Reject multi-statement injection
    stripped = query.strip().rstrip(";")
    if ";" in stripped:
        raise ValueError("Multi-statement SQL is not allowed")

    first = re.match(r"\s*([a-zA-Z]+)", stripped)
    if not first:
        raise ValueError("Could not determine SQL statement type")
    keyword = first.group(1).lower()

    if readonly:
        if keyword in _BLOCKED_PREFIXES:
            raise ValueError(f"Write statement '{keyword}' is blocked (read-only mode)")
        if keyword == "pragma":
            # Reject pragma ASSIGNMENTS (e.g. journal_mode=WAL) — those write state
            if "=" in stripped:
                raise ValueError("PRAGMA writes are not allowed (read-only mode)")
            # Only allow read-only pragmas
            pragma_match = re.match(r"\s*pragma\s+([a-zA-Z_]+)", stripped, re.IGNORECASE)
            pragma_name = pragma_match.group(1).lower() if pragma_match else ""
            if pragma_name not in _READ_ONLY_PRAGMAS:
                raise ValueError(f"PRAGMA '{pragma_name or '?'}' is not allowed (read-only)")
        elif keyword not in _READ_ONLY_PREFIXES:
            raise ValueError(f"Statement type '{keyword}' is not allowed (read-only mode)")

    return stripped


def _execute_sql_blocking(query: str, limit: int = _QUERY_MAX_ROWS) -> str:
    """Run the validated query against the memory bus DB (BLOCKING — thread only)."""
    import sqlite3

    db_path = _resolve_memory_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        limited = rows[:limit]

        if not limited:
            return "Query returned 0 rows."

        # Column names from the cursor description
        cols = [d[0] for d in (cursor.description or [])]

        # Build a compact text table
        header = " | ".join(cols)
        lines = [header, "-" * min(len(header), 120)]
        for row in limited:
            cells = []
            for col in cols:
                val = row[col]
                if isinstance(val, bytes):
                    val = f"<{len(val)} bytes>"
                text = str(val)
                cells.append(text[:80])
            lines.append(" | ".join(cells))

        if len(rows) > limit:
            lines.append(f"... truncated ({len(rows)} total rows, showing {limit})")

        return "\n".join(lines)
    finally:
        conn.close()


async def run_sql_query(
    query: str,
    limit: int = _QUERY_MAX_ROWS,
    readonly: Optional[bool] = None,
) -> str:
    """Execute a read-only SQL query against BARQ's memory bus.

    Runs in ``asyncio.to_thread`` so blocking sqlite3 I/O never blocks
    the event loop (required for the async voice/agent pipelines).

    Args:
        query: A single SQL SELECT/WITH/EXPLAIN/read-only PRAGMA statement.
        limit: Maximum rows to return.
        readonly: Override the readonly gate (defaults to config).

    Returns:
        A formatted text representation of the result rows.

    Raises:
        ValueError: If the query is unsafe or multi-statement.
    """
    if readonly is None:
        from config import get_settings
        readonly = get_settings().sql_tool_readonly

    validated = _validate_query(query, readonly=readonly)
    return await asyncio.to_thread(_execute_sql_blocking, validated, limit)


async def memory_snapshot() -> str:
    """Return a compact real-time snapshot of the memory bus (no SQL needed).

    Useful as a tool-return for the agent before responding: counts per
    category + a few recent entries.
    """
    def _snapshot_blocking() -> str:
        import sqlite3
        db_path = _resolve_memory_db_path()
        conn = sqlite3.connect(db_path)
        try:
            cats = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM memory_entries "
                "WHERE expires_at IS NULL OR expires_at > ? GROUP BY category",
                (__import__("time").time(),),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM memory_entries "
                "WHERE expires_at IS NULL OR expires_at > ?",
                (__import__("time").time(),),
            ).fetchone()[0]
            recent = conn.execute(
                "SELECT key, value FROM memory_entries "
                "WHERE expires_at IS NULL OR expires_at > ? "
                "ORDER BY updated_at DESC LIMIT 5",
                (__import__("time").time(),),
            ).fetchall()
        finally:
            conn.close()

        parts = [f"Memory bus snapshot — {total} active entries"]
        for cat, cnt in cats:
            parts.append(f"  {cat}: {cnt}")
        if recent:
            parts.append("Recent:")
            for key, value in recent:
                parts.append(f"  - {key}: {value[:100]}")
        return "\n".join(parts)

    return await asyncio.to_thread(_snapshot_blocking)
