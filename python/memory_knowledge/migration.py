"""
BARQ Graph Migration — distributes old monolithic ``graph_brain`` data into
the domain-specific ``MultiBrainManager`` system.

This script reads the legacy ``data/graph.json`` (saved by ``BARQGraphBrain``),
extracts all ``(subject, relation, object)`` triplets, routes each triplet to
the most appropriate brain using keyword heuristics, and persists each brain
as an individual ``data/brains/{brain_type}.json`` file.

It is **idempotent**: running it multiple times produces the same result
because it reads from the source graph and clears the target brains first.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import networkx as nx
from networkx.readwrite import json_graph

from memory_knowledge.multi_brain import BRAIN_REGISTRY, multi_brain_manager

logger = logging.getLogger("barq.migration")

# ─── Default paths ──────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SOURCE = _PROJECT_ROOT / "data" / "graph.json"
_DEFAULT_BACKUP_DIR = _PROJECT_ROOT / "data" / "migration_backups"
_DEFAULT_BRAINS_DIR = _PROJECT_ROOT / "data" / "brains"

# ─── Keyword-based routing heuristics ──────────────────────────────────────

# Each brain type has a list of (entity_keywords, relation_regex) pairs.
# If an entity name contains one of the keywords OR the relation matches
# the regex, the triplet scores for that brain.
# Higher score = more specific match.

BRAIN_KEYWORDS: dict[str, dict[str, Any]] = {
    "career": {
        "entity_keywords": [
            "job", "career", "company", "salary", "interview", "resume",
            "skill", "experience", "position", "role", "hire", "recruit",
            "engineer", "developer", "manager", "designer", "analyst",
            "internship", "remote", "full.time", "part.time", "contract",
            "startup", "corporation", "enterprise", "freelance",
            "cto", "ceo", "vp", "director", "lead", "senior", "junior",
            "qualification", "requirement", "responsibility", "benefit",
            "python", "javascript", "typescript", "react", "node",
            "aws", "docker", "kubernetes", "sql", "nosql", "api",
        ],
        "relation_patterns": [
            r"WORKS_AT", r"EMPLOYED_BY", r"HAS_SKILL", r"REQUIRES",
            r"APPLIED_TO", r"INTERVIEWED_AT", r"OFFERED_BY",
            r"LOCATED_IN", r"REMOTE_", r"SALARY_", r"COMPANY_",
        ],
    },
    "ai_chats": {
        "entity_keywords": [
            "ai", "artificial intelligence", "chat", "gpt", "llm",
            "model", "prompt", "agent", "assistant", "conversation",
            "message", "user", "assistant", "bot", "dialog",
            "machine learning", "deep learning", "neural", "transformer",
            "token", "embedding", "vector", "training", "inference",
            "openai", "anthropic", "claude", "gemini", "ollama",
            "llama", "mistral", "language model",
        ],
        "relation_patterns": [
            r"ASKED", r"ANSWERED", r"RESPONDED_WITH", r"MENTIONED",
            r"EXPLAINED", r"SUMMARIZED", r"TRANSLATED", r"GENERATED",
        ],
    },
    "apple_notes": {
        "entity_keywords": [
            "note", "apple note", "idea", "thought", "journal",
            "diary", "reminder", "memo", "personal", "brainstorm",
            "reflection", "goal", "habit", "todo", "task",
            "shopping", "recipe", "bookmark", "quote",
        ],
        "relation_patterns": [
            r"NOTE_", r"REMINDER_", r"JOURNAL_", r"IDEA_",
        ],
    },
    "gemini_chats": {
        "entity_keywords": [
            "gemini", "google gemini", "gemini flash", "gemini pro",
            "gemini vision", "gemini live", "gemini ultra",
            "gemini nano", "gemini 2", "gemini 1.5", "gemini 2.5",
            "bard", "google ai", "vertex ai",
        ],
        "relation_patterns": [
            r"GEMINI_", r"GENERATED_", r"VISION_", r"LIVE_",
        ],
    },
    "google_docs": {
        "entity_keywords": [
            "document", "google doc", "report", "proposal",
            "meeting notes", "project plan", "specification",
            "research paper", "article", "draft", "manuscript",
            "spreadsheet", "presentation", "slides",
        ],
        "relation_patterns": [
            r"DOCUMENT_", r"SECTION_", r"HEADING_", r"PARAGRAPH_",
        ],
    },
}


def _score_triplet(subject: str, relation: str, object_: str) -> dict[str, int]:
    """Score a triplet against each brain type using keyword heuristics.

    Returns a dict mapping brain_type → score (higher = more relevant).
    """
    scores: dict[str, int] = {}
    for brain_type, rules in BRAIN_KEYWORDS.items():
        score = 0
        text = f"{subject} {object_}".lower()
        # Entity keyword matches (substring)
        for kw in rules["entity_keywords"]:
            if kw in text:
                score += 2
        # Relation pattern matches (regex on the relation field)
        for pat in rules["relation_patterns"]:
            if re.search(pat, relation, re.IGNORECASE):
                score += 5  # relation matches are stronger signals
        if score > 0:
            scores[brain_type] = score
    return scores


def _default_brain(subject: str, relation: str, object_: str) -> str:
    """Determine the best brain for a triplet, falling back to ``general``.

    Strategy:
    1. Score against all keyword-defined brains
    2. If a brain scores >= 5, pick the highest-scoring one
    3. If multiple tie for highest, prefer career > ai_chats > apple_notes > google_docs
    4. Otherwise, route to ``general``
    """
    scores = _score_triplet(subject, relation, object_)
    if not scores:
        return "general"

    # Find max score
    max_score = max(scores.values())
    if max_score < 2:
        return "general"

    # Collect all brains with max score
    candidates = [bt for bt, s in scores.items() if s == max_score]
    if len(candidates) == 1:
        return candidates[0]

    # Tie-break by priority
    priority = ["career", "ai_chats", "gemini_chats", "apple_notes", "google_docs"]
    for bt in priority:
        if bt in candidates:
            return bt
    return candidates[0]


# ═════════════════════════════════════════════════════════════════════════════
#  MigrationRunner
# ═════════════════════════════════════════════════════════════════════════════


class MigrationRunner:
    """Reads a legacy ``graph.json`` file, distributes its triplets across
    the domain-specific brains via ``MultiBrainManager``, and persists each
    brain to disk.

    Usage::

        runner = MigrationRunner()
        result = runner.run()
        print(result)
    """

    def __init__(
        self,
        source_path: Optional[str] = None,
        backup_dir: Optional[str] = None,
        brains_dir: Optional[str] = None,
    ) -> None:
        self.source_path = Path(source_path or _DEFAULT_SOURCE)
        self.backup_dir = Path(backup_dir or _DEFAULT_BACKUP_DIR)
        self.brains_dir = Path(brains_dir or _DEFAULT_BRAINS_DIR)

    # ── Run ─────────────────────────────────────────────────────────────

    def run(self, dry_run: bool = False) -> dict[str, Any]:
        """Execute the migration.

        Args:
            dry_run: If True, only report what would happen without writing.

        Returns:
            Dict with keys: ``status``, ``source_file``, ``total_triplets``,
            ``brains`` (mapping brain → count), ``errors``, ``backup_path``.
        """
        if not self.source_path.exists():
            return {
                "status": "skipped",
                "source_file": str(self.source_path),
                "reason": "Source graph file not found — nothing to migrate",
                "total_triplets": 0,
                "brains": {},
                "errors": [],
            }

        # Read the old graph
        try:
            raw = self.source_path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw)
            old_graph: nx.Graph = json_graph.node_link_graph(data)
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
            logger.error("[Migration] Failed to read source graph: %s", exc)
            return {
                "status": "error",
                "source_file": str(self.source_path),
                "error": f"Failed to read source graph: {exc}",
                "total_triplets": 0,
                "brains": {},
                "errors": [str(exc)],
            }

        # Extract triplets from graph edges
        triplets: list[tuple[str, str, str]] = self._extract_triplets(old_graph)

        if not triplets:
            return {
                "status": "empty",
                "source_file": str(self.source_path),
                "reason": "Source graph contains no edges",
                "total_triplets": 0,
                "brains": {},
                "errors": [],
            }

        # Route each triplet to a brain
        routing: dict[str, list[tuple[str, str, str]]] = {}
        for subj, rel, obj in triplets:
            brain = _default_brain(subj, rel, obj)
            routing.setdefault(brain, []).append((subj, rel, obj))

        if dry_run:
            brain_counts = {bt: len(triplets) for bt, triplets in routing.items()}
            return {
                "status": "dry_run",
                "source_file": str(self.source_path),
                "total_triplets": len(triplets),
                "brains": brain_counts,
                "routing": {
                    bt: [{"subject": s, "relation": r, "object": o} for s, r, o in t]
                    for bt, t in routing.items()
                },
                "errors": [],
            }

        # Clear target brains and insert triplets
        errors: list[str] = []
        brain_counts: dict[str, int] = {}
        multi_brain_manager.clear_all()

        for brain_type, brain_triplets in routing.items():
            if brain_type not in BRAIN_REGISTRY:
                errors.append(f"Unknown brain type '{brain_type}' — skipping {len(brain_triplets)} triplets")
                continue
            count = 0
            for subj, rel, obj in brain_triplets:
                multi_brain_manager.add_triplet(brain_type, subj, rel, obj)
                count += 1
            brain_counts[brain_type] = count

        # Backup old graph file
        backup_path: Optional[str] = None
        try:
            backup_path = self._backup_source()
        except OSError as exc:
            errors.append(f"Backup failed: {exc}")

        # Persist all brains to disk
        save_results = multi_brain_manager.save_all(directory=str(self.brains_dir))
        total_saved = sum(save_results.values())

        logger.info(
            "[Migration] Complete: %d triplets → %d brains (%d total nodes saved). %d errors.",
            len(triplets), len(brain_counts), total_saved, len(errors),
        )

        return {
            "status": "completed",
            "source_file": str(self.source_path),
            "total_triplets": len(triplets),
            "brains": brain_counts,
            "nodes_saved": save_results,
            "backup_path": backup_path,
            "errors": errors if errors else None,
        }

    # ── Triplet Extraction ──────────────────────────────────────────────

    @staticmethod
    def _extract_triplets(graph: nx.Graph) -> list[tuple[str, str, str]]:
        """Convert NetworkX edges into ``(subject, relation, object)`` tuples.

        Each edge in the graph has a ``relation`` attribute. If none is set,
        defaults to ``"RELATED_TO"``.
        """
        triplets: list[tuple[str, str, str]] = []
        for u, v, data in graph.edges(data=True):
            subj = str(u).strip().lower()[:80]
            obj = str(v).strip().lower()[:80]
            rel = str(data.get("relation", "RELATED_TO")).strip().upper().replace(" ", "_")[:50]
            if subj and obj:
                triplets.append((subj, rel, obj))
        return triplets

    # ── Backup ──────────────────────────────────────────────────────────

    def _backup_source(self) -> str:
        """Copy the source graph.json to a timestamped backup file.

        Returns:
            Path to the backup file.
        """
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"graph_pre_migration_{timestamp}.json"
        shutil.copy2(str(self.source_path), str(backup_path))
        logger.info("[Migration] Backed up old graph to %s", backup_path)
        return str(backup_path)

    # ── Verification ────────────────────────────────────────────────────

    def verify(self) -> dict[str, Any]:
        """Compare the sum of all brain nodes vs. the original graph.

        Returns a dict with counts and any mismatch warnings.
        """
        brains_dir = self.brains_dir
        if not brains_dir.exists():
            return {"status": "no_brains_dir", "brains_dir": str(brains_dir)}

        brain_nodes = 0
        brain_edges = 0
        brain_files = 0
        for f in sorted(brains_dir.iterdir()):
            if f.suffix == ".json" and f.stem in BRAIN_REGISTRY:
                try:
                    raw = f.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    brain_nodes += len(data.get("nodes", []))
                    brain_edges += len(data.get("links", []))
                    brain_files += 1
                except (json.JSONDecodeError, OSError):
                    pass

        return {
            "status": "verified",
            "brains_dir": str(brains_dir),
            "brain_files": brain_files,
            "total_nodes": brain_nodes,
            "total_edges": brain_edges,
            "registered_brains": len(BRAIN_REGISTRY),
        }


# ═════════════════════════════════════════════════════════════════════════════
#  Standalone runner
# ═════════════════════════════════════════════════════════════════════════════


def run_migration(
    source_path: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Convenience function to run the migration programmatically.

    Args:
        source_path: Path to the legacy ``graph.json`` file.
        dry_run: If True, report only without modifying any data.

    Returns:
        Migration result dict.
    """
    runner = MigrationRunner(source_path=source_path)
    return runner.run(dry_run=dry_run)


