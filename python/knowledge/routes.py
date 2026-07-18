"""
FastAPI routes for the Knowledge module: Obsidian vault configuration,
manual extraction triggers, graph snapshot dumping, and Gemini chat import.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from graph_brain import graph_brain

from .auto_extractor import AutoExtractor, run_auto_extraction
from .obsidian_dumper import ObsidianDumper, get_obsidian_dumper
from .gemini_importer import GeminiChatImporter, ImportResult, get_gemini_importer

logger = logging.getLogger("barq.knowledge_routes")
router = APIRouter()

# Singleton instances
_auto_extractor = AutoExtractor()
_gemini_importer = GeminiChatImporter()


# ─── Models ─────────────────────────────────────────────────────────

class ObsidianConfigRequest(BaseModel):
    vault_path: str


class ExtractionResponse(BaseModel):
    status: str
    extraction: Optional[dict[str, int]] = None
    message: str = ""


class DumpRequest(BaseModel):
    topic: str
    report: str
    depth: str = "standard"
    sources_count: int = 0
    facts_count: int = 0


class GeminiImportRequest(BaseModel):
    file_path: str
    """Path to a Gemini export JSON file (Takeout, AI Studio, or generic chat JSON)."""


class GeminiImportTextRequest(BaseModel):
    json_text: str
    """Raw JSON text containing Gemini conversation data."""
    source_name: str = "direct_input"
    """Optional label for the import source."""


# ═════════════════════════════════════════════════════════════════════
#  Obsidian Vault Configuration
# ═════════════════════════════════════════════════════════════════════

@router.get("/obsidian/config", summary="Get Obsidian vault configuration")
async def get_obsidian_config():
    """Get the current Obsidian vault path and configuration status."""
    try:
        from database import settings_dao
        vault_path_raw = await settings_dao.get_setting("obsidian_vault_path")
        vault_path = vault_path_raw or ""

        dumper = get_obsidian_dumper()
        dumper.vault_path = vault_path

        return {
            "vault_path": vault_path,
            "configured": bool(vault_path),
            "valid": dumper.is_configured(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/obsidian/config", summary="Set Obsidian vault path")
async def set_obsidian_config(request: ObsidianConfigRequest):
    """Set the Obsidian vault path. The path must point to an existing directory."""
    import os

    path = request.vault_path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="Vault path is required")

    # Validate the path exists
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {path}")

    try:
        from database import settings_dao
        await settings_dao.set_setting("obsidian_vault_path", path, category="knowledge")

        # Update the singleton
        dumper = get_obsidian_dumper()
        dumper.vault_path = path

        return {
            "status": "configured",
            "vault_path": path,
            "message": f"Obsidian vault set to: {path}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═════════════════════════════════════════════════════════════════════
#  Manual Extraction
# ═════════════════════════════════════════════════════════════════════

@router.post("/extract/run", summary="Run extraction on all unprocessed content")
async def trigger_extraction():
    """Run knowledge triplet extraction on unprocessed job descriptions and trends."""
    try:
        result = await _auto_extractor.run_full_extraction()
        return {
            "status": "completed",
            "extraction": result,
            "message": f"Extracted {result['total_triplets']} triplets total",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract/jobs", summary="Extract from job descriptions")
async def extract_jobs(limit: int = 20):
    """Extract knowledge triplets from job descriptions."""
    try:
        total = await _auto_extractor.extract_from_jobs_batch(limit=limit)
        return {
            "status": "completed",
            "extraction": {"triplets_added": total, "jobs_scanned": limit},
            "message": f"Extracted {total} triplets from job descriptions",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract/trends", summary="Extract from social trends")
async def extract_trends(limit: int = 10):
    """Extract knowledge triplets from social trends."""
    try:
        total = await _auto_extractor.extract_from_trends_batch(limit=limit)
        return {
            "status": "completed",
            "extraction": {"triplets_added": total, "trends_scanned": limit},
            "message": f"Extracted {total} triplets from trends",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═════════════════════════════════════════════════════════════════════
#  Obsidian Dumping
# ═════════════════════════════════════════════════════════════════════

@router.post("/obsidian/dump/research", summary="Dump research report to Obsidian")
async def dump_research(request: DumpRequest):
    """Dump a deep research report to the Obsidian vault."""
    try:
        dumper = get_obsidian_dumper()
        # Refresh vault path from settings
        from database import settings_dao
        vault_path = await settings_dao.get_setting("obsidian_vault_path")
        if vault_path:
            dumper.vault_path = vault_path

        if not dumper.is_configured():
            raise HTTPException(status_code=400, detail="Obsidian vault not configured. Set a vault path first.")

        filepath = dumper.dump_research_report(
            topic=request.topic,
            report=request.report,
            depth=request.depth,
            sources_count=request.sources_count,
            facts_count=request.facts_count,
        )

        if filepath:
            return {"status": "dumped", "filepath": filepath}
        return {"status": "skipped", "message": "Vault not configured"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/obsidian/dump/graph", summary="Dump graph snapshot to Obsidian")
async def dump_graph_snapshot():
    """Dump a snapshot of the current knowledge graph to the Obsidian vault."""
    try:
        dumper = get_obsidian_dumper()
        from database import settings_dao
        vault_path = await settings_dao.get_setting("obsidian_vault_path")
        if vault_path:
            dumper.vault_path = vault_path

        if not dumper.is_configured():
            raise HTTPException(status_code=400, detail="Obsidian vault not configured.")

        stats = graph_brain.get_statistics()
        top = graph_brain.get_top_entities(limit=10)

        summary = f"Graph brain auto-snapshot at {stats['nodes']} nodes and {stats['edges']} edges."

        filepath = dumper.dump_graph_snapshot(
            nodes_count=stats["nodes"],
            edges_count=stats["edges"],
            top_entities=top,
            summary=summary,
        )

        if filepath:
            return {"status": "dumped", "filepath": filepath, "stats": stats}
        return {"status": "skipped", "message": "Vault not configured"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═════════════════════════════════════════════════════════════════════
#  Gemini Chat Import
# ═════════════════════════════════════════════════════════════════════

@router.post(
    "/gemini/import",
    summary="Import Gemini chat file by path",
)
async def gemini_import_file(request: GeminiImportRequest) -> dict[str, Any]:
    """Import Gemini conversations from a JSON file on disk into the
    ``gemini_chats`` knowledge graph brain.

    Supports:
    - Google Takeout export (``Takeout/Gemini/MyActivity.json``)
    - Google AI Studio export
    - Generic chat JSON (array of ``{role, content}`` messages)

    The file is parsed, entities are extracted from conversations using
    lightweight NLP heuristics, and knowledge triplets are added to the
    ``gemini_chats`` brain and persisted to disk.
    """
    try:
        result = _gemini_importer.import_file(request.file_path)
        if result.errors:
            return {
                "status": "partial" if result.triplets_added > 0 else "error",
                **result.to_dict(),
            }
        return {
            "status": "ok",
            **result.to_dict(),
        }
    except Exception as e:
        logger.error("Gemini import failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/gemini/import/text",
    summary="Import Gemini conversations from raw JSON text",
)
async def gemini_import_text(request: GeminiImportTextRequest) -> dict[str, Any]:
    """Import Gemini conversations from a raw JSON string into the
    ``gemini_chats`` knowledge graph brain.

    Useful for API clients that have the JSON data in memory rather than
    as a file on disk.
    """
    try:
        result = _gemini_importer.import_text(
            request.json_text,
            source_name=request.source_name,
        )
        if result.errors:
            return {
                "status": "partial" if result.triplets_added > 0 else "error",
                **result.to_dict(),
            }
        return {
            "status": "ok",
            **result.to_dict(),
        }
    except Exception as e:
        logger.error("Gemini import text failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/gemini/import/upload",
    summary="Import Gemini conversations from an uploaded JSON file",
)
async def gemini_import_upload(
    file: UploadFile = File(..., description="Gemini export JSON file"),
) -> dict[str, Any]:
    """Upload and import a Gemini export JSON file.

    The file is read in memory, parsed, and triplets are added to the
    ``gemini_chats`` brain. Supported formats:
    - Google Takeout ``.json``
    - Google AI Studio ``.json``
    - Generic chat ``.json``
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.filename}. Only .json files are accepted.",
        )

    try:
        content = await file.read()
        json_text = content.decode("utf-8", errors="replace")
        result = _gemini_importer.import_text(
            json_text,
            source_name=file.filename,
        )
        if result.errors:
            return {
                "status": "partial" if result.triplets_added > 0 else "error",
                **result.to_dict(),
            }
        return {
            "status": "ok",
            **result.to_dict(),
        }
    except Exception as e:
        logger.error("Gemini import upload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/gemini/import/directory",
    summary="Import all Gemini chat files from a directory",
)
async def gemini_import_directory(
    dir_path: str = Query(..., description="Path to directory containing Gemini export JSON files"),
) -> dict[str, Any]:
    """Import all Gemini conversation JSON files from a directory.

    Scans recursively for ``*.json`` files and imports each one.
    Returns a summary of all imports.
    """
    import os

    if not os.path.isdir(dir_path):
        raise HTTPException(status_code=400, detail=f"Directory not found: {dir_path}")

    try:
        results = _gemini_importer.import_directory(dir_path)
        total_triplets = sum(r.triplets_added for r in results)
        total_convs = sum(r.conversations_imported for r in results)
        total_files = len(results)
        errors = [r.to_dict() for r in results if r.errors]

        return {
            "status": "ok",
            "directory": dir_path,
            "files_processed": total_files,
            "conversations_imported": total_convs,
            "triplets_added": total_triplets,
            "files_with_errors": len(errors),
            "details": [r.to_dict() for r in results] if total_files <= 20 else [],
        }
    except Exception as e:
        logger.error("Gemini import directory failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/gemini/status",
    summary="Get gemini_chats brain statistics",
)
async def gemini_import_status() -> dict[str, Any]:
    """Return current statistics for the ``gemini_chats`` brain.

    Includes node/edge counts, density, connected components,
    and top entities by centrality.
    """
    try:
        stats = _gemini_importer.get_brain_stats()
        return {
            "status": "ok",
            "brain_type": stats.get("brain_type", "gemini_chats"),
            "nodes": stats.get("nodes", 0),
            "edges": stats.get("edges", 0),
            "density": stats.get("density", 0.0),
            "connected_components": stats.get("connected_components", 0),
            "top_entities": stats.get("top_entities", []),
            "supported_formats": _gemini_importer.list_formats(),
        }
    except Exception as e:
        logger.error("Gemini status check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/gemini/formats",
    summary="List supported Gemini import formats",
)
async def gemini_import_formats() -> dict[str, Any]:
    """Return the list of supported Gemini import formats with descriptions."""
    try:
        formats = _gemini_importer.list_formats()
        return {
            "status": "ok",
            "formats": formats,
        }
    except Exception as e:
        logger.error("Gemini formats check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
