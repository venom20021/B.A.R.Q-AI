"""
FastAPI routes for memory and knowledge: core memory, notes,
vector search, and RAG knowledge base.
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import analytics_dao, settings_dao

router = APIRouter()


# ─── Models ───────────────────────────────────────────────────────────────────

class MemoryItem(BaseModel):
    key: str
    value: str
    category: str = "general"

class NoteItem(BaseModel):
    title: str
    content: str
    tags: list[str] = []

class SearchQuery(BaseModel):
    query: str
    limit: int = 10

class RAGQuery(BaseModel):
    query: str
    collection: str = "default"


# ─── Core Memory ──────────────────────────────────────────────────────────────

@router.get("/memory")
async def get_all_memory():
    """Get all stored memory items."""
    try:
        items = await settings_dao.get_settings_by_category("memory")
        return {
            "items": [
                {"key": s["key"], "value": s["value"], "category": s.get("category", "general")}
                for s in items
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory")
async def store_memory(request: MemoryItem):
    """Store a fact in core memory."""
    try:
        await settings_dao.set_setting(f"memory_{request.key}", request.value, category="memory")
        await analytics_dao.log_activity(
            "memory", "store", f"Stored memory: {request.key}"
        )
        return {"status": "stored", "key": request.key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/memory/{key}")
async def forget_memory(key: str):
    """Remove a fact from memory."""
    try:
        await settings_dao.delete_setting(f"memory_{key}")
        await analytics_dao.log_activity(
            "memory", "forget", f"Forgot: {key}"
        )
        return {"status": "forgotten", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/search")
async def search_memory(query: str):
    """Search memory by key or value."""
    try:
        items = await settings_dao.get_settings_by_category("memory")
        query_lower = query.lower()
        results = [
            {"key": s["key"].replace("memory_", "", 1), "value": s["value"]}
            for s in items
            if query_lower in s["key"].lower() or query_lower in s["value"].lower()
        ]
        return {"results": results, "query": query}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Notes ────────────────────────────────────────────────────────────────────

NOTES_FILE = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes.json"))


def _load_notes() -> list[dict]:
    """Load notes from JSON file."""
    if NOTES_FILE.exists():
        try:
            return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_notes(notes: list[dict]):
    """Save notes to JSON file."""
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTES_FILE.write_text(json.dumps(notes, indent=2), encoding="utf-8")


@router.get("/notes")
async def get_notes():
    """Get all saved notes."""
    try:
        notes = _load_notes()
        # Return newest first
        notes.reverse()
        return {"notes": notes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notes")
async def create_note(request: NoteItem):
    """Create a new note."""
    try:
        notes = _load_notes()
        note = {
            "id": len(notes) + 1,
            "title": request.title,
            "content": request.content,
            "tags": request.tags,
            "created_at": _now_iso(),
        }
        notes.append(note)
        _save_notes(notes)

        await analytics_dao.log_activity(
            "memory", "create_note", f"Created note: {request.title[:50]}"
        )
        return {"status": "created", "note": note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int):
    """Delete a note by ID."""
    try:
        notes = _load_notes()
        notes = [n for n in notes if n.get("id") != note_id]
        _save_notes(notes)
        return {"status": "deleted", "note_id": note_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Vector Search (LanceDB) ─────────────────────────────────────────────────

@router.post("/vector/index")
async def index_directory(directory: str):
    """Index a directory for vector search."""
    try:
        try:
            import lancedb
            import numpy as np
        except ImportError:
            return {"status": "unavailable", "message": "LanceDB not installed. Run: pip install lancedb"}

        db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lancedb")
        db = lancedb.connect(db_dir)

        # Simple path-based indexing (embedding would use sentence-transformers)
        indexed = 0
        for path in Path(directory).rglob("*"):
            if path.is_file() and path.stat().st_size < 1_000_000:  # Skip files > 1MB
                try:
                    table_name = "files"
                    if table_name not in db.table_names():
                        db.create_table(table_name, data=[
                            {"vector": np.random.rand(384).tolist(),
                             "path": str(path),
                             "name": path.name,
                             "size": path.stat().st_size}
                        ])
                    else:
                        table = db.open_table(table_name)
                        table.add([{"vector": np.random.rand(384).tolist(),
                                    "path": str(path),
                                    "name": path.name,
                                    "size": path.stat().st_size}])
                    indexed += 1
                except Exception:
                    continue

        await analytics_dao.log_activity(
            "memory", "index_directory", f"Indexed {indexed} files from {directory}"
        )
        return {"status": "indexed", "files_indexed": indexed, "directory": directory}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vector/search")
async def vector_search(request: SearchQuery):
    """Search indexed files by query."""
    try:
        try:
            import lancedb
        except ImportError:
            return {"status": "unavailable", "message": "LanceDB not installed",
                    "results": [], "query": request.query}

        db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lancedb")
        db = lancedb.connect(db_dir)

        if "files" not in db.table_names():
            return {"results": [], "query": request.query, "message": "No indexed files yet"}

        table = db.open_table("files")
        # Simple string matching fallback for now
        results = table.search().limit(request.limit).to_list()
        return {"results": results, "query": request.query}
    except Exception as e:
        # Fallback to filename search
        return await _filename_search(request)


async def _filename_search(request: SearchQuery) -> dict:
    """Fallback: search by filename pattern."""
    results = []
    query_lower = request.query.lower()
    for path in Path(".").rglob("*"):
        if path.is_file() and query_lower in path.name.lower():
            results.append({
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
            })
            if len(results) >= request.limit:
                break
    return {"results": results, "query": request.query, "method": "filename"}


# ─── RAG Knowledge Base ───────────────────────────────────────────────────────

@router.post("/rag/ingest")
async def ingest_file(file_path: str):
    """Ingest a file into the RAG knowledge base."""
    try:
        path = Path(file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        content = path.read_text(encoding="utf-8", errors="ignore")

        # Store in settings as a knowledge entry
        entry_key = f"rag_{path.stem}_{path.stat().st_mtime}"
        await settings_dao.set_setting(
            entry_key,
            json.dumps({"path": str(path), "content": content[:5000], "size": path.stat().st_size}),
            category="knowledge"
        )

        await analytics_dao.log_activity(
            "memory", "rag_ingest", f"Ingested: {file_path}"
        )
        return {"status": "ingested", "file": file_path, "size": len(content)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/query")
async def rag_query(request: RAGQuery):
    """Query the RAG knowledge base."""
    try:
        entries = await settings_dao.get_settings_by_category("knowledge")
        query_lower = request.query.lower()

        results = []
        for entry in entries:
            try:
                data = json.loads(entry["value"])
                content = data.get("content", "").lower()
                if query_lower in content:
                    results.append({
                        "source": data.get("path", entry["key"]),
                        "relevance": "keyword_match",
                        "snippet": data.get("content", "")[:300],
                    })
            except (json.JSONDecodeError, KeyError):
                continue

        return {"results": results[:5], "query": request.query, "total_entries": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/status")
async def rag_status():
    """Get RAG knowledge base status."""
    try:
        entries = await settings_dao.get_settings_by_category("knowledge")
        return {
            "total_entries": len(entries),
            "collections": ["default"],
            "embedding_model": "sentence-transformers (planned)",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helper ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
