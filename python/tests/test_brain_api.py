"""Tests for the brain_api visualization endpoint (GET /api/brain/visualize).

Verifies the endpoint returns the correct node-link graph format that
the React force-directed graph frontend expects.
"""

from unittest.mock import patch

import pytest

# The /api/brain/visualize endpoint reads the NEW multi_brain_manager
# (legacy graph_brain was migrated to domain-specific brains in an earlier
# commit). These tests must target the same manager the endpoint uses.
from memory_knowledge.multi_brain import multi_brain_manager


@pytest.fixture(autouse=True)
def _reset_graph(tmp_path):
    """Clear the 'general' brain and redirect persistence to a temp dir."""
    multi_brain_manager.clear_brain("general")
    # Save-on-mutate endpoints write brain JSON files — keep tests hermetic by
    # pointing the data dir at a per-test temp directory.
    multi_brain_manager.set_data_dir(str(tmp_path))
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
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")

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
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")
    multi_brain_manager.add_triplet("general", "python", "USED_AT", "google")
    multi_brain_manager.add_triplet("general", "data science", "REQUIRES", "statistics")

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
    multi_brain_manager.add_triplet("general", "react", "IS_A", "frontend framework")

    resp = await client.get("/api/brain/visualize")
    data = resp.json()

    for node in data["nodes"]:
        assert "label" in node
        assert node["label"] == node["id"]


# ─── Edge cases ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_triplet_increments_weight(client):
    """Adding the same triplet twice should increment the edge weight."""
    multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")
    multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")

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
        multi_brain_manager.add_triplet("general", entities[i], "LINKS_TO", entities[i + 1])

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
    multi_brain_manager.add_triplet("general", "machine learning", "REQUIRES", "data")

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
    multi_brain_manager.add_triplet("general", "x", "RELATED_TO", "y")
    multi_brain_manager.add_triplet("general", "x", "RELATED_TO", "z")  # 'x' already exists

    resp = await client.get("/api/brain/visualize")
    data = resp.json()

    ids = [n["id"] for n in data["nodes"]]
    assert len(ids) == len(set(ids))  # All unique


# ─── Mutation endpoints (ingest / triplet / clear / seed / import) ───────────


@pytest.mark.asyncio
async def test_add_triplet_endpoint(client):
    """POST /api/brain/{type}/triplet should add a triplet and report counts."""
    resp = await client.post(
        "/api/brain/general/triplet",
        json={"subject": "python", "relation": "USED_FOR", "object": "data science"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["triplets_added"] == 1
    assert data["nodes"] == 2
    assert data["edges"] == 1

    # The triplet is actually in the graph the frontend visualises
    viz = (await client.get("/api/brain/general/visualize")).json()
    assert viz["_meta"]["nodes"] == 2
    assert viz["_meta"]["edges"] == 1


@pytest.mark.asyncio
async def test_ingest_endpoint_uses_extractor(client):
    """POST /api/brain/{type}/ingest should use LLM extraction and persist results."""
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[
        ("python", "USED_FOR", "data science"),
        ("google", "USES", "python"),
    ]):
        resp = await client.post(
            "/api/brain/general/ingest",
            json={"text": "Python is used for data science at Google."},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["triplets_added"] == 2
    assert data["nodes"] == 3
    assert data["edges"] == 2
    assert data["provider"] == "ollama"
    assert data["note"] is None


@pytest.mark.asyncio
async def test_ingest_falls_back_to_gemini_when_ollama_empty(client):
    """When Ollama extracts nothing, the chain should try Gemini and report it."""
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[]), \
         patch("memory_knowledge.brain_api._extract_triplets_gemini", return_value=[
             ("python", "USED_FOR", "data science"),
         ]):
        resp = await client.post(
            "/api/brain/general/ingest",
            json={"text": "Python powers data science."},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["triplets_added"] == 1
    assert data["provider"] == "gemini"
    assert data["note"] is None
    # The triplet actually landed in the graph
    viz = (await client.get("/api/brain/general/visualize")).json()
    assert viz["_meta"]["nodes"] == 2


@pytest.mark.asyncio
async def test_ingest_endpoint_empty_extraction_returns_note(client):
    """Ingest with no extracted triplets should 200 with a note (never blocks)."""
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[]), \
         patch("memory_knowledge.brain_api._extract_triplets_gemini", return_value=[]):
        resp = await client.post("/api/brain/general/ingest", json={"text": "nothing here"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["triplets_added"] == 0
    assert data["provider"] == "none"
    assert data["note"] is not None


@pytest.mark.asyncio
async def test_extract_triplets_with_provider_prefers_ollama():
    """The provider chain should prefer Ollama when it returns relationships."""
    from memory_knowledge.brain_api import extract_triplets_with_provider
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[("a", "R", "b")]), \
         patch("memory_knowledge.brain_api._extract_triplets_gemini", return_value=[("c", "R", "d")]):
        triplets, provider = await extract_triplets_with_provider("some text")
    assert provider == "ollama"
    assert triplets == [("a", "R", "b")]


@pytest.mark.asyncio
async def test_extract_triplets_with_provider_uses_gemini_when_ollama_empty():
    """The provider chain should fall back to Gemini when Ollama yields nothing."""
    from memory_knowledge.brain_api import extract_triplets_with_provider
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[]), \
         patch("memory_knowledge.brain_api._extract_triplets_gemini", return_value=[("c", "R", "d")]):
        triplets, provider = await extract_triplets_with_provider("some text")
    assert provider == "gemini"
    assert triplets == [("c", "R", "d")]


@pytest.mark.asyncio
async def test_extract_triplets_with_provider_reports_none_when_both_fail():
    """The provider chain should report 'none' when every LLM is unavailable."""
    from memory_knowledge.brain_api import extract_triplets_with_provider
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[]), \
         patch("memory_knowledge.brain_api._extract_triplets_gemini", return_value=[]):
        triplets, provider = await extract_triplets_with_provider("some text")
    assert provider == "none"
    assert triplets == []


