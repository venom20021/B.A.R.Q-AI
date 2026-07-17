"""
FastAPI routes for the BARQ Graph Migration.

Allows triggering the migration of old monolithic ``graph_brain`` data
into the domain-specific ``MultiBrainManager`` system, verifying the
current state of brain files, and running dry-run reports.

Endpoints
---------
- ``POST /migration/run``       — execute the migration (or dry-run)
- ``GET  /migration/verify``    — check current brain file state
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from memory_knowledge.migration import MigrationRunner

logger = logging.getLogger("barq.migration_routes")
router = APIRouter(prefix="/migration", tags=["Graph Migration"])


# ─── Run Migration ──────────────────────────────────────────────────────────


@router.post("/run")
async def run_migration(
    dry_run: bool = Query(default=False, description="If true, report only without writing"),
    source_path: Optional[str] = Query(default=None, description="Override source graph.json path"),
) -> dict[str, Any]:
    """Execute the graph data migration from old monolithic format to
    domain-specific multi-brain files.

    Reads the legacy ``data/graph.json``, extracts all triplets, routes
    each to the most appropriate brain using keyword heuristics, clears
    all existing brains, inserts the routed triplets, and persists each
    brain to ``data/brains/{brain_type}.json``.

    The old graph is backed up to ``data/migration_backups/`` before any
    changes are made.

    Parameters
    ----------
    dry_run : bool
        If True, only report what would happen without modifying any data.
    source_path : str, optional
        Override the source graph.json file path.

    Returns
    -------
    dict
        Migration result with per-brain triplet counts and any errors.
    """
    try:
        runner = MigrationRunner(source_path=source_path)
        result = runner.run(dry_run=dry_run)
        return result
    except Exception as e:
        logger.error("[Migration] Route failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Verify ─────────────────────────────────────────────────────────────────


@router.get("/verify")
async def verify_migration() -> dict[str, Any]:
    """Verify the current state of brain files created by migration.

    Checks that all expected brain JSON files exist in the brains
    directory and reports node/edge counts per brain.
    """
    try:
        runner = MigrationRunner()
        return runner.verify()
    except Exception as e:
        logger.error("[Migration] Verify failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
