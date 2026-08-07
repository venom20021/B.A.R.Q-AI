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

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from memory_knowledge.multi_brain import BRAIN_REGISTRY, multi_brain_manager

logger = logging.getLogger("barq.brain_api")
router = APIRouter(prefix="/api/brain", tags=["Brain Visualisation"])
# ─── Entity image history (static) ─────────────────────────────────────────


class EntityImageSave(BaseModel):
    "Payload for persisting a generated entity image to the brain."

    brain_id: str = 'general'
    entity: str
    prompt: str = ''
    image_url: str


class EntityImageDelete(BaseModel):
    "Payload for removing a saved entity image."

    id: int


@router.post("/images")
async def save_entity_image(request: EntityImageSave) -> dict[str, Any]:
    "Persist a generated entity image so it survives restarts."
    try:
        from database.connection import db_connection

        image_id = await db_connection.insert(
            'INSERT INTO entity_images (brain_id, entity, prompt, image_url) VALUES (?, ?, ?, ?)',
            (request.brain_id, request.entity, request.prompt, request.image_url),
        )
        return {'id': image_id, 'brain_id': request.brain_id, 'entity': request.entity}
    except Exception as e:
        logger.error('save_entity_image failed: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/images")
async def list_entity_images(brain_id: str = '', entity: str = '') -> dict[str, Any]:
    "List saved images for a brain/entity, newest first."
    try:
        from database.connection import db_connection

        sql = (
            'SELECT id, brain_id, entity, prompt, image_url, created_at '
            'FROM entity_images WHERE 1=1'
        )
        params: list[str] = []
        if brain_id:
            sql += ' AND brain_id = ?'
            params.append(brain_id)
        if entity:
            sql += ' AND entity = ?'
            params.append(entity)
        sql += ' ORDER BY id DESC LIMIT 100'
        rows = await db_connection.fetch_all(sql, tuple(params))
        return {'items': rows, 'count': len(rows)}
    except Exception as e:
        logger.error('list_entity_images failed: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/images/delete")
async def delete_entity_image(request: EntityImageDelete) -> dict[str, Any]:
    "Remove a saved entity image by id."
    try:
        from database.connection import db_connection

        deleted = await db_connection.delete(
            'DELETE FROM entity_images WHERE id = ?',
            (request.id,),
        )
        return {'deleted': deleted}
    except Exception as e:
        logger.error('delete_entity_image failed: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/{brain_type}/node/{entity}")
async def get_node_details(brain_type: str, entity: str) -> dict[str, Any]:
    """Return a single node's neighbours and connectivity stats.

    Used by the Knowledge Graph details panel that opens when a node is
    clicked.  The entity is matched case-insensitively and must exist in the
    brain's graph.

    Parameters
    ----------
    brain_type : str
        Which brain to inspect (e.g. ``"career"``).
    entity : str
        The entity name to expand (URL-encoded).

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
        return multi_brain_manager.get_node_details(brain_type, entity)
    except Exception as e:
        logger.error("get_node_details(%s, %s) failed: %s", brain_type, entity, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{brain_type}/node/{entity}/remove")
async def remove_node_from_brain(brain_type: str, entity: str) -> dict[str, Any]:
    """Remove a single entity (node + all its edges) from a brain.

    Used by the "Remove entity" action in the Knowledge Graph details panel.
    The entity is matched case-insensitively.  POST is used rather than
    DELETE because the Electron bridge's ``python.request`` only issues
    GET/POST (body presence decides) — matching every other brain mutation
    (``/triplet``, ``/clear``, ``/ingest``).

    Parameters
    ----------
    brain_type : str
        Which brain to edit.
    entity : str
        The entity name to remove (URL-encoded).

    Returns
    -------
    Dict with ``found`` / ``removed_edges`` / ``removed_timeline_entries``
    and the brain's updated ``nodes`` / ``edges`` counts.

    Raises
    ------
    404
        If *brain_type* is not a registered brain.
    """
    if not multi_brain_manager.is_valid_brain(brain_type):
        raise HTTPException(status_code=404, detail=f"Unknown brain type '{brain_type}'")

    try:
        result = multi_brain_manager.remove_entity(brain_type, entity)
        if result["found"]:
            multi_brain_manager.save_brain(brain_type)
            multi_brain_manager.save_timeline()
        stats = multi_brain_manager.get_statistics(brain_type)
        result["nodes"] = stats["nodes"]
        result["edges"] = stats["edges"]
        return result
    except Exception as e:
        logger.error("remove_node_from_brain(%s, %s) failed: %s", brain_type, entity, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════
#  Mutation endpoints — ingest / triplet / clear / save / seed / import.
#  These let the Knowledge Graph page populate the multi-brain graphs it
#  displays (the legacy ``/graph/ingest`` route writes to a *different*
#  graph, which is why the page used to stay empty).
# ═══════════════════════════════════════════════════════════════════════════


class IngestTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Unstructured text to mine for triplets")


class TripletAddRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subject: str = Field(..., min_length=1, description="Source entity")
    relation: str = Field(..., min_length=1, description="Relationship type (e.g. WORKS_AT)")
    object_: str = Field(..., alias="object", min_length=1, description="Target entity")


# ─── Shared helpers ────────────────────────────────────────────────────────


# Gemini models are frequently deprecated/renamed, so the extraction model is
# configurable (GEMINI_MODEL env var) and falls back through a verified list.
GEMINI_EXTRACTION_MODEL = os.getenv(
    "GEMINI_MODEL", "gemini-3.1-flash-lite"
)
GEMINI_MODEL_FALLBACKS = [
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
]


def _extract_triplets_ollama(text: str) -> list[tuple[str, str, str]]:
    """Real relationship extraction via the local Ollama LLM.

    Reuses the legacy ``graph_brain`` extractor (``/api/generate`` with JSON
    mode).  Returns ``[]`` when Ollama is unreachable or extracts nothing.
    """
    try:
        from graph_brain import graph_brain
        return graph_brain.extract_triplets(text)
    except Exception as e:
        logger.warning("Ollama triplet extraction unavailable: %s", e)
        return []


def _extract_triplets_gemini(text: str) -> list[tuple[str, str, str]]:
    """Real relationship extraction via Google Gemini (google-genai SDK).

    Uses the same extraction prompt as the Ollama path with
    ``response_mime_type="application/json"`` so Gemini returns a clean JSON
    triplet array.  The API key is resolved the same way as the vision module
    (``config/api_keys.json`` → env → ``.env``).  Returns ``[]`` on any failure
    so the provider chain degrades gracefully.
    """
    if not text or not text.strip():
        return []

    try:
        from agent.vision import _load_gemini_api_key
        api_key = _load_gemini_api_key()
    except Exception as e:
        logger.warning("Gemini extraction skipped (no API key): %s", e)
        return []
    if not api_key:
        return []

    try:
        from google import genai
        from google.genai import types as genai_types
        from graph_brain import EXTRACTION_SYSTEM_PROMPT, graph_brain

        client = genai.Client(api_key=api_key)
        models_to_try = [GEMINI_EXTRACTION_MODEL, *GEMINI_MODEL_FALLBACKS]
        response = None
        last_err: Exception | None = None
        for model in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=text.strip()[:4000],
                    config=genai_types.GenerateContentConfig(
                        system_instruction=EXTRACTION_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        temperature=0.1,
                        top_p=0.9,
                    ),
                )
                break
            except Exception as e:  # 404 (model deprecated) or quota errors
                last_err = e
                logger.warning("Gemini model %s failed: %s", model, str(e)[:120])
        if response is None:
            raise last_err or RuntimeError("No Gemini model available")
        raw = (response.text or "").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            logger.warning("Gemini response is not a JSON array: %s …", raw[:200])
            return []

        triplets: list[tuple[str, str, str]] = []
        for item in parsed:
            if not isinstance(item, list) or len(item) != 3:
                continue
            subj = graph_brain._normalize_entity(str(item[0]))
            obj = graph_brain._normalize_entity(str(item[2]))
            rel = str(item[1]).strip().upper().replace(" ", "_") or "RELATED_TO"
            if subj and obj:
                triplets.append((subj, rel, obj))
        return triplets
    except Exception as e:
        logger.warning("Gemini triplet extraction failed: %s", e)
        return []


async def extract_triplets_with_provider(
    text: str,
) -> tuple[list[tuple[str, str, str]], str]:
    """Real LLM relationship extraction with a provider chain.

    Tries the local Ollama LLM first (no network cost, private).  If Ollama
    returns nothing, falls back to Google Gemini (requires ``GEMINI_API_KEY``).
    Returns ``(triplets, provider)`` where provider is ``"ollama"``, ``"gemini"``
    or ``"none"`` — so callers can report exactly which engine produced the
    relationships instead of silently returning an empty graph.
    """
    if not text or not text.strip():
        return [], "none"

    # Tier 1: local Ollama (its httpx client self-times-out at ~60s, but we cap
    # the whole step so a stuck server never pins a threadpool worker).
    try:
        triplets = await asyncio.wait_for(
            asyncio.to_thread(_extract_triplets_ollama, text), timeout=40
        )
        if triplets:
            return triplets, "ollama"
    except Exception as e:
        logger.warning("Ollama extraction step failed: %s", e)

    # Tier 2: Google Gemini (SDK default timeout is very long — cap it here).
    try:
        triplets = await asyncio.wait_for(
            asyncio.to_thread(_extract_triplets_gemini, text), timeout=45
        )
        if triplets:
            return triplets, "gemini"
    except Exception as e:
        logger.warning("Gemini extraction step failed: %s", e)

    return [], "none"


def _brain_stats_dict(brain_type: str) -> dict[str, Any]:
    stats = multi_brain_manager.get_statistics(brain_type)
    return {"nodes": stats["nodes"], "edges": stats["edges"]}


def _seed_demo_core() -> dict[str, int]:
    """Populate every empty brain with a small starter knowledge graph (no LLM)."""
    DEMO_SEED: dict[str, list[tuple[str, str, str]]] = {
        "general": [
            ("barq", "is_a", "ai assistant"),
            ("barq", "supports", "voice control"),
            ("barq", "automates", "job search"),
            ("barq", "automates", "social media"),
            ("barq", "builds", "knowledge graph"),
        ],
        "ai_chats": [
            ("assistant", "uses", "gemini"),
            ("assistant", "uses", "deepgram"),
            ("assistant", "manages", "conversations"),
        ],
        "career": [
            ("career engine", "tracks", "job applications"),
            ("career engine", "matches", "skills"),
            ("career engine", "generates", "cover letters"),
        ],
        "apple_notes": [
            ("apple notes", "stores", "notes"),
            ("notes", "contain", "knowledge"),
        ],
        "google_docs": [
            ("google docs", "stores", "documents"),
            ("documents", "contain", "knowledge"),
        ],
        "gemini_chats": [
            ("gemini", "powers", "chat conversations"),
            ("gemini", "analyzes", "images"),
        ],
    }
    added: dict[str, int] = {}
    for brain_type, triplets in DEMO_SEED.items():
        graph = multi_brain_manager.get_brain(brain_type)
        if graph.number_of_nodes() > 0:
            added[brain_type] = 0
            continue
        count = 0
        for subj, rel, obj in triplets:
            multi_brain_manager.add_triplet(brain_type, subj, rel, obj)
            count += 1
        added[brain_type] = count
        multi_brain_manager.save_brain(brain_type)
    multi_brain_manager.save_timeline()
    return added


async def _import_direct_sources() -> dict[str, int]:
    """Import real BARQ data into brains without requiring the LLM.

    Notes → ``(title, about, first sentence)`` triplets in the general brain.
    Long-term memory → ``(key, contains, value summary)`` triplets.
    Jobs table (when present) → ``(company, hiring_for, title)`` in the career brain.
    AI conversations (agent chat history, memory-bus facts, voice session
    summaries) → ``(topic, ASKED_ABOUT/DISCUSSED_AS, …)`` triplets in the
    ``ai_chats`` brain — so the AI Chat graph always has real content.
    """
    added: dict[str, int] = {}

    # ── Notes → general brain ────────────────────────────────────────────
    try:
        from database.connection import db_connection
        rows = await db_connection.fetch_all("SELECT title, content FROM notes")
        notes_added = 0
        for row in rows:
            title = str(row.get("title") or "note").strip()
            content = str(row.get("content") or "").strip()
            snippet = " ".join(content.split())[:60] or "untitled note"
            if not title.lower() == "note":
                multi_brain_manager.add_triplet("general", title, "about", snippet)
                notes_added += 1
        added["general"] = notes_added
    except Exception as e:
        logger.warning("import-from-sources: notes skipped (%s)", e)

    # ── Long-term memory → general brain ─────────────────────────────────
    try:
        from memory.agent_memory_manager import MEMORY_PATH
        if MEMORY_PATH.exists():
            raw = MEMORY_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
            mem_added = 0
            for key, value in data.items():
                if not isinstance(value, (str, int, float, bool)):
                    value = str(value)[:120]
                value_s = str(value).strip()
                if not value_s:
                    continue
                multi_brain_manager.add_triplet(
                    "general", str(key).replace("_", " "), "contains", value_s[:60]
                )
                mem_added += 1
            added["general"] = added.get("general", 0) + mem_added
    except Exception as e:
        logger.warning("import-from-sources: memory skipped (%s)", e)

    # ── Jobs → career brain ──────────────────────────────────────────────
    try:
        from database.connection import db_connection
        job_rows = await db_connection.fetch_all(
            "SELECT company, title FROM job_listings WHERE company IS NOT NULL LIMIT 25"
        )
        jobs_added = 0
        for row in job_rows:
            company = str(row.get("company") or "").strip()
            title = str(row.get("title") or "role").strip()
            if company:
                multi_brain_manager.add_triplet("career", company, "hiring_for", title)
                jobs_added += 1
        added["career"] = jobs_added
    except Exception as e:
        logger.warning("import-from-sources: jobs skipped (%s)", e)

    # ── AI chat history → ai_chats brain (LLM-free) ──────────────────────
    # Real conversation-derived data: agent chat history topics, memory-bus
    # facts learned from user/agent turns, and voice session summaries.
    chats_added = 0

    # Agent chat history (cross-device sync: /memory/agent-history)
    try:
        from database import settings_dao
        raw_history = await settings_dao.get_setting("agent_chat_history")
        if raw_history:
            history = json.loads(raw_history)
            topics: list[str] = []
            if isinstance(history, dict):
                for _agent, messages in history.items():
                    if not isinstance(messages, list):
                        continue
                    for msg in messages:
                        if not isinstance(msg, dict):
                            continue
                        if msg.get("role") != "user":
                            continue
                        content = str(msg.get("content") or "").strip()
                        topic = " ".join(content.split()[:8])[:60]
                        if topic and topic not in topics:
                            topics.append(topic)
            for topic in topics[:50]:
                multi_brain_manager.add_triplet(
                    "ai_chats", topic, "ASKED_ABOUT", "barq assistant"
                )
                chats_added += 1
    except Exception as e:
        logger.warning("import-from-sources: chat history skipped (%s)", e)

    # Memory-bus facts learned from conversations (source user/agent)
    # Reads via a thread so the blocking sqlite3 call never stalls the event
    # loop, and excludes TTL-expired entries like every other bus read path.
    try:
        import sqlite3
        import time as _time
        from memory.memory_bus import MEMORY_BUS_DB
        from pathlib import Path as _P
        bus_path = str(_P(__file__).resolve().parent.parent / "data" / MEMORY_BUS_DB)
        if _P(bus_path).exists():
            def _read_mem_rows() -> list[dict]:
                with sqlite3.connect(bus_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT key, value FROM memory_entries "
                        "WHERE source IN ('user','agent') AND value != '' "
                        "AND (expires_at IS NULL OR expires_at > ?) LIMIT 60",
                        (_time.time(),),
                    ).fetchall()
                return [dict(r) for r in rows]

            mem_rows = await asyncio.to_thread(_read_mem_rows)
            for row in mem_rows:
                key = str(row["key"]).replace("_", " ").strip()
                value = str(row["value"]).strip()[:60]
                if key and value:
                    multi_brain_manager.add_triplet("ai_chats", key, "DISCUSSED_AS", value)
                    chats_added += 1
    except Exception as e:
        logger.warning("import-from-sources: memory-bus chat import skipped (%s)", e)

    # Voice session summaries (morning recall)
    try:
        from memory.agent_memory_manager import MEMORY_PATH
        if MEMORY_PATH.exists():
            sessions = json.loads(MEMORY_PATH.read_text(encoding="utf-8")).get("sessions", [])
            for s in sessions:
                if not isinstance(s, dict):
                    continue
                summary = str(s.get("summary") or "").strip()
                if not summary:
                    continue
                for topic in summary.split(";")[:4]:
                    topic = topic.replace("Discussed:", "", 1).strip().strip(":")
                    topic = " ".join(topic.split())[:50]
                    if topic:
                        multi_brain_manager.add_triplet(
                            "ai_chats", topic, "DISCUSSED_IN", "voice session"
                        )
                        chats_added += 1
    except Exception as e:
        logger.warning("import-from-sources: session summaries skipped (%s)", e)

    added["ai_chats"] = chats_added

    for brain_type in added:
        multi_brain_manager.save_brain(brain_type)
    multi_brain_manager.save_timeline()
    return added


async def ensure_populated() -> dict[str, Any]:
    """One-time population so the Knowledge Graph page is never blank.

    Seeds the demo graph and imports real notes/memory/jobs data only on a
    true first run — i.e. when no brain data files have ever been persisted.
    This way an explicit user "Clear" + "Save" is not undone on restart.
    Called from the app startup hook in ``main.py``.
    """
    # If brain files exist on disk, this is not a first run — even if the
    # graphs are currently empty (user may have deliberately cleared them).
    from pathlib import Path
    base = Path(multi_brain_manager._data_dir) if multi_brain_manager._data_dir else Path("data/brains")
    if base.exists() and any(base.glob("*.json")):
        return {"status": "already_persisted", "note": "brain files exist; skipping auto-population"}
    total = sum(
        multi_brain_manager.get_brain(bt).number_of_nodes()
        for bt in multi_brain_manager.brains
    )
    if total > 0:
        return {"status": "already_populated", "nodes": total}
    demo = _seed_demo_core()
    imported = await _import_direct_sources()
    return {
        "status": "populated",
        "demo_added": sum(demo.values()),
        "imported": imported,
    }


# ─── Ingest / Triplet ──────────────────────────────────────────────────────


@router.post("/{brain_type}/ingest")
async def ingest_text_into_brain(brain_type: str, request: IngestTextRequest) -> dict[str, Any]:
    """Extract knowledge triplets from text and add them to a specific brain.

    Runs real LLM relationship extraction with a provider chain — local Ollama
    first, then Google Gemini as fallback.  If both LLMs are unavailable or
    extract nothing, the request still succeeds so the UI can show a friendly
    "nothing extracted" message.
    """
    if not multi_brain_manager.is_valid_brain(brain_type):
        raise HTTPException(status_code=404, detail=f"Unknown brain type '{brain_type}'")

    triplets, provider = await extract_triplets_with_provider(request.text)
    for subj, rel, obj in triplets:
        multi_brain_manager.add_triplet(brain_type, subj, rel, obj)
    if triplets:
        multi_brain_manager.save_brain(brain_type)
        multi_brain_manager.save_timeline()

    stats = multi_brain_manager.get_statistics(brain_type)
    return {
        "brain_type": brain_type,
        "triplets_added": len(triplets),
        "nodes": stats["nodes"],
        "edges": stats["edges"],
        "provider": provider,
        "note": None if triplets else "No triplets extracted — Ollama and Gemini both unavailable.",
    }


@router.post("/{brain_type}/triplet")
async def add_triplet_to_brain(brain_type: str, request: TripletAddRequest) -> dict[str, Any]:
    """Directly add a single (subject, relation, object) triplet to a brain."""
    if not multi_brain_manager.is_valid_brain(brain_type):
        raise HTTPException(status_code=404, detail=f"Unknown brain type '{brain_type}'")

    multi_brain_manager.add_triplet(
        brain_type, request.subject, request.relation, request.object_
    )
    multi_brain_manager.save_brain(brain_type)
    multi_brain_manager.save_timeline()
    stats = multi_brain_manager.get_statistics(brain_type)
    return {
        "brain_type": brain_type,
        "triplets_added": 1,
        "nodes": stats["nodes"],
        "edges": stats["edges"],
    }


@router.post("/{brain_type}/clear")
async def clear_brain(brain_type: str) -> dict[str, Any]:
    """Remove all nodes and edges from a single brain."""
    if not multi_brain_manager.is_valid_brain(brain_type):
        raise HTTPException(status_code=404, detail=f"Unknown brain type '{brain_type}'")
    removed = multi_brain_manager.get_brain(brain_type).number_of_nodes()
    multi_brain_manager.clear_brain(brain_type)
    multi_brain_manager.save_brain(brain_type)
    return {"brain_type": brain_type, "status": "cleared", "removed_nodes": removed}


# ─── Save / Seed / Import (static routes — registered last is fine) ────────


@router.post("/save")
async def save_brains() -> dict[str, Any]:
    """Persist all brains and the timeline to disk."""
    results = multi_brain_manager.save_all()
    return {"status": "saved", "brains": results, "total_nodes": sum(results.values())}


@router.post("/seed-demo")
async def seed_demo() -> dict[str, Any]:
    """Populate empty brains with a starter demo knowledge graph (no LLM)."""
    added = _seed_demo_core()
    return {"status": "seeded", "brains": added, "total_added": sum(added.values())}


async def run_brain_reimport() -> dict[str, Any]:
    """Re-import real BARQ data (notes, memory, jobs, AI chats) into the brains.

    Shared core used by both the ``POST /api/brain/import-from-sources``
    endpoint and the periodic scheduler job.  Runs LLM triplet extraction on
    each source (Ollama → Gemini chain) when available, then falls back to
    direct (LLM-free) triplets so data always lands.  New notes/memory/jobs
    add to the graphs; existing edges just have their weights bumped.

    Also feeds the ``ai_chats`` brain from real conversation data (agent
    chat history + voice session summaries) and processes any files dropped
    into ``data/dropbox/<brain>/`` or ``data/ingest/ai_chats/`` so the
    apple_notes / google_docs / gemini_chats / career brains populate too.

    Returns:
        Dict with ``status`` and per-source ``results``.
    """
    results: dict[str, Any] = {}

    # ── Notes → general (LLM extraction, fallback to direct) ─────────────
    notes_text = ""
    try:
        from database.connection import db_connection
        rows = await db_connection.fetch_all("SELECT title, content FROM notes")
        notes_text = "\n".join(
            f"{r.get('title', '')}: {r.get('content', '')}" for r in rows
        )
    except Exception as e:
        logger.warning("import-from-sources: notes read skipped (%s)", e)
    if notes_text.strip():
        triplets, provider = await extract_triplets_with_provider(notes_text)
        for subj, rel, obj in triplets:
            multi_brain_manager.add_triplet("general", subj, rel, obj)
        results["notes_llm_triplets"] = len(triplets)
        results["notes_provider"] = provider

    # ── Memory → general (LLM extraction) ────────────────────────────────
    mem_text = ""
    try:
        from memory.agent_memory_manager import MEMORY_PATH
        if MEMORY_PATH.exists():
            mem_text = json.dumps(
                json.loads(MEMORY_PATH.read_text(encoding="utf-8")), default=str
            )[:4000]
    except Exception as e:
        logger.warning("import-from-sources: memory read skipped (%s)", e)
    if mem_text.strip():
        triplets, provider = await extract_triplets_with_provider(mem_text)
        for subj, rel, obj in triplets:
            multi_brain_manager.add_triplet("general", subj, rel, obj)
        results["memory_llm_triplets"] = len(triplets)
        results["memory_provider"] = provider

    # ── AI chats → ai_chats brain (LLM extraction) ───────────────────────
    # Real conversation data: cross-device agent chat history + voice
    # session summaries.  LLM extraction first, direct fallback below.
    chat_text = ""
    try:
        from database import settings_dao
        raw_history = await settings_dao.get_setting("agent_chat_history")
        if raw_history:
            history = json.loads(raw_history)
            turns: list[str] = []
            if isinstance(history, dict):
                for _agent, messages in history.items():
                    if not isinstance(messages, list):
                        continue
                    for msg in messages:
                        if not isinstance(msg, dict):
                            continue
                        role = "User" if msg.get("role") == "user" else "Assistant"
                        content = str(msg.get("content") or "").strip()
                        if content:
                            turns.append(f"{role}: {content}")
            chat_text = "\n".join(turns)
    except Exception as e:
        logger.warning("import-from-sources: chat history read skipped (%s)", e)
    try:
        from memory.agent_memory_manager import MEMORY_PATH
        if MEMORY_PATH.exists():
            sessions = json.loads(MEMORY_PATH.read_text(encoding="utf-8")).get("sessions", [])
            summaries = [
                str(s.get("summary") or "").strip()
                for s in sessions
                if isinstance(s, dict) and s.get("summary")
            ]
            if summaries:
                chat_text += "\n" + "\n".join(f"Session: {s}" for s in summaries)
    except Exception as e:
        logger.warning("import-from-sources: session summaries read skipped (%s)", e)
    if chat_text.strip():
        triplets, provider = await extract_triplets_with_provider(chat_text[:4000])
        for subj, rel, obj in triplets:
            multi_brain_manager.add_triplet("ai_chats", subj, rel, obj)
        results["ai_chats_llm_triplets"] = len(triplets)
        results["ai_chats_provider"] = provider

    # ── Drop-folder ingestion (apple_notes / google_docs / gemini_chats …) ──
    # Processes any files dropped into ``data/dropbox/<brain>/`` so those
    # brains fill automatically whenever source files are present.
    try:
        from memory_knowledge.ingestion import run_ingestion_once
        results["dropbox_triplets"] = await asyncio.to_thread(run_ingestion_once)
    except Exception as e:
        logger.warning("import-from-sources: dropbox processing skipped (%s)", e)

    # ── Gemini chat file ingestion (data/ingest/ai_chats/) ───────────────
    try:
        from app.services.gemini_watcher import get_gemini_watcher
        results["gemini_ingest_triplets"] = await asyncio.to_thread(
            get_gemini_watcher().process_all_existing
        )
    except Exception as e:
        logger.warning("import-from-sources: gemini ingest skipped (%s)", e)

    # ── Guaranteed non-LLM fallback (notes / memory / jobs / chats) ──────
    direct = await _import_direct_sources()
    results["direct_triplets"] = direct

    multi_brain_manager.save_all()
    multi_brain_manager.save_timeline()
    return {"status": "imported", "results": results}


@router.post("/import-from-sources")
async def import_from_sources() -> dict[str, Any]:
    """Auto-import real BARQ data (notes, memory, jobs) into the brains.

    Runs LLM triplet extraction on each source when Ollama is available, then
    falls back to direct (LLM-free) triplets so data always lands.
    """
    return await run_brain_reimport()