# ═════════════════════════════════════════════════════════════════════════════
#  CLI Entrypoint
# ═════════════════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI entrypoint for the migration tool.

    Usage::

        python -m memory_knowledge.migration
        python -m memory_knowledge.migration --source path/to/graph.json
        python -m memory_knowledge.migration --dry-run
        python -m memory_knowledge.migration --verify
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="BARQ Graph Migration — distribute old graph data into domain-specific brains",
    )
    parser.add_argument(
        "--source", "-s",
        type=str,
        default=None,
        help=f"Path to the legacy graph.json (default: {_DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Report what would be migrated without writing anything",
    )
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify the current state of brain files without migrating",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    runner = MigrationRunner(source_path=args.source)

    if args.verify:
        print("Verifying current brain state ...")
        result = runner.verify()
        print(f"  Brains directory: {result.get('brains_dir')}")
        print(f"  Brain files:      {result.get('brain_files')}/{result.get('registered_brains')}")
        print(f"  Total nodes:      {result.get('total_nodes')}")
        print(f"  Total edges:      {result.get('total_edges')}")
        return

    print(f"Running migration{'' if not args.dry_run else ' (DRY RUN)'} ...")
    print(f"  Source: {runner.source_path}")
    result = runner.run(dry_run=args.dry_run)

    print(f"  Status:           {result.get('status')}")
    print(f"  Total triplets:   {result.get('total_triplets')}")

    brains = result.get("brains", {})
    if brains:
        print("  Per-brain routing:")
        for brain_type, count in sorted(brains.items()):
            label = BRAIN_REGISTRY.get(brain_type, {}).get("label", brain_type)
            print(f"    {label:20s}  {count:4d} triplets")

    if args.dry_run and result.get("routing"):
        print("\n  Detailed routing:")
        for brain_type, items in sorted(result["routing"].items()):
            for item in items:
                print(f"    [{brain_type:15s}] ({item['subject']}, {item['relation']}, {item['object']})")

    errors = result.get("errors")
    if errors:
        print("  Errors:")
        for err in errors:
            print(f"    ⚠ {err}")

    backup = result.get("backup_path")
    if backup:
        print(f"  Backup saved to: {backup}")

    print("Done.")


if __name__ == "__main__":
    main()
