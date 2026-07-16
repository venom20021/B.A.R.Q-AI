"""
Brain Visualization API — serialises the NetworkX knowledge graph for the
React force-directed graph frontend.

Uses ``networkx.node_link_data`` with ``edges="links"`` so the JSON output
contains top-level ``nodes`` and ``links`` arrays that
``react-force-graph-2d`` expects natively.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from networkx.readwrite import json_graph

from graph_brain import graph_brain

logger = logging.getLogger("barq.brain_api")
router = APIRouter(prefix="/api/brain", tags=["Brain Visualisation"])


@router.get("/visualize")
async def visualize_brain() -> dict[str, Any]:
    """Return the full knowledge graph in node-link format for the frontend.

    The response has the shape:
    ``{"nodes": [{"id": str, "label": str, ...}], "links": [{"source": str, "target": str, "relation": str, "weight": int}]}``

    This matches the schema that ``react-force-graph-2d`` consumes directly.
    """
    try:
        with graph_brain._graph_lock:
            graph = graph_brain.graph
            data: dict[str, Any] = json_graph.node_link_data(graph, edges="links")

        # Ensure standard shape even for an empty graph
        data.setdefault("nodes", [])
        data.setdefault("links", [])

        # Add metadata in a separate top-level key so the frontend can show stats
        data["_meta"] = {
            "nodes": len(data["nodes"]),
            "edges": len(data["links"]),
        }

        return data
    except Exception as e:
        logger.error("Brain visualise failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
