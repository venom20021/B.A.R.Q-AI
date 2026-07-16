"""Tests for the brain_api visualization endpoint (GET /api/brain/visualize).

Verifies the endpoint returns the correct node-link graph format that
the React force-directed graph frontend expects.
"""

import pytest

# Ensure a fresh graph for each test module invocation
from graph_brain import graph_brain as _gb


@pytest.fixture(autouse=True)
def _reset_graph():
    """Clear the shared graph singleton before each test so tests are isolated."""
    _gb.clear()
    yield


@pytest.fixture
def router():
    from memory_knowledge.brain_api import router
    return router


# ─── Empty graph ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_graph_returns_valid_structure(client):
    """GET /api/brain/visualize on an empty graph should return valid shape."""
    resp = await client.get("/api/brain/visualize")
    assert resp.status_code == 200
    data = resp.json()

    # Must have the three top-level keys the frontend expects
    assert "nodes" in data
    assert "links" in data
    assert "_meta" in data

    assert data["nodes"] == []
    assert data["links"] == []

    # Metadata should reflect emptiness
    assert data["_meta"]["nodes"] == 0
    assert data["_meta"]["edges"] == 0


# ─── Graph with data ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_with_single_triplet(client):
    """A single triplet should appear as two nodes and one link."""
    _gb.add_triplet("python", "USED_FOR", "data science")

    resp = await client.get("/api/brain/visualize")
    assert resp.status_code == 200
    data = resp.json()

    assert data["_meta"]["nodes"] == 2
    assert data["_meta"]["edges"] == 1

    # Node ids
    node_ids = {n["id"] for n in data["nodes"]}
    assert node_ids == {"python", "data science"}

    # Link structure
    assert len(data["links"]) == 1
    link = data["links"][0]
    assert link["source"] == "python"
    assert link["target"] == "data science"
    assert link["relation"] == "USED_FOR"
    assert link["weight"] == 1


@pytest.mark.asyncio
async def test_graph_with_multiple_triplets(client):
    """Multiple overlapping triplets produce correct node/link counts."""
    _gb.add_triplet("python", "USED_FOR", "data science")
    _gb.add_triplet("python", "USED_AT", "google")
    _gb.add_triplet("data science", "REQUIRES", "statistics")

    resp = await client.get("/api/brain/visualize")
    assert resp.status_code == 200
    data = resp.json()

    assert data["_meta"]["nodes"] == 4  # python, data science, google, statistics
    assert data["_meta"]["edges"] == 3

    node_ids = {n["id"] for n in data["nodes"]}
    assert node_ids == {"python", "data science", "google", "statistics"}

    # Verify link structure
    links = data["links"]
    assert len(links) == 3
    for link in links:
        assert "source" in link
        assert "target" in link
        assert "relation" in link
        assert "weight" in link


@pytest.mark.asyncio
async def test_node_attributes_include_label(client):
    """Nodes should have a 'label' attribute matching their id."""
    _gb.add_triplet("react", "IS_A", "frontend framework")

    resp = await client.get("/api/brain/visualize")
    data = resp.json()

    for node in data["nodes"]:
        assert "label" in node
        assert node["label"] == node["id"]


# ─── Edge cases ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_triplet_increments_weight(client):
    """Adding the same triplet twice should increment the edge weight."""
    _gb.add_triplet("a", "RELATED_TO", "b")
    _gb.add_triplet("a", "RELATED_TO", "b")

    resp = await client.get("/api/brain/visualize")
    data = resp.json()

    # Still one edge, but weight is 2
    assert data["_meta"]["nodes"] == 2
    assert data["_meta"]["edges"] == 1
    assert data["links"][0]["weight"] == 2


@pytest.mark.asyncio
async def test_many_entities(client):
    """A larger graph should still produce the correct counts."""
    entities = [f"entity_{i}" for i in range(50)]
    for i in range(49):
        _gb.add_triplet(entities[i], "LINKS_TO", entities[i + 1])

    resp = await client.get("/api/brain/visualize")
    data = resp.json()

    assert data["_meta"]["nodes"] == 50
    assert data["_meta"]["edges"] == 49
    assert len(data["nodes"]) == 50
    assert len(data["links"]) == 49


# ─── Response format contract ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_link_structure_uses_source_target_keys(client):
    """Every link must have 'source' and 'target' as strings (this is what react-force-graph-2d expects)."""
    _gb.add_triplet("machine learning", "REQUIRES", "data")

    resp = await client.get("/api/brain/visualize")
    data = resp.json()

    for link in data["links"]:
        assert isinstance(link["source"], str)
        assert isinstance(link["target"], str)
        # The library expects these field names specifically
        assert "source" in link
        assert "target" in link


@pytest.mark.asyncio
async def test_node_ids_are_unique(client):
    """No duplicate node ids in the response."""
    _gb.add_triplet("x", "RELATED_TO", "y")
    _gb.add_triplet("x", "RELATED_TO", "z")  # 'x' already exists

    resp = await client.get("/api/brain/visualize")
    data = resp.json()

    ids = [n["id"] for n in data["nodes"]]
    assert len(ids) == len(set(ids))  # All unique
