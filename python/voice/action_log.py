"""
BARQ Action Log — Transparent record of every AI-executed system action.
Provides a floating feed of commands the AI has executed, with severity,
timestamps, and auto-pruning of old entries (max 200).
"""

import json
from typing import Any, Optional

from database import db_connection

# ─── Severity levels ────────────────────────────────────────────────────────

INFO = "info"
WARNING = "warning"
DANGER = "danger"


async def log_action(
    action: str,
    description: str,
    severity: str = INFO,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """Log an AI-executed action to the action_log table.

    Args:
        action: Short action name (e.g. "run_command", "launch_app")
        description: Human-readable description
        severity: One of "info", "warning", "danger"
        metadata: Optional structured data (command, target, etc.)

    Returns:
        The ID of the inserted log entry.
    """
    import json as _json
    meta_json = _json.dumps(metadata or {})
    row_id = await db_connection.insert(
        """INSERT INTO action_log (action, description, severity, metadata, created_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        (action, description, severity, meta_json),
    )
    # Prune old entries (keep latest 200)
    await db_connection.execute(
        "DELETE FROM action_log WHERE id NOT IN (SELECT id FROM action_log ORDER BY id DESC LIMIT 200)"
    )
    return row_id


async def get_recent_actions(limit: int = 20) -> list[dict[str, Any]]:
    """Get the most recent logged actions.

    Args:
        limit: Max entries to return (default 20, max 100).

    Returns:
        List of action log entries with id, action, description, severity, created_at.
    """
    limit = min(limit, 100)
    rows = await db_connection.fetch_all(
        "SELECT id, action, description, severity, metadata, created_at "
        "FROM action_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    result = []
    for row in rows:
        entry = dict(row)
        if isinstance(entry.get("metadata"), str):
            try:
                entry["metadata"] = json.loads(entry["metadata"])
            except (json.JSONDecodeError, TypeError):
                entry["metadata"] = {}
        result.append(entry)
    return result
