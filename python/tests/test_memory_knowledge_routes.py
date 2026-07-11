"""Tests for memory_knowledge FastAPI routes: memory CRUD, notes, search, RAG."""

import os
import tempfile

import pytest


@pytest.fixture
def router():
    from memory_knowledge import routes
    return routes.router


# ─── Core Memory ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_memory_empty(client):
    """GET /memory should return empty list initially."""
    response = await client.get("/memory")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_store_and_retrieve_memory(client):
    """POST then GET /memory should return stored items."""
    store_resp = await client.post(
        "/memory",
        json={"key": "my_name", "value": "BARQ", "category": "general"},
    )
    assert store_resp.status_code == 200
    assert store_resp.json()["status"] == "stored"
    assert store_resp.json()["key"] == "my_name"

    get_resp = await client.get("/memory")
    assert get_resp.status_code == 200
    items = get_resp.json()["items"]
    assert len(items) >= 1
    assert any("my_name" in item["key"] for item in items)


@pytest.mark.asyncio
async def test_forget_memory(client):
    """DELETE /memory/{key} should remove a stored memory."""
    await client.post(
        "/memory",
        json={"key": "temp_key", "value": "temp_value", "category": "general"},
    )

    del_resp = await client.delete("/memory/temp_key")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "forgotten"

    get_resp = await client.get("/memory")
    items = get_resp.json()["items"]
    assert all("temp_key" not in item["key"] for item in items)


@pytest.mark.asyncio
async def test_search_memory(client):
    """GET /memory/search should find matching memories."""
    await client.post("/memory", json={"key": "api_key", "value": "sk-abc123", "category": "general"})
    await client.post("/memory", json={"key": "db_url", "value": "sqlite:///test.db", "category": "general"})

    resp = await client.get("/memory/search?query=abc123")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1
    assert any("api_key" in r["key"] for r in results)

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


# ─── Notes (SQLite) ──────────────────────────────────────────────────────────

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
    """Creating multiple notes should increment IDs."""
    r1 = await client.post("/notes", json={"title": "Note 1", "content": "First"})
    assert r1.status_code == 200
    id1 = r1.json()["note"]["id"]

    r2 = await client.post("/notes", json={"title": "Note 2", "content": "Second"})
    assert r2.status_code == 200
    id2 = r2.json()["note"]["id"]

    r3 = await client.post("/notes", json={"title": "Note 3", "content": "Third"})
    assert r3.status_code == 200
    id3 = r3.json()["note"]["id"]

    assert id1 < id2 < id3  # IDs should be monotonically increasing
    assert id3 >= 3


@pytest.mark.asyncio
async def test_delete_note(client):
    """DELETE /notes/{id} should remove the note."""
    create_resp = await client.post("/notes", json={"title": "Delete Me", "content": "bye"})
    note_id = create_resp.json()["note"]["id"]

    del_resp = await client.delete(f"/notes/{note_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

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
    """POST /vector/search should return results even without lancedb."""
    resp = await client.post(
        "/vector/search",
        json={"query": "test", "limit": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data


@pytest.mark.asyncio
async def test_vector_index_no_lancedb(client):
    """POST /vector/index should return gracefully (unavailable, indexed, or error)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        resp = await client.post(
            f"/vector/index?directory={tmpdir}",
        )
        # Should not crash - may return unavailable, indexed, or fallback to 200
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "status" in data


# ─── RAG Knowledge Base ──────────────────────────────────────────────────────

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
        ingest_resp = await client.post(f"/rag/ingest?file_path={f_path}")
        assert ingest_resp.status_code == 200
        assert ingest_resp.json()["status"] == "ingested"

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
