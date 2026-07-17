"""
Tests for MultiBrainManager — isolated domain-specific knowledge graphs.

Covers singleton behaviour, brain access, triplet insertion (with
normalisation, dedup, weight increments), serialisation (visualize),
persistence (save/load), statistics, clear operations, and edge cases.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
import networkx as nx

from memory_knowledge.multi_brain import (
    BRAIN_REGISTRY,
    MultiBrainManager,
    multi_brain_manager,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_brains():
    """Clear all brains and timeline before each test so tests are isolated."""
    multi_brain_manager.clear_all()
    multi_brain_manager.clear_timeline()
    yield


# ─── Singleton ───────────────────────────────────────────────────────────────


class TestSingleton:
    def test_get_instance_returns_same_object(self):
        """Multiple calls to get_instance() return the same object."""
        m1 = MultiBrainManager.get_instance()
        m2 = MultiBrainManager.get_instance()
        assert m1 is m2

    def test_new_returns_singleton(self):
        """Direct MultiBrainManager() constructor returns the singleton."""
        m1 = MultiBrainManager()
        m2 = MultiBrainManager()
        assert m1 is m2

    def test_all_brains_initialised(self):
        """All brains from BRAIN_REGISTRY should be present on init."""
        for brain_type in BRAIN_REGISTRY:
            assert brain_type in multi_brain_manager.brains
            assert brain_type in multi_brain_manager._locks

    def test_each_brain_is_isolated_graph(self):
        """Each brain should be an independent nx.Graph instance."""
        brains = multi_brain_manager.brains
        instances = {id(g) for g in brains.values()}
        assert len(instances) == len(brains)


# ─── Brain Access ────────────────────────────────────────────────────────────


class TestBrainAccess:
    def test_get_brain_returns_graph(self):
        """get_brain returns a networkx.Graph for a valid brain type."""
        graph = multi_brain_manager.get_brain("ai_chats")
        assert isinstance(graph, nx.Graph)

    def test_get_brain_raises_on_unknown(self):
        """get_brain raises KeyError for an unregistered brain type."""
        with pytest.raises(KeyError):
            multi_brain_manager.get_brain("nonexistent_brain")

    def test_is_valid_brain_true(self):
        """is_valid_brain returns True for registered brain types."""
        assert multi_brain_manager.is_valid_brain("general") is True
        assert multi_brain_manager.is_valid_brain("career") is True

    def test_is_valid_brain_false(self):
        """is_valid_brain returns False for unknown brain types."""
        assert multi_brain_manager.is_valid_brain("unknown") is False
        assert multi_brain_manager.is_valid_brain("") is False

    def test_list_brains_returns_all_with_metadata(self):
        """list_brains returns all registered brains with correct keys."""
        brains = multi_brain_manager.list_brains()
        assert len(brains) == len(BRAIN_REGISTRY)

        for b in brains:
            assert "type" in b
            assert "label" in b
            assert "description" in b
            assert "color" in b
            assert "neon_glow" in b
            assert "icon" in b
            assert "nodes" in b
            assert "edges" in b
            assert b["nodes"] == 0
            assert b["edges"] == 0

        types = {b["type"] for b in brains}
        assert types == set(BRAIN_REGISTRY.keys())

    def test_list_brains_reflects_insertions(self):
        """list_brains shows updated node/edge counts after insertions."""
        multi_brain_manager.add_triplet("career", "python", "USED_FOR", "data science")
        brains = multi_brain_manager.list_brains()
        career = next(b for b in brains if b["type"] == "career")
        assert career["nodes"] == 2
        assert career["edges"] == 1


# ─── Triplet Insertion ───────────────────────────────────────────────────────


class TestTripletInsertion:
    def test_add_triplet_creates_nodes_and_edge(self):
        """A single triplet creates two nodes and one edge."""
        multi_brain_manager.add_triplet("ai_chats", "python", "USED_FOR", "data science")
        graph = multi_brain_manager.get_brain("ai_chats")
        assert graph.number_of_nodes() == 2
        assert graph.number_of_edges() == 1

    def test_add_triplet_normalises_entities(self):
        """Entities are lowercased, stripped, truncated to 80 chars."""
        multi_brain_manager.add_triplet(
            "general", "  PYTHON Programming  ", "USED_BY", "  DATA SCIENCE  "
        )
        graph = multi_brain_manager.get_brain("general")
        assert graph.has_node("python programming")
        assert graph.has_node("data science")

    def test_add_triplet_normalises_relation(self):
        """Relation is uppercased and spaces replaced with underscores."""
        multi_brain_manager.add_triplet("general", "something", "used for", "data")
        graph = multi_brain_manager.get_brain("general")
        edge = list(graph.edges(data=True))[0]
        assert edge[2]["relation"] == "USED_FOR"

    def test_add_triplet_default_relation(self):
        """Empty relation defaults to RELATED_TO."""
        multi_brain_manager.add_triplet("general", "something", "", "data")
        graph = multi_brain_manager.get_brain("general")
        edge = list(graph.edges(data=True))[0]
        assert edge[2]["relation"] == "RELATED_TO"

    def test_add_triplet_empty_strings_ignored(self):
        """Empty subject or object are silently ignored."""
        multi_brain_manager.add_triplet("general", "", "RELATED_TO", "")
        graph = multi_brain_manager.get_brain("general")
        assert graph.number_of_nodes() == 0

    def test_add_triplet_unknown_brain_ignored(self):
        """Adding to an unknown brain type is silently ignored (no crash)."""
        multi_brain_manager.add_triplet("unknown_brain", "a", "RELATED_TO", "b")
        # Should not raise; just log a warning

    def test_duplicate_triplet_increments_weight(self):
        """Adding the same triplet twice increments the edge weight."""
        multi_brain_manager.add_triplet("career", "python", "USED_FOR", "data science")
        multi_brain_manager.add_triplet("career", "python", "USED_FOR", "data science")
        graph = multi_brain_manager.get_brain("career")
        assert graph.number_of_nodes() == 2
        assert graph.number_of_edges() == 1
        assert graph.edges["python", "data science"]["weight"] == 2

    def test_duplicate_with_different_relation_combines(self):
        """Adding same entities with different relations combines them."""
        multi_brain_manager.add_triplet("general", "python", "USED_FOR", "web dev")
        multi_brain_manager.add_triplet("general", "python", "USED_AT", "google")
        graph = multi_brain_manager.get_brain("general")
        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() == 2

    def test_add_triplet_isolation_between_brains(self):
        """Triplets added to one brain do not appear in another."""
        multi_brain_manager.add_triplet("ai_chats", "python", "USED_FOR", "data")
        multi_brain_manager.add_triplet("career", "java", "USED_FOR", "backend")
        ai_graph = multi_brain_manager.get_brain("ai_chats")
        career_graph = multi_brain_manager.get_brain("career")
        assert ai_graph.has_node("python")
        assert not career_graph.has_node("python")
        assert career_graph.has_node("java")
        assert not ai_graph.has_node("java")

    def test_add_triplet_truncates_long_entities(self):
        """Entities longer than 80 chars are truncated."""
        long_name = "a" * 200
        multi_brain_manager.add_triplet("general", long_name, "RELATED_TO", "b")
        graph = multi_brain_manager.get_brain("general")
        nodes = list(graph.nodes())
        assert len(nodes[0]) == 80

    def test_isolation_across_all_brains(self):
        """All 5 brains remain independent even with same entity names."""
        for brain in BRAIN_REGISTRY:
            multi_brain_manager.add_triplet(brain, "python", "RELATED_TO", "java")
        for brain in BRAIN_REGISTRY:
            graph = multi_brain_manager.get_brain(brain)
            assert graph.number_of_nodes() == 2
            assert graph.number_of_edges() == 1


# ─── Serialisation (visualize) ───────────────────────────────────────────────


class TestVisualize:
    def test_empty_brain_returns_valid_structure(self):
        """visualize on empty brain returns correct node-link structure."""
        data = multi_brain_manager.visualize("general")
        assert "nodes" in data
        assert "links" in data
        assert "_meta" in data
        assert data["nodes"] == []
        assert data["links"] == []

    def test_visualize_returns_nodes_and_links(self):
        """visualize returns correct node/link count for populated brain."""
        multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data science")
        data = multi_brain_manager.visualize("general")
        assert data["_meta"]["nodes"] == 2
        assert data["_meta"]["edges"] == 1
        assert len(data["nodes"]) == 2
        assert len(data["links"]) == 1

    def test_visualize_link_structure(self):
        """Each link has source, target, relation, and weight."""
        multi_brain_manager.add_triplet("general", "react", "IS_A", "framework")
        data = multi_brain_manager.visualize("general")
        link = data["links"][0]
        assert "source" in link
        assert "target" in link
        assert "relation" in link
        assert "weight" in link
        assert link["source"] == "react"
        assert link["target"] == "framework"
        assert link["relation"] == "IS_A"

    def test_visualize_meta_contains_brain_metadata(self):
        """_meta contains brain type, label, colors, and counts."""
        multi_brain_manager.add_triplet("apple_notes", "idea", "RELATED_TO", "thought")
        data = multi_brain_manager.visualize("apple_notes")
        meta = data["_meta"]
        assert meta["brain_type"] == "apple_notes"
        assert meta["label"] == "Apple Notes"
        assert "color" in meta
        assert "neon_glow" in meta
        assert meta["nodes"] == 2
        assert meta["edges"] == 1

    def test_visualize_raises_on_unknown_brain(self):
        """visualize raises KeyError for unknown brain type."""
        with pytest.raises(KeyError):
            multi_brain_manager.visualize("nonexistent")


# ─── Persistence ─────────────────────────────────────────────────────────────


class TestPersistence:
    def test_save_and_load_single_brain(self):
        """A brain can be saved to disk and loaded back."""
        multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data")
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save the brain
            ok = multi_brain_manager.save_brain("general", directory=tmpdir)
            assert ok is True

            # Clear and verify empty
            multi_brain_manager.clear_brain("general")
            assert multi_brain_manager.get_brain("general").number_of_nodes() == 0

            # Load back and verify
            ok = multi_brain_manager.load_brain("general", directory=tmpdir)
            assert ok is True
            graph = multi_brain_manager.get_brain("general")
            assert graph.number_of_nodes() == 2
            assert graph.number_of_edges() == 1

    def test_save_and_load_all_brains(self):
        """All brains can be saved and loaded back."""
        multi_brain_manager.add_triplet("ai_chats", "gpt", "IS_A", "model")
        multi_brain_manager.add_triplet("career", "engineer", "WORKS_AT", "techcorp")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Save all
            results = multi_brain_manager.save_all(directory=tmpdir)
            assert "ai_chats" in results
            assert "career" in results
            assert results["ai_chats"] >= 2
            assert results["career"] >= 2

            # Verify files exist
            assert (Path(tmpdir) / "ai_chats.json").exists()
            assert (Path(tmpdir) / "career.json").exists()
            assert (Path(tmpdir) / "general.json").exists()

            # Clear all and verify
            multi_brain_manager.clear_all()
            assert multi_brain_manager.get_brain("ai_chats").number_of_nodes() == 0

            # Load all back
            load_results = multi_brain_manager.load_all(directory=tmpdir)
            assert load_results.get("ai_chats") is True
            assert load_results.get("career") is True
            assert multi_brain_manager.get_brain("ai_chats").number_of_nodes() == 2

    def test_load_returns_false_for_missing_file(self):
        """load_brain returns False when the brain file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ok = multi_brain_manager.load_brain("general", directory=tmpdir)
            assert ok is False

    def test_save_brain_returns_false_for_unknown_brain(self):
        """save_brain returns False for unknown brain type."""
        ok = multi_brain_manager.save_brain("nonexistent")
        assert ok is False

    def test_load_brain_returns_false_for_unknown_brain(self):
        """load_brain returns False for unknown brain type."""
        ok = multi_brain_manager.load_brain("nonexistent")
        assert ok is False

    def test_load_returns_empty_for_missing_directory(self):
        """load_all returns empty dict when the brains directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir) / "nonexistent"
            results = multi_brain_manager.load_all(directory=str(empty_dir))
            assert results == {}

    def test_save_file_content_is_valid_json(self):
        """Saved brain files contain valid JSON with correct structure."""
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")
        with tempfile.TemporaryDirectory() as tmpdir:
            multi_brain_manager.save_brain("general", directory=tmpdir)
            raw = (Path(tmpdir) / "general.json").read_text(encoding="utf-8")
            data = json.loads(raw)
            assert "nodes" in data
            assert "links" in data
            assert "_meta" in data
            assert data["_meta"]["nodes"] == 2

    def test_save_all_creates_directory(self):
        """save_all creates the target directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_brains"
            assert not new_dir.exists()
            multi_brain_manager.save_all(directory=str(new_dir))
            assert new_dir.exists()


