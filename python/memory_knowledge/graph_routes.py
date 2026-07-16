"""
FastAPI routes for the BARQ Graph Brain — knowledge graph operations.

Provides endpoints to ingest text, query entities, traverse relationships,
and persist the graph to disk.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from graph_brain import graph_brain

logger = logging.getLogger("barq.graph_routes")
router = APIRouter(tags=["Graph Brain"])


# ─── Request / Response Models ───────────────────────────────────────────────

class IngestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Unstructured text to extract knowledge from")


class IngestResponse(BaseModel):
    status: str
    triplets_added: int
    total_nodes: int
    total_edges: int


class TripletAddRequest(BaseModel):
    subject: str = Field(..., min_length=1, description="Source entity")
    relation: str = Field(..., min_length=1, description="Relationship type (e.g. WORKS_AT)")
    object_: str = Field(..., alias="object", min_length=1, description="Target entity")

    class Config:
        populate_by_name = True


class TopEntitiesResponse(BaseModel):
    entities: list[dict[str, Any]]


class PathRequest(BaseModel):
    source: str = Field(..., min_length=1, description="Starting entity")
    target: str = Field(..., min_length=1, description="Target entity")


class PathResponse(BaseModel):
    found: bool
    path: list[str]
    edges: list[dict[str, Any]]
    length: int
    error: Optional[str] = None


class SaveLoadResponse(BaseModel):
    status: str
    path: str
    nodes: int = 0
    edges: int = 0


class GraphStatsResponse(BaseModel):
    nodes: int
    edges: int
    density: float
    connected_components: int
    top_entities: list[dict[str, Any]] = []


# ─── Ingestion Endpoints ────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(request: IngestRequest) -> dict[str, Any]:
    """Extract knowledge triplets from unstructured text and add them to the graph.

    Sends the text to the local Ollama LLM for triplet extraction, then
    populates the in-memory NetworkX graph.
    """
    try:
        count = graph_brain.add_knowledge(request.text)
        stats = graph_brain.get_statistics()
        return IngestResponse(
            status="ok",
            triplets_added=count,
            total_nodes=stats["nodes"],
            total_edges=stats["edges"],
        ).model_dump()
    except Exception as e:
        logger.error("Ingest failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/triplet", response_model=IngestResponse)
async def add_triplet(request: TripletAddRequest) -> dict[str, Any]:
    """Directly add a single triplet (subject, relation, object) to the graph.

    Useful for programmatic inserts without LLM inference.
    """
    try:
        graph_brain.add_triplet(
            subject=request.subject,
            relation=request.relation,
            object_=request.object_,
        )
        stats = graph_brain.get_statistics()
        return IngestResponse(
            status="ok",
            triplets_added=1,
            total_nodes=stats["nodes"],
            total_edges=stats["edges"],
        ).model_dump()
    except Exception as e:
        logger.error("Triplet add failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Query Endpoints ────────────────────────────────────────────────────────

@router.get("/top-entities", response_model=TopEntitiesResponse)
async def top_entities(limit: int = Query(default=5, ge=1, le=100)) -> dict[str, Any]:
    """Return the most central (best-connected) entities in the knowledge graph.

    Uses NetworkX's degree centrality to identify high-value nodes.
    """
    try:
        entities = graph_brain.get_top_entities(limit=limit)
        return TopEntitiesResponse(entities=entities).model_dump()
    except Exception as e:
        logger.error("top_entities failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/path", response_model=PathResponse)
async def relationship_path(request: PathRequest) -> dict[str, Any]:
    """Find the shortest path connecting two entities in the graph.

    Useful for discovering how disparate concepts (e.g. a tech trend and
    a company in the user's job queue) are connected.
    """
    try:
        result = graph_brain.find_relationship_path(
            source=request.source,
            target=request.target,
        )
        return result
    except Exception as e:
        logger.error("path query failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/neighbours")
async def neighbours(
    entity: str = Query(..., description="Entity to expand from"),
    depth: int = Query(default=1, ge=1, le=5),
) -> dict[str, Any]:
    """Get all entities connected to *entity*, up to *depth* hops away."""
    try:
        results = graph_brain.get_neighbours(entity=entity, depth=depth)
        return {"entity": entity, "depth": depth, "neighbours": results}
    except Exception as e:
        logger.error("neighbours query failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Persistence Endpoints ──────────────────────────────────────────────────

@router.post("/save", response_model=SaveLoadResponse)
async def save_graph(
    file_path: str = Query(default="data/graph.json", description="Destination file path"),
) -> dict[str, Any]:
    """Serialize the knowledge graph to a JSON file on disk."""
    try:
        stats = graph_brain.get_statistics()
        graph_brain.save_to_disk(file_path)
        return SaveLoadResponse(
            status="saved",
            path=file_path,
            nodes=stats["nodes"],
            edges=stats["edges"],
        ).model_dump()
    except Exception as e:
        logger.error("Save failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load", response_model=SaveLoadResponse)
async def load_graph(
    file_path: str = Query(default="data/graph.json", description="Source file path"),
) -> dict[str, Any]:
    """Rebuild the knowledge graph from a previously saved JSON file."""
    try:
        success = graph_brain.load_from_disk(file_path)
        if not success:
            raise HTTPException(status_code=404, detail=f"Graph file not found or invalid: {file_path}")
        stats = graph_brain.get_statistics()
        return SaveLoadResponse(
            status="loaded",
            path=file_path,
            nodes=stats["nodes"],
            edges=stats["edges"],
        ).model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Load failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear")
async def clear_graph() -> dict[str, str]:
    """Remove all nodes and edges from the in-memory graph."""
    try:
        graph_brain.clear()
        return {"status": "cleared"}
    except Exception as e:
        logger.error("Clear failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Statistics Endpoint ────────────────────────────────────────────────────

@router.get("/stats", response_model=GraphStatsResponse)
async def graph_statistics() -> dict[str, Any]:
    """Return aggregate statistics about the current knowledge graph."""
    try:
        stats = graph_brain.get_statistics()
        return stats
    except Exception as e:
        logger.error("Stats failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
