"""
BARQ Checkpoint Store — durable agent execution state (Plan-Act-Reflect support).

Persists in-progress agent plans and workflow runs to the ``agent_checkpoints``
table so long-running executions survive restarts. After a BARQ restart the
state can be loaded and the remaining steps resumed.

Usage:
    store = get_checkpoint_store()
    await store.save("agent:abc123", {"goal": ..., "plan": ..., "completed_steps": []})
    state = await store.load("agent:abc123")
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from database import db_connection

# Keys are namespaced per consumer: 'agent:<task_id>' / 'workflow:<run_id>'


class CheckpointStore:
    """Async SQLite-backed checkpoint persistence via the shared db_connection."""

    async def save(
        self,
        key: str,
        data: dict[str, Any],
        agent_type: str = "agent",
        status: str = "active",
    ) -> None:
        """Create or update a checkpoint (upsert by checkpoint_key)."""
        payload = json.dumps(data, ensure_ascii=False)
        await db_connection.execute(
            """
            INSERT INTO agent_checkpoints (checkpoint_key, agent_type, data, status, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(checkpoint_key) DO UPDATE SET
                data = excluded.data,
                status = excluded.status,
                agent_type = excluded.agent_type,
                updated_at = datetime('now')
            """,
            (key, agent_type, payload, status),
        )
        await db_connection.commit()

    async def load(self, key: str) -> Optional[dict[str, Any]]:
        """Load a checkpoint by key. Returns None if not found."""
        row = await db_connection.fetch_one(
            "SELECT data, status FROM agent_checkpoints WHERE checkpoint_key = ?",
            (key,),
        )
        if not row:
            return None
        try:
            data = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            data = {}
        data["_status"] = row["status"]
        data["_checkpoint_key"] = key
        return data

    async def delete(self, key: str) -> bool:
        """Delete a checkpoint. Returns True if one was removed."""
        count = await db_connection.delete(
            "DELETE FROM agent_checkpoints WHERE checkpoint_key = ?", (key,)
        )
        return count > 0

    async def list_checkpoints(self, agent_type: Optional[str] = None, limit: int = 50) -> list[dict]:
        """List recent checkpoints (newest first), including the raw data JSON."""
        if agent_type:
            rows = await db_connection.fetch_all(
                "SELECT checkpoint_key, agent_type, status, updated_at, data "
                "FROM agent_checkpoints WHERE agent_type = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (agent_type, limit),
            )
        else:
            rows = await db_connection.fetch_all(
                "SELECT checkpoint_key, agent_type, status, updated_at, data "
                "FROM agent_checkpoints ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]

    async def list_with_parsed_data(
        self, agent_type: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        """Like :meth:`list_checkpoints` but with each row's data JSON decoded into a dict."""
        rows = await self.list_checkpoints(agent_type=agent_type, limit=limit)
        for row in rows:
            try:
                row["data"] = json.loads(row.get("data") or "{}")
            except (json.JSONDecodeError, TypeError):
                row["data"] = {}
        return rows

    async def mark_complete(self, key: str) -> None:
        """Mark a checkpoint as complete (execution finished)."""
        await db_connection.execute(
            "UPDATE agent_checkpoints SET status = 'complete', updated_at = datetime('now') "
            "WHERE checkpoint_key = ?",
            (key,),
        )
        await db_connection.commit()


# ─── Singleton ─────────────────────────────────────────────────────────────

_store: Optional[CheckpointStore] = None


def get_checkpoint_store() -> CheckpointStore:
    """Get or create the global CheckpointStore singleton."""
    global _store
    if _store is None:
        _store = CheckpointStore()
    return _store


def new_task_key(prefix: str = "agent") -> str:
    """Generate a fresh checkpoint key (e.g. 'agent:8f3a2b1c')."""
    return f"{prefix}:{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