@pytest.mark.asyncio
async def test_clear_brain_endpoint(client):
    """POST /api/brain/{type}/clear should empty the brain."""
    multi_brain_manager.add_triplet("general", "a", "RELATES_TO", "b")
    resp = await client.post("/api/brain/general/clear")
    assert resp.status_code == 200
    data = resp.json()
    assert data["removed_nodes"] == 2
    assert multi_brain_manager.get_brain("general").number_of_nodes() == 0


@pytest.mark.asyncio
async def test_seed_demo_populates_empty_brains(client):
    """POST /api/brain/seed-demo should fill empty brains with starter data."""
    multi_brain_manager.clear_all()
    resp = await client.post("/api/brain/seed-demo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "seeded"
    assert data["total_added"] > 0
    assert multi_brain_manager.get_brain("general").number_of_nodes() > 0


@pytest.mark.asyncio
async def test_import_from_sources_direct_fallback(client):
    """Import should degrade gracefully to LLM-free direct triplets."""
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[]), \
         patch("memory_knowledge.brain_api._extract_triplets_gemini", return_value=[]):
        resp = await client.post("/api/brain/import-from-sources")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "imported"
    assert "direct_triplets" in data["results"]
    # LLM path reported 'none' provider (graceful degradation)
    assert data["results"].get("notes_provider") in ("none", None)


@pytest.mark.asyncio
async def test_import_from_sources_fills_ai_chats_from_chat_history(client):
    """AI chat history should populate the ai_chats brain via the LLM-free path."""
    import json
    from unittest.mock import AsyncMock

    from database import settings_dao

    multi_brain_manager.clear_brain("ai_chats")
    history = {
        "agent_1": [
            {"role": "user", "content": "how do i optimize python performance"},
            {"role": "assistant", "content": "try profiling with cProfile"},
        ]
    }
    with patch("memory_knowledge.brain_api._extract_triplets_ollama", return_value=[]), \
         patch("memory_knowledge.brain_api._extract_triplets_gemini", return_value=[]), \
         patch.object(
             settings_dao, "get_setting",
             new=AsyncMock(return_value=json.dumps(history)),
         ):
        resp = await client.post("/api/brain/import-from-sources")

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"]["direct_triplets"]["ai_chats"] > 0
    graph = multi_brain_manager.get_brain("ai_chats")
    assert graph.number_of_nodes() > 0
    # The topic derived from the user message should be a node
    assert any("optimize python performance" in n for n in graph.nodes)