# ─── Timeline Persistence ────────────────────────────────────────────────────


class TestTimelinePersistence:
    def test_save_timeline_creates_file(self):
        """save_timeline writes a _timeline.json file to the directory."""
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")
        with tempfile.TemporaryDirectory() as tmpdir:
            ok = multi_brain_manager.save_timeline(directory=tmpdir)
            assert ok is True
            assert (Path(tmpdir) / "_timeline.json").exists()

    def test_save_timeline_content_structure(self):
        """Saved timeline file has correct structure with _meta and entries."""
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")
        with tempfile.TemporaryDirectory() as tmpdir:
            multi_brain_manager.save_timeline(directory=tmpdir)
            raw = (Path(tmpdir) / "_timeline.json").read_text(encoding="utf-8")
            data = json.loads(raw)
            assert "_meta" in data
            assert data["_meta"]["version"] == 1
            assert data["_meta"]["count"] >= 1
            assert "entries" in data
            assert len(data["entries"]) >= 1

    def test_save_timeline_entry_content(self):
        """Each saved timeline entry has all required fields."""
        multi_brain_manager.add_triplet("career", "python", "USED_FOR", "data science")
        with tempfile.TemporaryDirectory() as tmpdir:
            multi_brain_manager.save_timeline(directory=tmpdir)
            raw = (Path(tmpdir) / "_timeline.json").read_text(encoding="utf-8")
            data = json.loads(raw)
            entry = data["entries"][0]
            assert "timestamp" in entry
            assert entry["brain_type"] == "career"
            assert entry["subject"] == "python"
            assert entry["relation"] == "USED_FOR"
            assert entry["object_"] == "data science"
            assert "is_new_edge" in entry

    def test_load_timeline_restores_entries(self):
        """Timeline entries are restored from disk correctly."""
        multi_brain_manager.add_triplet("ai_chats", "gpt", "IS_A", "model")
        multi_brain_manager.add_triplet("career", "engineer", "WORKS_AT", "techcorp")

        with tempfile.TemporaryDirectory() as tmpdir:
            multi_brain_manager.save_timeline(directory=tmpdir)

            # Clear in-memory timeline
            cleared = multi_brain_manager.clear_timeline()
            assert cleared >= 2
            assert len(multi_brain_manager.get_timeline()) == 0

            # Load back
            ok = multi_brain_manager.load_timeline(directory=tmpdir)
            assert ok is True
            restored = multi_brain_manager.get_timeline(limit=100)
            assert len(restored) >= 2

    def test_load_timeline_preserves_entry_content(self):
        """Restored entries retain all original fields."""
        multi_brain_manager.add_triplet("general", "python", "USED_FOR", "data")

        with tempfile.TemporaryDirectory() as tmpdir:
            multi_brain_manager.save_timeline(directory=tmpdir)
            multi_brain_manager.clear_timeline()
            multi_brain_manager.load_timeline(directory=tmpdir)

            restored = multi_brain_manager.get_timeline(limit=100)
            entry = restored[0]
            assert entry["subject"] == "python"
            assert entry["relation"] == "USED_FOR"
            assert entry["object_"] == "data"
            assert entry["brain_type"] == "general"

    def test_load_timeline_missing_file_returns_true(self):
        """Missing timeline file returns True (not an error, just empty history)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ok = multi_brain_manager.load_timeline(directory=tmpdir)
            assert ok is True
            assert len(multi_brain_manager.get_timeline()) == 0

    def test_load_timeline_corrupt_file_returns_false(self):
        """Corrupt timeline file returns False gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "_timeline.json"
            file_path.write_text("not valid json", encoding="utf-8")
            ok = multi_brain_manager.load_timeline(directory=tmpdir)
            assert ok is False
            assert len(multi_brain_manager.get_timeline()) == 0

    def test_save_and_load_via_save_all(self):
        """Timeline is persisted alongside brains via save_all/load_all."""
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")

        with tempfile.TemporaryDirectory() as tmpdir:
            # save_all persists brains + timeline
            multi_brain_manager.save_all(directory=tmpdir)

            # Verify _timeline.json was created
            assert (Path(tmpdir) / "_timeline.json").exists()

            # Clear everything
            multi_brain_manager.clear_all()
            multi_brain_manager.clear_timeline()
            assert len(multi_brain_manager.get_timeline()) == 0

            # load_all restores brains + timeline
            multi_brain_manager.load_all(directory=tmpdir)
            restored = multi_brain_manager.get_timeline(limit=100)
            assert len(restored) >= 1

    def test_load_timeline_respects_max_entries(self):
        """Timeline loading respects the max entries cap."""
        # Save with many entries
        for i in range(50):
            multi_brain_manager.add_triplet("general", f"a{i}", "RELATED_TO", f"b{i}")

        with tempfile.TemporaryDirectory() as tmpdir:
            multi_brain_manager.save_timeline(directory=tmpdir)
            multi_brain_manager.clear_timeline()

            # Set a small max and load
            original_max = multi_brain_manager._max_timeline_entries
            multi_brain_manager._max_timeline_entries = 10
            multi_brain_manager.load_timeline(directory=tmpdir)

            restored = multi_brain_manager.get_timeline(limit=100)
            assert len(restored) <= 10

            # Restore original
            multi_brain_manager._max_timeline_entries = original_max


