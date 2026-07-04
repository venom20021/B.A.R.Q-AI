"""
Tests for memory_knowledge FastAPI routes: memory CRUD, notes, search, RAG.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_knowledge.routes import NOTES_FILE


@pytest.fixture
def router():
    from memory_knowledge import routes
    return routes.router


@pytest.fixture(autouse=True)
def clean_notes_file():
    """Remove notes.json before and after each test."""
    if NOTES_FILE.exists():
        NOTES_FILE.unlink()
    yield
    if NOTES_FILE.exists():
        NOTES_FILE.unlink()


# ─── Core Memory ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_memory_empty(client):
    """GET /memory should return empty list initially."""
    response = await client.get("/memory")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_store_and_retrieve_memory(client):
    """POST then GET /memory should return stored items."""
    # Store a memory
    store_resp = await client.post(
        "/memory",
        json={"key": "my_name", "value": "BARQ", "category": "general"},
    )
    assert store_resp.status_code == 200
    assert store_resp.json()["status"] == "stored"
    assert store_resp.json()["key"] == "my_name"

    # Retrieve all memories
    get_resp = await client.get("/memory")
    assert get_resp.status_code == 200
    items = get_resp.json()["items"]
    assert len(items) >= 1
    # The key is stored with "memory_" prefix
    assert any("my_name" in item["key"] for item in items)


@pytest.mark.asyncio
async def test_forget_memory(client):
    """DELETE /memory/{key} should remove a stored memory."""
    # Store first
    await client.post(
        "/memory",
        json={"key": "temp_key", "value": "temp_value", "category": "general"},
    )

    # Delete
    del_resp = await client.delete("/memory/temp_key")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "forgotten"

    # Verify gone
    get_resp = await client.get("/memory")
    items = get_resp.json()["items"]
    assert all("temp_key" not in item["key"] for item in items)


@pytest.mark.asyncio
async def test_search_memory(client):
    """GET /memory/search should find matching memories."""
    await client.post("/memory", json={"key": "api_key", "value": "sk-abc123", "category": "general"})
    await client.post("/memory", json={"key": "db_url", "value": "sqlite:///test.db", "category": "general"})

    # Search by value
    resp = await client.get("/memory/search?query=abc123")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1
    assert any("api_key" in r["key"] for r in results)

    # Search by key
    resp = await client.get("/memory/search?query=db_url")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_memory_no_results(client):
    """GET /memory/search with non-matching query should return empty."""
    await client.post("/memory", json={"key": "color", "value": "blue", "category": "general"})

    resp = await client.get("/memory/search?query=zzzznotfound")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 0


# ─── Notes ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_notes_empty(client):
    """GET /notes should return empty list initially."""
    response = await client.get("/notes")
    assert response.status_code == 200
    assert response.json()["notes"] == []


@pytest.mark.asyncio
async def test_create_and_get_notes(client):
    """POST then GET /notes should return created notes."""
    create_resp = await client.post(
        "/notes",
        json={"title": "Test Note", "content": "Hello BARQ", "tags": ["test"]},
    )
    assert create_resp.status_code == 200
    note = create_resp.json()["note"]
    assert note["title"] == "Test Note"
    assert note["content"] == "Hello BARQ"
    assert note["tags"] == ["test"]
    assert "created_at" in note

    get_resp = await client.get("/notes")
    assert get_resp.status_code == 200
    notes = get_resp.json()["notes"]
    assert len(notes) >= 1
    assert notes[0]["title"] == "Test Note"


@pytest.mark.asyncio
async def test_create_multiple_notes(client):
    """Creating multiple notes should auto-increment IDs."""
    r1 = await client.post("/notes", json={"title": "Note 1", "content": "First"})
    assert r1.json()["note"]["id"] == 1

    r2 = await client.post("/notes", json={"title": "Note 2", "content": "Second"})
    assert r2.json()["note"]["id"] == 2

    r3 = await client.post("/notes", json={"title": "Note 3", "content": "Third"})
    assert r3.json()["note"]["id"] == 3


@pytest.mark.asyncio
async def test_delete_note(client):
    """DELETE /notes/{id} should remove the note."""
    # Create
    create_resp = await client.post("/notes", json={"title": "Delete Me", "content": "bye"})
    note_id = create_resp.json()["note"]["id"]

    # Delete
    del_resp = await client.delete(f"/notes/{note_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify
    get_resp = await client.get("/notes")
    assert all(n["id"] != note_id for n in get_resp.json()["notes"])


@pytest.mark.asyncio
async def test_delete_nonexistent_note(client):
    """DELETE /notes/{id} on non-existent note should still succeed gracefully."""
    resp = await client.delete("/notes/99999")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


# ─── Vector Search ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vector_search_no_lancedb(client):
    """POST /vector/search should return unavailable when lancedb not installed."""
    resp = await client.post(
        "/vector/search",
        json={"query": "test", "limit": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should fallback to filename search or return unavailable
    assert "results" in data or "status" in data


@pytest.mark.asyncio
async def test_vector_index_no_lancedb(client):
    """POST /vector/index should return unavailable when lancedb not installed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        resp = await client.post(
            f"/vector/index?directory={tmpdir}",
        )
        assert resp.status_code == 200
        data = resp.json()
        # Either unavailable (lancedb not installed) or indexed
        assert data["status"] in ("unavailable", "indexed")


# ─── RAG Knowledge Base ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rag_ingest_file_not_found(client):
    """POST /rag/ingest with non-existent file should return 404."""
    resp = await client.post("/rag/ingest?file_path=/nonexistent/foo.txt")
    assert resp.status_code == 404
    assert "File not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_rag_ingest_and_query(client):
    """POST /rag/ingest then POST /rag/query should return matches."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("BARQ is a voice-controlled desktop AI assistant.")
        f.write(" It can scan jobs and automate social media.")
        f_path = f.name

    try:
        # Ingest
        ingest_resp = await client.post(f"/rag/ingest?file_path={f_path}")
        assert ingest_resp.status_code == 200
        assert ingest_resp.json()["status"] == "ingested"

        # Query for matching content
        query_resp = await client.post(
            "/rag/query",
            json={"query": "voice-controlled", "collection": "default"},
        )
        assert query_resp.status_code == 200
        data = query_resp.json()
        assert len(data["results"]) >= 1
        assert data["total_entries"] >= 1
        assert any("voice" in r["snippet"].lower() for r in data["results"])
    finally:
        os.unlink(f_path)


@pytest.mark.asyncio
async def test_rag_query_no_match(client):
    """POST /rag/query with non-matching query should return empty results."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("Only Python and FastAPI content here.")
        f_path = f.name

    try:
        await client.post(f"/rag/ingest?file_path={f_path}")

        resp = await client.post(
            "/rag/query",
            json={"query": "quantum computing", "collection": "default"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 0
    finally:
        os.unlink(f_path)


@pytest.mark.asyncio
async def test_rag_status(client):
    """GET /rag/status should return current RAG state."""
    resp = await client.get("/rag/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_entries" in data
    assert "collections" in data
    assert "embedding_model" in data
    assert data["total_entries"] >= 0