@pytest.mark.asyncio
async def test_import_from_sources_ai_chats_llm_extraction(client):
    """Chat history should also flow through LLM extraction into ai_chats."""
    import json
    from unittest.mock import AsyncMock

    from database import settings_dao

    multi_brain_manager.clear_brain("ai_chats")
    history = {"agent_1": [{"role": "user", "content": "tell me about neural networks"}]}
    with patch(
        "memory_knowledge.brain_api._extract_triplets_ollama",
        return_value=[("neural networks", "RELATED_TO", "deep learning")],
    ), \
         patch.object(
             settings_dao, "get_setting",
             new=AsyncMock(return_value=json.dumps(history)),
         ):
        resp = await client.post("/api/brain/import-from-sources")

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"]["ai_chats_provider"] == "ollama"
    assert data["results"]["ai_chats_llm_triplets"] == 1
    graph = multi_brain_manager.get_brain("ai_chats")
    assert "neural networks" in graph.nodes
    assert "deep learning" in graph.nodes


@pytest.mark.asyncio
async def test_ensure_populated_seeds_when_all_empty(client):
    """ensure_populated() should seed + import when every brain is empty."""
    from memory_knowledge.brain_api import ensure_populated
    multi_brain_manager.clear_all()
    result = await ensure_populated()
    assert result["status"] == "populated"
    assert multi_brain_manager.get_brain("general").number_of_nodes() > 0


@pytest.mark.asyncio
async def test_ensure_populated_skips_when_data_exists(client):
    """ensure_populated() should not touch brains that already have data."""
    from memory_knowledge.brain_api import ensure_populated
    multi_brain_manager.add_triplet("general", "existing", "RELATES_TO", "data")
    result = await ensure_populated()
    assert result["status"] == "already_populated"


@pytest.mark.asyncio
async def test_ensure_populated_skips_when_persisted_files_exist(client):
    """First-run gate: persisted brain files must suppress auto-seeding even
    when the in-memory graphs are empty (user cleared + saved on purpose)."""
    from memory_knowledge.brain_api import ensure_populated
    multi_brain_manager.clear_all()
    # Simulate a prior Save — write empty graph files to the data dir.
    multi_brain_manager.save_all()
    result = await ensure_populated()
    assert result["status"] == "already_persisted"
    # Nothing should have been seeded.
    assert multi_brain_manager.get_brain("general").number_of_nodes() == 0


@pytest.mark.asyncio
async def test_unknown_brain_mutation_returns_404(client):
    """Mutations on an unregistered brain type should 404."""
    resp = await client.post("/api/brain/nope/ingest", json={"text": "x"})
    assert resp.status_code == 404
    resp = await client.post(
        "/api/brain/nope/triplet",
        json={"subject": "a", "relation": "R", "object": "b"},
    )
    assert resp.status_code == 404


# ─── Node details (GET /api/brain/{type}/node/{entity}) ─────────────────────


@pytest.mark.asyncio
async def test_node_details_returns_neighbours_and_stats(client):
    """GET /api/brain/{type}/node/{entity} should return neighbours + stats."""
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")
    multi_brain_manager.add_triplet("general", "python", "USED_AT", "google")
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "ml")

    resp = await client.get("/api/brain/general/node/python")
    assert resp.status_code == 200
    data = resp.json()

    assert data["found"] is True
    assert data["entity"] == "python"
    assert data["degree"] == 3
    assert data["weight_sum"] == 3

    # All three neighbours present with relations + weights
    nb_entities = {n["entity"] for n in data["neighbors"]}
    assert nb_entities == {"data science", "google", "ml"}
    for nb in data["neighbors"]:
        assert "relation" in nb
        assert nb["weight"] == 1

    # USED_FOR appears twice → top relation
    assert data["top_relations"][0]["relation"] == "USED_FOR"
    assert data["top_relations"][0]["count"] == 2


@pytest.mark.asyncio
async def test_node_details_unknown_entity_returns_found_false(client):
    """A missing entity should return found=False with empty neighbours."""
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")

    resp = await client.get("/api/brain/general/node/nothere")
    assert resp.status_code == 200
    data = resp.json()

    assert data["found"] is False
    assert data["degree"] == 0
    assert data["neighbors"] == []


@pytest.mark.asyncio
async def test_node_details_normalises_entity_case_insensitively(client):
    """Entity lookup should be case-insensitive (nodes are stored lowercased)."""
    multi_brain_manager.add_triplet("general", "Python", "USED_FOR", "Data Science")

    resp = await client.get("/api/brain/general/node/PYTHON")
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["entity"] == "python"
    assert data["neighbors"][0]["entity"] == "data science"


