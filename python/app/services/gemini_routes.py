"""
FastAPI routes for the Gemini File Watcher — status, manual ingestion trigger,
and watcher lifecycle control.

Allows the frontend (or API clients) to interact with the background Gemini
chat history ingestion service.

Endpoints
---------
- ``POST /gemini/trigger``             — process all existing files now
- ``POST /gemini/trigger/file``        — process a specific file by path
- ``GET  /gemini/status``              — check watcher status & extractor stats
- ``POST /gemini/watcher/start``       — start the background file watcher
- ``POST /gemini/watcher/stop``        — stop the background file watcher
- ``GET  /gemini/extractor/stats``     — get triplet extractor statistics
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.gemini_watcher import (
    GeminiFileWatcher,
    GeminiTripletExtractor,
    get_extractor,
    get_gemini_watcher,
)

logger = logging.getLogger("barq.gemini_routes")
router = APIRouter(prefix="/gemini", tags=["Gemini File Watcher"])

# ─── Global monitor instance (set by main.py on startup) ────────────────────

_monitor: Optional[GeminiFileWatcher] = None


def set_monitor(monitor: GeminiFileWatcher) -> None:
    """Set the global monitor instance (called from main.py startup)."""
    global _monitor
    _monitor = monitor


# ─── Request Models ─────────────────────────────────────────────────────────


class TriggerFileRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or project-relative path to a Gemini chat file")


# ─── Trigger Ingestion ──────────────────────────────────────────────────────


@router.post("/trigger")
async def trigger_ingestion() -> dict[str, Any]:
    """Process all existing files in the watch directory immediately.

    Returns the total number of triplets added and per-file breakdown.
    The watcher does not need to be running for this to work.
    """
    try:
        watcher = _monitor or get_gemini_watcher()
        total = watcher.process_all_existing()
        logger.info("[GeminiRoutes] Manual trigger: %d triplets added", total)
        return {
            "status": "completed",
            "total_triplets": total,
            "brain_type": "ai_chats",
        }
    except Exception as e:
        logger.error("[GeminiRoutes] Trigger failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/file")
async def trigger_file(request: TriggerFileRequest) -> dict[str, Any]:
    """Process a single Gemini chat history file by path.

    The path can be absolute or relative to the project root.
    The file is processed through the full pipeline: parse → Ollama → graph.
    The file is deleted on success, renamed to ``.failed`` on error.
    """
    # Resolve the file path
    file_path = request.file_path
    path = Path(file_path)

    if not path.is_absolute():
        # Try resolving relative to the project root
        project_root = Path(__file__).resolve().parent.parent.parent
        path = project_root / file_path

    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {file_path}",
        )

    # Check file extension
    if path.suffix.lower() not in (".json", ".html", ".htm", ".txt", ".md"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {path.suffix}. "
            f"Supported: .json, .html, .htm, .txt, .md",
        )

    try:
        watcher = _monitor or get_gemini_watcher()
        count = watcher._process_file(str(path.resolve()))
        logger.info(
            "[GeminiRoutes] File trigger: %s → %d triplets",
            path.name,
            count,
        )
        return {
            "status": "completed",
            "file": str(path),
            "file_name": path.name,
            "triplets_added": count,
            "brain_type": "ai_chats",
        }
    except Exception as e:
        logger.error("[GeminiRoutes] File trigger failed for %s: %s", file_path, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Watcher Control ────────────────────────────────────────────────────────


@router.post("/watcher/start")
async def start_watcher() -> dict[str, Any]:
    """Start the background Gemini file watcher.

    The watcher monitors ``data/ingest/ai_chats/`` for new files.
    Uses ``watchdog`` for instant notifications (if installed) or async
    polling as a fallback.
    """
    if _monitor is None:
        raise HTTPException(status_code=503, detail="Watcher not initialised")

    _monitor.start()
    return {
        "status": "started",
        "is_running": _monitor.is_running,
        "mode": _monitor.mode,
    }


@router.post("/watcher/stop")
async def stop_watcher() -> dict[str, Any]:
    """Stop the background Gemini file watcher."""
    if _monitor is None:
        raise HTTPException(status_code=503, detail="Watcher not initialised")

    _monitor.stop()
    return {
        "status": "stopped",
        "is_running": _monitor.is_running,
    }


# ─── Status ─────────────────────────────────────────────────────────────────


@router.get("/status")
async def gemini_status() -> dict[str, Any]:
    """Return the current state of the Gemini file watcher.

    Includes:
    - Watcher running state and mode (watchdog or polling)
    - Watch directory path
    - Brain type being populated
    - Extractor statistics
    - Dependency availability (watchdog, beautifulsoup)
    """
    try:
        watcher = _monitor or get_gemini_watcher()
        stats = watcher.get_stats()

        return {
            "watcher_running": _monitor.is_running if _monitor else False,
            "watcher_available": _monitor is not None,
            "mode": stats["mode"],
            "watch_dir": stats["watch_dir"],
            "brain_type": stats["brain_type"],
            "has_watchdog": stats["has_watchdog"],
            "has_beautifulsoup": stats["has_beautifulsoup"],
            "extractor": stats["extractor"],
        }
    except Exception as e:
        logger.error("[GeminiRoutes] Status check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Extractor Stats ────────────────────────────────────────────────────────


@router.get("/extractor/stats")
async def extractor_stats() -> dict[str, Any]:
    """Return Gemini triplet extractor statistics.

    Includes total prompts processed, total triplets extracted,
    Ollama host and model, and the last error message (if any).
    """
    try:
        extractor = get_extractor()
        return extractor.stats
    except Exception as e:
        logger.error("[GeminiRoutes] Extractor stats failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
