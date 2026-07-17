"""
Multi-Brain Visualization API — serialises domain-specific NetworkX knowledge
graphs for the React force-directed graph frontend.

Each brain type (``apple_notes``, ``google_docs``, ``ai_chats``, ``career``,
``general``) has its own isolated ``nx.Graph()`` instance with a distinct
colour theme used by the frontend for visual differentiation.

Uses ``networkx.node_link_data`` with ``edges="links"`` so the JSON output
contains top-level ``nodes`` and ``links`` arrays that
``react-force-graph-2d`` expects natively.

Endpoints
---------
- ``GET /api/brain/list``                     — list all brains with metadata
- ``GET /api/brain/{brain_type}/visualize``   — full graph in node-link format
- ``GET /api/brain/{brain_type}/stats``       — per-brain network statistics
- ``GET /api/brain/visualize``                — (legacy) defaults to ``general``
- ``GET /api/brain/timeline``                 — combined timeline for all brains
- ``GET /api/brain/{brain_type}/timeline``    — timeline for a specific brain
- ``GET /api/brain/timeline/summary``         — per-brain activity summary
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from memory_knowledge.multi_brain import BRAIN_REGISTRY, multi_brain_manager

logger = logging.getLogger("barq.brain_api")
router = APIRouter(prefix="/api/brain", tags=["Brain Visualisation"])

# ═══════════════════════════════════════════════════════════════════════════
#  IMPORTANT: Static routes MUST be registered BEFORE parameterised routes
#  so that /list and /visualize are not captured by /{brain_type}/...
# ═══════════════════════════════════════════════════════════════════════════

# ─── List Brains (static) ────────────────────────────────────────────────────


@router.get("/list")
async def list_brains() -> list[dict[str, Any]]:
    """Return metadata for all registered brains with live node/edge counts.

    Each entry includes the brain type, label, description, colour theme,
    icon, and current graph size.  The frontend uses this to build the
    tabbed navigation header.
    """
    try:
        return multi_brain_manager.list_brains()
    except Exception as e:
        logger.error("list_brains failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Legacy Endpoint (static — defaults to ``general``) ─────────────────────


@router.get("/visualize")
async def visualize_brain_legacy() -> dict[str, Any]:
    """Legacy: return the ``general`` brain in node-link format.

    This endpoint exists so existing frontend references to
    ``/api/brain/visualize`` continue to work until they are migrated
    to the domain-specific ``/api/brain/{brain_type}/visualize``.
    """
    try:
        return multi_brain_manager.visualize("general")
    except Exception as e:
        logger.error("Legacy visualize failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Timeline / History (static) ────────────────────────────────────────────


@router.get("/timeline")
async def get_timeline_all(
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return the combined timeline for all brains, newest first.

    Parameters
    ----------
    limit : int
        Maximum number of entries to return (default 50).
    offset : int
        Number of entries to skip for pagination (default 0).

    Returns
    -------
    list
        Chronologically ordered timeline entries with timestamp, brain type,
        subject, relation, and object fields.
    """
    try:
        return multi_brain_manager.get_timeline(limit=limit, offset=offset)
    except Exception as e:
        logger.error("get_timeline_all failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline/summary")
async def get_timeline_summary() -> list[dict[str, Any]]:
    """Return per-brain activity summary for the timeline.

    Each entry includes total events, new edges count, and latest timestamp
    for each brain that has any timeline entries.

    Returns
    -------
    list
        Per-brain activity summaries, sorted by most recent activity first.
    """
    try:
        return multi_brain_manager.get_timeline_summary()
    except Exception as e:
        logger.error("get_timeline_summary failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════
#  Parameterised routes — MUST come after all static routes
# ═══════════════════════════════════════════════════════════════════════════

# ─── Visualize ───────────────────────────────────────────────────────────────


@router.get("/{brain_type}/visualize")
async def visualize_brain(brain_type: str) -> dict[str, Any]:
    """Return the knowledge graph for *brain_type* in node-link format.

    The response has the shape:
    ``{"nodes": [...], "links": [...], "_meta": {...}}``

    This matches the schema that ``react-force-graph-2d`` consumes directly.

    Parameters
    ----------
    brain_type : str
        One of the registered brain types (e.g. ``"ai_chats"``, ``"career"``).

    Raises
    ------
    404
        If *brain_type* is not a registered brain.
    """
    if not multi_brain_manager.is_valid_brain(brain_type):
        available = list(BRAIN_REGISTRY.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown brain type '{brain_type}'. Available: {', '.join(available)}",
        )

    try:
        return multi_brain_manager.visualize(brain_type)
    except Exception as e:
        logger.error("visualize_brain(%s) failed: %s", brain_type, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Statistics ──────────────────────────────────────────────────────────────


@router.get("/{brain_type}/timeline")
async def get_brain_timeline(
    brain_type: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return the timeline for a specific brain, newest first.

    Parameters
    ----------
    brain_type : str
        Which brain's timeline to retrieve.
    limit : int
        Maximum number of entries to return (default 50).
    offset : int
        Number of entries to skip for pagination (default 0).

    Raises
    ------
    404
        If *brain_type* is not a registered brain.
    """
    if not multi_brain_manager.is_valid_brain(brain_type):
        available = list(BRAIN_REGISTRY.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown brain type '{brain_type}'. Available: {', '.join(available)}",
        )

    try:
        return multi_brain_manager.get_timeline(
            brain_type=brain_type, limit=limit, offset=offset
        )
    except Exception as e:
        logger.error("get_brain_timeline(%s) failed: %s", brain_type, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{brain_type}/stats")
async def brain_statistics(brain_type: str) -> dict[str, Any]:
    """Return aggregate network statistics for a specific brain.

    Includes node/edge counts, density, number of connected components,
    and the top 5 most central entities with degree centrality scores.

    Parameters
    ----------
    brain_type : str
        Which brain to inspect (e.g. ``"career"``).

    Raises
    ------
    404
        If *brain_type* is not a registered brain.
    """
    if not multi_brain_manager.is_valid_brain(brain_type):
        available = list(BRAIN_REGISTRY.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown brain type '{brain_type}'. Available: {', '.join(available)}",
        )

    try:
        return multi_brain_manager.get_statistics(brain_type)
    except Exception as e:
        logger.error("brain_statistics(%s) failed: %s", brain_type, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


