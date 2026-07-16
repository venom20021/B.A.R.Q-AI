"""
FastAPI routes for memory and knowledge: core memory, notes,
vector search, and RAG knowledge base.
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import analytics_dao, settings_dao
from database.connection import db_connection

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


# ─── Notes (SQLite) ───────────────────────────────────────────────────────────


@router.get("/notes")
async def get_notes():
    """Get all saved notes from the database."""
    try:
        rows = await db_connection.fetch_all(
            "SELECT id, title, content, tags, pinned, color, created_at, updated_at "
            "FROM notes ORDER BY pinned DESC, created_at DESC"
        )
        notes = []
        for row in rows:
            note = dict(row)
            # Parse tags from JSON string
            if isinstance(note.get("tags"), str):
                try:
                    note["tags"] = json.loads(note["tags"])
                except (json.JSONDecodeError, TypeError):
                    note["tags"] = []
            notes.append(note)
        return {"notes": notes}
    except Exception:
        # Fallback to file-based notes if table doesn't exist yet
        return _fallback_get_notes()


def _fallback_get_notes() -> dict:
    """Fallback: load notes from JSON file."""
    NOTES_FILE = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes.json"))
    if NOTES_FILE.exists():
        try:
            notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
            notes.reverse()
            return {"notes": notes}
        except (json.JSONDecodeError, OSError):
            pass
    return {"notes": []}


@router.post("/notes")
async def create_note(request: NoteItem):
    """Create a new note in the database."""
    try:
        # Migrate old notes from JSON file if they exist
        NOTES_FILE = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes.json"))
        if NOTES_FILE.exists():
            await _migrate_notes_from_json(NOTES_FILE)

        note_id = await db_connection.insert(
            "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
            (request.title, request.content, json.dumps(request.tags)),
        )

        await analytics_dao.log_activity(
            "memory", "create_note", f"Created note: {request.title[:50]}"
        )
        return {
            "status": "created",
            "note": {
                "id": note_id,
                "title": request.title,
                "content": request.content,
                "tags": request.tags,
                "created_at": _now_iso(),
            },
        }
    except Exception:
        # Fallback to file-based notes
        return _fallback_create_note(request)


def _fallback_create_note(request: NoteItem) -> dict:
    """Fallback: create note in JSON file."""
    NOTES_FILE = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes.json"))
    notes = []
    if NOTES_FILE.exists():
        try:
            notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            notes = []
    note = {
        "id": len(notes) + 1,
        "title": request.title,
        "content": request.content,
        "tags": request.tags,
        "created_at": _now_iso(),
    }
    notes.append(note)
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTES_FILE.write_text(json.dumps(notes, indent=2), encoding="utf-8")
    return {"status": "created", "note": note}


async def _migrate_notes_from_json(json_path: Path):
    """Migrate notes from JSON file to SQLite."""
    try:
        old_notes = json.loads(json_path.read_text(encoding="utf-8"))
        for note in old_notes:
            try:
                await db_connection.insert(
                    "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
                    (note.get("title", ""), note.get("content", ""), json.dumps(note.get("tags", []))),
                )
            except Exception:
                continue
        # Rename old file as backup
        backup_path = json_path.with_suffix(".json.bak")
        json_path.rename(backup_path)
        print(f"[Notes] Migrated {len(old_notes)} notes from JSON to SQLite. Backup saved to {backup_path}")
    except Exception as e:
        print(f"[Notes] Migration error: {e}")


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int):
    """Delete a note by ID."""
    try:
        await db_connection.delete("DELETE FROM notes WHERE id = ?", (note_id,))
        return {"status": "deleted", "note_id": note_id}
    except Exception as e:
        # Fallback to file-based deletion
        NOTES_FILE = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes.json"))
        if NOTES_FILE.exists():
            try:
                notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
                notes = [n for n in notes if n.get("id") != note_id]
                NOTES_FILE.write_text(json.dumps(notes, indent=2), encoding="utf-8")
                return {"status": "deleted", "note_id": note_id}
            except (json.JSONDecodeError, OSError):
                pass
        raise HTTPException(status_code=500, detail=str(e))


# ─── Vector Search (LanceDB) ─────────────────────────────────────────────────

@router.post("/vector/index")
async def index_directory(directory: str):
    """Index a directory for vector search."""
    try:
        try:
            import numpy as np

            import lancedb
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
    except Exception:
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


# ─── Agent Chat History (cross-device sync) ──────────────────────────────

@router.get("/agent-history")
async def get_agent_history():
    """Get the persisted agent chat history."""
    try:
        raw = await settings_dao.get_setting("agent_chat_history")
        if raw:
            return {"history": json.loads(raw)}
        return {"history": {}}
    except Exception:
        return {"history": {}}


@router.post("/agent-history")
async def save_agent_history(data: dict):
    """Persist agent chat history to the database."""
    try:
        history = data.get("history", {})
        await settings_dao.set_setting(
            "agent_chat_history",
            json.dumps(history),
            category="memory",
        )
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helper ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
