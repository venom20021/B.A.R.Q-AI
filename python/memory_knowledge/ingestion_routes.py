"""
FastAPI routes for the BARQ Ingestion Pipeline.

Allows the frontend (or API clients) to trigger ingestion actions and
check the status of the drop-folder watcher.

Endpoints
---------
- ``POST /ingestion/trigger``          — process all files in drop-folders now
- ``POST /ingestion/trigger/{brain}``  — process files for a specific brain
- ``GET  /ingestion/status``           — check watcher & extractor status
- ``POST /ingestion/watcher/start``    — start the folder watcher
- ``POST /ingestion/watcher/stop``     — stop the folder watcher
- ``GET  /ingestion/extractor/stats``  — get extractor statistics
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from memory_knowledge.ingestion import (
    BRAIN_FOLDER_MAP,
    DropFolderMonitor,
    TripletExtractor,
    get_extractor,
    run_ingestion_once,
)
from memory_knowledge.multi_brain import BRAIN_REGISTRY

logger = logging.getLogger("barq.ingestion_routes")
router = APIRouter(prefix="/ingestion", tags=["Ingestion Pipeline"])

# ─── Global monitor instance (set by main.py on startup) ────────────────────

_monitor: Optional[DropFolderMonitor] = None


def set_monitor(monitor: DropFolderMonitor) -> None:
    """Set the global monitor instance (called from main.py startup)."""
    global _monitor
    _monitor = monitor


# ─── Trigger Ingestion ──────────────────────────────────────────────────────


@router.post("/trigger")
async def trigger_ingestion() -> dict[str, Any]:
    """Process all files in all drop-folders immediately.

    Returns a dict mapping each brain type to the number of triplets added.
    """
    try:
        results = run_ingestion_once()
        total = sum(results.values())
        logger.info("[Ingestion] Triggered: %d triplets from %d brains", total, len(results))
        return {
            "status": "completed",
            "brains": results,
            "total_triplets": total,
            "brains_affected": len([v for v in results.values() if v > 0]),
        }
    except Exception as e:
        logger.error("[Ingestion] Trigger failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/{brain_type}")
async def trigger_ingestion_brain(brain_type: str) -> dict[str, Any]:
    """Process files in the drop-folder for *brain_type* only.

    Raises 404 if *brain_type* is not a registered brain.
    """
    if brain_type not in BRAIN_FOLDER_MAP:
        available = list(BRAIN_FOLDER_MAP.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown brain type '{brain_type}'. Available: {', '.join(available)}",
        )

    try:
        results = run_ingestion_once(brain_type=brain_type)
        count = results.get(brain_type, 0)
        return {
            "status": "completed",
            "brain_type": brain_type,
            "triplets_added": count,
        }
    except Exception as e:
        logger.error("[Ingestion] Trigger for '%s' failed: %s", brain_type, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Watcher Control ────────────────────────────────────────────────────────


@router.post("/watcher/start")
async def start_watcher() -> dict[str, str]:
    """Start the drop-folder file watcher.

    Returns the watcher status.  If ``watchdog`` is not installed,
    returns an explanatory message without error.
    """
    if _monitor is None:
        raise HTTPException(status_code=503, detail="Watcher not initialised")

    _monitor.start()
    return {"status": "started", "is_running": str(_monitor.is_running)}


@router.post("/watcher/stop")
async def stop_watcher() -> dict[str, str]:
    """Stop the drop-folder file watcher."""
    if _monitor is None:
        raise HTTPException(status_code=503, detail="Watcher not initialised")

    _monitor.stop()
    return {"status": "stopped", "is_running": str(_monitor.is_running)}


# ─── Status ─────────────────────────────────────────────────────────────────


@router.get("/status")
async def ingestion_status() -> dict[str, Any]:
    """Return the current state of the ingestion pipeline.

    Includes watcher status, extractor stats, registered brain types,
    and the drop-box directory path.
    """
    try:
        extractor = get_extractor()

        from memory_knowledge.ingestion import get_dropbox_base

        dropbox = get_dropbox_base()

        return {
            "watcher_running": _monitor.is_running if _monitor else False,
            "watcher_available": _monitor is not None,
            "dropbox_directory": dropbox,
            "registered_brains": list(BRAIN_REGISTRY.keys()),
            "extractor": extractor.stats,
        }
    except Exception as e:
        logger.error("[Ingestion] Status check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Extractor Stats ────────────────────────────────────────────────────────


@router.get("/extractor/stats")
async def extractor_stats() -> dict[str, Any]:
    """Return triplet extractor statistics.

    Includes total documents processed, total triplets extracted,
    and the last error message (if any).
    """
    try:
        extractor = get_extractor()
        return extractor.stats
    except Exception as e:
        logger.error("[Ingestion] Extractor stats failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