# ─── Statistics ──────────────────────────────────────────────────────────────


class TestStatistics:
    def test_empty_brain_stats(self):
        """get_statistics on empty brain returns zeros."""
        stats = multi_brain_manager.get_statistics("general")
        assert stats["nodes"] == 0
        assert stats["edges"] == 0
        assert stats["density"] == 0.0
        assert stats["connected_components"] == 0
        assert stats["top_entities"] == []

    def test_populated_brain_stats(self):
        """get_statistics returns correct values for a populated brain."""
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")
        multi_brain_manager.add_triplet("general", "b", "RELATED_TO", "c")
        stats = multi_brain_manager.get_statistics("general")
        assert stats["nodes"] == 3
        assert stats["edges"] == 2
        assert stats["density"] > 0
        assert stats["connected_components"] == 1
        assert len(stats["top_entities"]) <= 5

    def test_stats_raises_on_unknown_brain(self):
        """get_statistics raises KeyError for unknown brain type."""
        with pytest.raises(KeyError):
            multi_brain_manager.get_statistics("unknown")

    def test_top_entities_ordered_by_centrality(self):
        """top_entities in stats should be ordered by centrality descending."""
        # a connected to many → highest centrality
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "b")
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "c")
        multi_brain_manager.add_triplet("general", "a", "RELATED_TO", "d")
        multi_brain_manager.add_triplet("general", "b", "RELATED_TO", "c")
        stats = multi_brain_manager.get_statistics("general")
        entities = [e["entity"] for e in stats["top_entities"]]
        assert entities[0] == "a"


