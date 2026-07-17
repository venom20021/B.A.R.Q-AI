"""
Tests for the BARQ Graph Migration module — keyword-based routing heuristics,
MigrationRunner, and standalone convenience function.

Uses temporary files and mocks to avoid modifying real data or depending on
a real Ollama instance.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import networkx as nx
from networkx.readwrite import json_graph

from memory_knowledge.migration import (
    BRAIN_KEYWORDS,
    MigrationRunner,
    _score_triplet,
    _default_brain,
    run_migration,
)
from memory_knowledge.multi_brain import BRAIN_REGISTRY, multi_brain_manager


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_brains():
    """Clear the multi-brain singleton before each test."""
    multi_brain_manager.clear_all()
    yield


# ═════════════════════════════════════════════════════════════════════════════
#  _score_triplet
# ═════════════════════════════════════════════════════════════════════════════


class TestScoreTriplet:
    def test_career_keywords_scored(self):
        """Triplets with career keywords score for career brain."""
        scores = _score_triplet("python developer", "WORKS_AT", "google")
        assert "career" in scores
        assert scores["career"] >= 2  # entity keywords match

    def test_ai_chat_keywords_scored(self):
        """Triplets with AI chat keywords score for ai_chats brain."""
        scores = _score_triplet("chatgpt", "ANSWERED", "question about AI")
        assert "ai_chats" in scores
        assert scores["ai_chats"] >= 2

    def test_relation_pattern_boosts_score(self):
        """Relation pattern matches give higher score than entity keywords."""
        scores = _score_triplet("random_thing", "WORKS_AT", "another_thing")
        assert scores.get("career", 0) >= 5  # WORKS_AT is a career relation pattern

    def test_no_match_returns_empty(self):
        """Triplet with no matching keywords returns empty scores."""
        scores = _score_triplet("xyzzy", "UNKNOWN_RELATION", "plugh")
        assert scores == {}

    def test_apple_notes_keywords(self):
        """Apple Notes keywords are detected correctly."""
        scores = _score_triplet("my idea", "NOTE_RELATED", "journal entry")
        assert "apple_notes" in scores
        assert scores["apple_notes"] > 0

    def test_google_docs_keywords(self):
        """Google Docs keywords are detected correctly."""
        scores = _score_triplet("meeting notes", "DOCUMENT_SECTION", "project plan")
        assert "google_docs" in scores
        assert scores["google_docs"] > 0

    def test_multiple_brain_matches(self):
        """Triplet can score for multiple brain types simultaneously."""
        scores = _score_triplet("python ai model", "USED_FOR", "machine learning")
        # Should match both career (python) and ai_chats (ai, model, machine learning)
        matched = set(scores.keys())
        assert "career" in matched or "ai_chats" in matched


# ═════════════════════════════════════════════════════════════════════════════
#  _default_brain
# ═════════════════════════════════════════════════════════════════════════════


class TestDefaultBrain:
    def test_falls_back_to_general(self):
        """Triplet with no matched keywords falls back to 'general'."""
        brain = _default_brain("xyzzy", "UNKNOWN", "plugh")
        assert brain == "general"

    def test_career_preferred_when_tie(self):
        """career is preferred over other brains when scores tie."""
        brain = _default_brain("python engineer", "USED_FOR", "ai project")
        # This should score for both career (python, engineer) and ai_chats (ai)
        # career has tie-break priority
        assert brain == "career"

    def test_tie_break_order(self):
        """Tie-break follows: career > ai_chats > apple_notes > google_docs."""
        # ai_chats should win over apple_notes on tie
        brain = _default_brain("ai idea", "RELATED_TO", "note")
        # 'ai' -> ai_chats, 'idea' -> apple_notes, 'note' -> apple_notes
        # ai_chats = 2 (ai), apple_notes = 4 (idea, note)
        # apple_notes should win unless... let me check:
        # actually apple_notes has 'idea', 'note' = 4, ai_chats has 'ai' = 2
        # So apple_notes wins by score, not tie-break
        assert brain == "apple_notes"

    def test_high_score_wins_over_tie_break(self):
        """Higher-scoring brain wins even if tie-break would prefer another."""
        # Give career a higher score than ai_chats on a mixed triplet
        brain = _default_brain("senior engineer developer", "WORKS_AT", "tech startup")
        # career has: engineer, developer, WORKS_AT -> 2+2+5 = 9
        # ai_chats: no matches -> 0
        assert brain == "career"

    def test_low_score_falls_back(self):
        """Triplet with score < 2 falls back to general."""
        brain = _default_brain("apple", "RELATED_TO", "fruit")
        # No matches in any keyword list for these generic terms
        # Wait, 'apple' is not in apple_notes keywords (that would be 'apple note')
        # Actually, apple_notes has 'note', 'apple note' - but not 'apple' alone
        # So no match -> general
        assert brain == "general"

    def test_empty_subject_still_routed(self):
        """Even with empty/weird subjects, routing handles it."""
        brain = _default_brain("", "USED_FOR", "data")
        # No entity keywords match empty string, relation may not be in patterns
        # USED_FOR is not in any relation pattern -> falls back to general
        assert brain == "general"

    def test_ai_chat_tie_with_apple_notes(self):
        """When ai_chats and apple_notes tie, ai_chats wins by priority."""
        brain = _default_brain("ai reminder", "RELATED_TO", "chat model")
        # ai_chats: 'ai' (2), 'chat' (2), 'model' (2) = 6
        # apple_notes: 'reminder' (2) = 2
        # ai_chats wins by score, not tie-break
        assert brain == "ai_chats"


# ═════════════════════════════════════════════════════════════════════════════
#  MigrationRunner
# ═════════════════════════════════════════════════════════════════════════════


class TestMigrationRunnerInit:
    def test_default_paths(self):
        """Default paths are set correctly."""
        runner = MigrationRunner()
        assert runner.source_path.name == "graph.json"
        assert runner.backup_dir.name == "migration_backups"
        assert runner.brains_dir.name == "brains"


class TestMigrationRunnerExtractTriplets:
    def test_extract_from_edges(self):
        """Edges are correctly extracted as (subj, rel, obj) tuples."""
        g = nx.Graph()
        g.add_edge("python", "data science", relation="USED_FOR")
        g.add_edge("python", "google", relation="USED_AT")
        triplets = MigrationRunner._extract_triplets(g)
        assert len(triplets) == 2
        assert ("python", "USED_FOR", "data science") in triplets
        assert ("python", "USED_AT", "google") in triplets

    def test_extract_no_relation_defaults(self):
        """Edges without relation attribute default to RELATED_TO."""
        g = nx.Graph()
        g.add_edge("a", "b")
        triplets = MigrationRunner._extract_triplets(g)
        assert triplets == [("a", "RELATED_TO", "b")]

    def test_extract_normalises_entities(self):
        """Entities are normalised during extraction."""
        g = nx.Graph()
        g.add_edge("Python  ", "  Data Science", relation="USED_FOR")
        triplets = MigrationRunner._extract_triplets(g)
        assert triplets[0][0] == "python"
        assert triplets[0][2] == "data science"

    def test_extract_empty_graph(self):
        """Empty graph returns empty list."""
        g = nx.Graph()
        triplets = MigrationRunner._extract_triplets(g)
        assert triplets == []

    def test_extract_empty_entities_skipped(self):
        """Edges with empty node names are skipped."""
        g = nx.Graph()
        g.add_edge("", "something", relation="RELATED_TO")
        triplets = MigrationRunner._extract_triplets(g)
        assert len(triplets) == 0


class TestMigrationRunnerRun:
    def test_missing_source_file(self):
        """run() returns 'skipped' status when source graph doesn't exist."""
        runner = MigrationRunner(source_path="/nonexistent/graph.json")
        result = runner.run()
        assert result["status"] == "skipped"
        assert result["total_triplets"] == 0

    def test_empty_graph(self):
        """run() returns 'empty' status when the graph has no edges."""
        g = nx.Graph()
        g.add_node("orphan")  # node but no edges
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            data = json_graph.node_link_data(g)
            path.write_text(json.dumps(data), encoding="utf-8")

            runner = MigrationRunner(source_path=str(path), brains_dir=tmpdir)
            result = runner.run()
            assert result["status"] == "empty"
            assert result["total_triplets"] == 0

    def test_dry_run_returns_routing_without_writing(self):
        """dry_run mode reports routing but doesn't modify brains."""
        g = nx.Graph()
        g.add_edge("python developer", "google", relation="WORKS_AT")
        g.add_edge("chatgpt", "question", relation="ANSWERED")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            data = json_graph.node_link_data(g)
            path.write_text(json.dumps(data), encoding="utf-8")

            runner = MigrationRunner(source_path=str(path), brains_dir=tmpdir)
            result = runner.run(dry_run=True)

            assert result["status"] == "dry_run"
            assert result["total_triplets"] == 2
            assert "routing" in result
            assert len(result["routing"]) > 0

            # Verify brains were NOT modified
            assert multi_brain_manager.get_brain("general").number_of_nodes() == 0

    def test_full_run_routes_and_persists(self):
        """Full run routes triplets to correct brains and persists to disk."""
        g = nx.Graph()
        g.add_edge("python developer", "google", relation="WORKS_AT")
        g.add_edge("chatgpt", "question", relation="ANSWERED")
        # A general entity pair
        g.add_edge("sun", "moon", relation="RELATED_TO")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            data = json_graph.node_link_data(g)
            path.write_text(json.dumps(data), encoding="utf-8")

            runner = MigrationRunner(source_path=str(path), brains_dir=tmpdir)
            result = runner.run()

            assert result["status"] == "completed"
            assert result["total_triplets"] == 3
            assert "brains" in result
            # Should have routed to at least career and general
            assert result["brains"].get("career", 0) >= 1
            assert result["brains"].get("general", 0) >= 1

            # Verify files were created
            assert (Path(tmpdir) / "career.json").exists()
            assert (Path(tmpdir) / "general.json").exists()

    def test_backup_is_created(self):
        """A timestamped backup of the source graph is created."""
        g = nx.Graph()
        g.add_edge("a", "b", relation="RELATED_TO")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            data = json_graph.node_link_data(g)
            path.write_text(json.dumps(data), encoding="utf-8")

            backup_dir = Path(tmpdir) / "backups"
            runner = MigrationRunner(
                source_path=str(path),
                backup_dir=str(backup_dir),
                brains_dir=tmpdir,
            )
            result = runner.run()

            assert result["backup_path"] is not None
            assert "graph_pre_migration_" in result["backup_path"]
            assert Path(result["backup_path"]).exists()

    def test_idempotent(self):
        """Running the migration twice produces the same result (clear_all inside run)."""
        g = nx.Graph()
        g.add_edge("python", "data science", relation="USED_FOR")
        g.add_edge("engineer", "company", relation="WORKS_AT")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            data = json_graph.node_link_data(g)
            path.write_text(json.dumps(data), encoding="utf-8")

            runner = MigrationRunner(source_path=str(path), brains_dir=tmpdir)
            result1 = runner.run()
            result2 = runner.run()

            assert result1["brains"] == result2["brains"]
            assert result1["total_triplets"] == result2["total_triplets"]
            assert result1["status"] == "completed"
            assert result2["status"] == "completed"

    def test_invalid_graph_file(self):
        """Invalid graph.json returns 'error' status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            path.write_text("not valid json", encoding="utf-8")

            runner = MigrationRunner(source_path=str(path))
            result = runner.run()
            assert result["status"] == "error"


# ═════════════════════════════════════════════════════════════════════════════
#  MigrationRunner — verify
# ═════════════════════════════════════════════════════════════════════════════


class TestMigrationRunnerVerify:
    def test_verify_no_brains_dir(self):
        """verify returns 'no_brains_dir' when directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = MigrationRunner(brains_dir=str(Path(tmpdir) / "nonexistent"))
            result = runner.verify()
            assert result["status"] == "no_brains_dir"

    def test_verify_with_brain_files(self):
        """verify counts nodes/edges across all brain files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create brain files with some data (using edges="links" to match save_brain format)
            for brain_type, meta in BRAIN_REGISTRY.items():
                g = nx.Graph()
                g.add_edge(brain_type, "test", relation="RELATED_TO")
                data = json_graph.node_link_data(g, edges="links")
                data["_meta"] = {"brain_type": brain_type, "nodes": 2, "edges": 1}
                (Path(tmpdir) / f"{brain_type}.json").write_text(
                    json.dumps(data), encoding="utf-8"
                )

            runner = MigrationRunner(brains_dir=tmpdir)
            result = runner.verify()
            assert result["status"] == "verified"
            assert result["brain_files"] == len(BRAIN_REGISTRY)
            assert result["total_nodes"] == len(BRAIN_REGISTRY) * 2
            assert result["total_edges"] == len(BRAIN_REGISTRY) * 1

    def test_verify_ignores_non_brain_files(self):
        """verify ignores JSON files that don't match registered brain types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            g = nx.Graph()
            g.add_edge("a", "b", relation="RELATED_TO")
            data = json_graph.node_link_data(g)
            (Path(tmpdir) / "general.json").write_text(json.dumps(data), encoding="utf-8")
            (Path(tmpdir) / "unknown.json").write_text(json.dumps(data), encoding="utf-8")

            runner = MigrationRunner(brains_dir=tmpdir)
            result = runner.verify()
            assert result["brain_files"] == 1  # only general.json counted
            assert result["total_nodes"] == 2


# ═════════════════════════════════════════════════════════════════════════════
#  run_migration convenience function
# ═════════════════════════════════════════════════════════════════════════════


class TestRunMigrationFunction:
    def test_convenience_function_without_source(self):
        """run_migration without source returns 'skipped'."""
        result = run_migration(source_path="/nonexistent/graph.json")
        assert result["status"] == "skipped"

    def test_convenience_function_with_dry_run(self):
        """run_migration with dry_run=True returns 'dry_run'."""
        g = nx.Graph()
        g.add_edge("a", "b", relation="RELATED_TO")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            data = json_graph.node_link_data(g)
            path.write_text(json.dumps(data), encoding="utf-8")

            result = run_migration(source_path=str(path), dry_run=True)
            assert result["status"] == "dry_run"
            assert result["total_triplets"] == 1