@pytest.mark.asyncio
async def test_node_details_weight_sum_counts_multi_edges(client):
    """weight_sum should accumulate edge weights across neighbours."""
    multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")
    multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")  # weight 2
    multi_brain_manager.add_triplet("general", "a", "LINKS_TO", "c")

    resp = await client.get("/api/brain/general/node/a")
    data = resp.json()

    assert data["found"] is True
    assert data["degree"] == 2       # two distinct neighbours
    assert data["weight_sum"] == 3   # 2 + 1
    # Heaviest neighbour sorts first
    assert data["neighbors"][0]["entity"] == "b"
    assert data["neighbors"][0]["weight"] == 2


@pytest.mark.asyncio
async def test_node_details_unknown_brain_returns_404(client):
    """Node details on an unregistered brain type should 404."""
    resp = await client.get("/api/brain/nope/node/python")
    assert resp.status_code == 404


# ─── Remove entity (POST /api/brain/{type}/node/{entity}/remove) ─────────────


@pytest.mark.asyncio
async def test_remove_entity_endpoint_deletes_node_and_edges(client):
    """Removing an entity should drop the node + every incident edge."""
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")
    multi_brain_manager.add_triplet("general", "python", "USED_AT", "google")
    multi_brain_manager.add_triplet("general", "data science", "REQUIRES", "statistics")
    assert multi_brain_manager.get_brain("general").number_of_nodes() == 4

    resp = await client.post("/api/brain/general/node/python/remove")
    assert resp.status_code == 200
    data = resp.json()

    assert data["found"] is True
    assert data["entity"] == "python"
    assert data["removed_edges"] == 2  # USED_FOR + USED_AT
    # Neighbours survive; only 'python' (and its edges) are gone
    assert data["nodes"] == 3
    assert data["edges"] == 1  # data science — statistics remains

    graph = multi_brain_manager.get_brain("general")
    assert "python" not in graph
    assert graph.has_edge("data science", "statistics")


@pytest.mark.asyncio
async def test_remove_entity_endpoint_missing_entity_is_graceful(client):
    """Removing a non-existent entity returns found=False with a 200 (never blocks)."""
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")

    resp = await client.post("/api/brain/general/node/nothere/remove")
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert data["removed_edges"] == 0
    # The graph is untouched
    assert multi_brain_manager.get_brain("general").number_of_nodes() == 2


@pytest.mark.asyncio
async def test_remove_entity_endpoint_unknown_brain_returns_404(client):
    """Removing from an unregistered brain type should 404."""
    resp = await client.post("/api/brain/nope/node/python/remove")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_entity_normalises_case_insensitively(client):
    """Removal should match nodes case-insensitively (stored lowercased)."""
    multi_brain_manager.add_triplet("general", "Python", "USED_FOR", "Data Science")

    resp = await client.post("/api/brain/general/node/PYTHON/remove")
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["entity"] == "python"
    assert "python" not in multi_brain_manager.get_brain("general")


@pytest.mark.asyncio
async def test_remove_entity_strips_related_timeline_entries(client):
    """Timeline entries referencing the removed entity are cleaned up."""
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")
    multi_brain_manager.add_triplet("general", "rust", "USED_FOR", "systems")

    resp = await client.post("/api/brain/general/node/python/remove")
    assert resp.status_code == 200
    data = resp.json()
    assert data["removed_timeline_entries"] >= 1

    # The 'rust' entry survives; nothing references 'python' anymore
    entries = multi_brain_manager.get_timeline(brain_type="general", limit=100)
    assert all(
        e.get("subject") != "python" and e.get("object_") != "python"
        for e in entries
    )
    assert any(e.get("subject") == "rust" for e in entries)


@pytest.mark.asyncio
async def test_remove_entity_timeline_cleanup_is_brain_scoped(client):
    """Removing from one brain must not strip other brains' timeline entries."""
    multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")
    multi_brain_manager.add_triplet("career", "python", "WORKS_WITH", "django")

    resp = await client.post("/api/brain/general/node/python/remove")
    assert resp.status_code == 200

    # The career brain's entry referencing 'python' survives untouched
    career_entries = multi_brain_manager.get_timeline(brain_type="career", limit=100)
    assert any(
        e.get("subject") == "python" and e.get("object_") == "django"
        for e in career_entries
    )
    general_entries = multi_brain_manager.get_timeline(brain_type="general", limit=100)
    assert all(
        e.get("subject") != "python" and e.get("object_") != "python"
        for e in general_entries
    )