# ─── Clear Operations ────────────────────────────────────────────────────────


class TestClear:
    def test_clear_all_removes_all_nodes(self):
        """clear_all removes nodes and edges from every brain."""
        for brain in BRAIN_REGISTRY:
            multi_brain_manager.add_triplet(brain, "x", "RELATED_TO", "y")
        multi_brain_manager.clear_all()
        for brain in BRAIN_REGISTRY:
            assert multi_brain_manager.get_brain(brain).number_of_nodes() == 0

    def test_clear_brain_removes_only_that_brain(self):
        """clear_brain only clears the specified brain."""
        multi_brain_manager.add_triplet("ai_chats", "x", "RELATED_TO", "y")
        multi_brain_manager.add_triplet("career", "x", "RELATED_TO", "y")
        multi_brain_manager.clear_brain("ai_chats")
        assert multi_brain_manager.get_brain("ai_chats").number_of_nodes() == 0
        assert multi_brain_manager.get_brain("career").number_of_nodes() == 2

    def test_clear_brain_returns_false_for_unknown(self):
        """clear_brain returns False for unknown brain type."""
        result = multi_brain_manager.clear_brain("nonexistent")
        assert result is False

    def test_clear_brain_returns_true_for_valid(self):
        """clear_brain returns True when brain is cleared successfully."""
        multi_brain_manager.add_triplet("general", "x", "RELATED_TO", "y")
        result = multi_brain_manager.clear_brain("general")
        assert result is True


# ─── Thread Safety ───────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_adds_do_not_corrupt(self):
        """Adding triplets from multiple threads doesn't corrupt the graph."""
        import threading

        results: list[Exception] = []

        def add_triplet(brain: str, subj: str, rel: str, obj: str) -> None:
            try:
                multi_brain_manager.add_triplet(brain, subj, rel, obj)
            except Exception as e:
                results.append(e)

        threads = [
            threading.Thread(target=add_triplet, args=("general", f"entity_{i}", "RELATED_TO", f"other_{i}"))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 0
        graph = multi_brain_manager.get_brain("general")
        assert graph.number_of_nodes() == 40
        assert graph.number_of_edges() == 20
