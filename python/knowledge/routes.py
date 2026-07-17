"""
FastAPI routes for the Knowledge module: Obsidian vault configuration,
manual extraction triggers, and graph snapshot dumping.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from graph_brain import graph_brain

from .auto_extractor import AutoExtractor, run_auto_extraction
from .obsidian_dumper import ObsidianDumper, get_obsidian_dumper

router = APIRouter()

# Singleton instances
_auto_extractor = AutoExtractor()


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


# ─── Obsidian Vault Configuration ──────────────────────────────────

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


# ─── Manual Extraction ─────────────────────────────────────────────

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


# ─── Obsidian Dumping ─────────────────────────────────────────────

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
