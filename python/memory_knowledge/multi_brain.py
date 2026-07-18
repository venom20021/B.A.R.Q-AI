"""
Multi-Brain Manager — Isolated Domain-Specific Knowledge Graphs.

Instead of a single monolithic knowledge graph, BARQ uses isolated
``NetworkX`` graphs per domain (e.g. Apple Notes, AI Chats, Career)
to prevent information overload and keep each domain's entities clean.

Each brain:
- Has its own ``nx.Graph()`` instance (completely isolated)
- Has its own threading lock for safe concurrent access
- Can be serialised to node-link JSON independently
- Has a colour theme used by the frontend for visual differentiation
- Has a timeline event log recording all ``add_triplet`` calls for the
  Timeline/History frontend view
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import networkx as nx
from networkx.readwrite import json_graph

logger = logging.getLogger("barq.multi_brain")


# ─── Brain Metadata ──────────────────────────────────────────────────────────

BRAIN_REGISTRY: dict[str, dict[str, Any]] = {
    "apple_notes": {
        "label": "Apple Notes",
        "description": "Extracted knowledge from Apple Notes exports",
        "color": "#f59e0b",         # amber / warm gold
        "neon_glow": "rgba(245,158,11,0.5)",
        "icon": "sticky-note",
    },
    "google_docs": {
        "label": "Google Docs",
        "description": "Extracted knowledge from Google Documents",
        "color": "#3b82f6",         # blue
        "neon_glow": "rgba(59,130,246,0.5)",
        "icon": "file-text",
    },
    "ai_chats": {
        "label": "AI Chats",
        "description": "Knowledge from AI chat conversations",
        "color": "#10b981",         # emerald / neon green
        "neon_glow": "rgba(16,185,129,0.5)",
        "icon": "message-circle",
    },
    "career": {
        "label": "Career Engine",
        "description": "Job descriptions, skills, companies, and career data",
        "color": "#a855f7",         # purple / violet
        "neon_glow": "rgba(168,85,247,0.5)",
        "icon": "briefcase",
    },
    "gemini_chats": {
        "label": "Gemini Chats",
        "description": "Conversations and knowledge from Google Gemini interactions",
        "color": "#d946ef",         # fuchsia / magenta
        "neon_glow": "rgba(217,70,239,0.5)",
        "icon": "sparkles",
    },
    "general": {
        "label": "General Knowledge",
        "description": "Catch-all knowledge from auto-extraction and ingestion",
        "color": "#818cf8",         # indigo
        "neon_glow": "rgba(129,140,248,0.5)",
        "icon": "brain",
    },
}


# ─── Timeline Event Type ────────────────────────────────────────────────────

TimelineEntry = dict[str, Any]
"""A single timeline entry recording a triplet addition.

Keys:
- ``timestamp``: ISO-8601 UTC string
- ``brain_type``: Which brain received the triplet
- ``subject``: Normalised subject entity
- ``relation``: Normalised relation type
- ``object_``: Normalised object entity
- ``is_new_edge``: True if this created a new edge (vs incrementing weight)
"""


# ═════════════════════════════════════════════════════════════════════════════
#  MultiBrainManager
# ═════════════════════════════════════════════════════════════════════════════


class MultiBrainManager:
    """Thread-safe manager for multiple isolated domain-specific graphs.

    Usage:
        >>> manager = MultiBrainManager.get_instance()
        >>> data = manager.visualize("ai_chats")
        >>> all_brains = manager.list_brains()
        >>> manager.add_triplet("career", "python", "USED_FOR", "data science")
    """

    _instance: Optional[MultiBrainManager] = None
    _class_lock = threading.Lock()

    # ── Singleton ─────────────────────────────────────────────────────────

    def __new__(cls) -> MultiBrainManager:
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    cls._instance = obj
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._class_lock:
            if self._initialized:
                return

            self.brains: dict[str, nx.Graph] = {}
            self._locks: dict[str, threading.Lock] = {}
            self._timeline: list[TimelineEntry] = []
            self._timeline_lock = threading.Lock()
            self._data_dir: str = ""
            self._max_timeline_entries: int = 2000

            for brain_type in BRAIN_REGISTRY:
                self.brains[brain_type] = nx.Graph()
                self._locks[brain_type] = threading.Lock()

            self._initialized = True
            logger.info(
                "MultiBrainManager initialised with %d brains: %s",
                len(self.brains),
                ", ".join(self.brains.keys()),
            )

    @classmethod
    def get_instance(cls) -> MultiBrainManager:
        """Return or create the singleton multi-brain manager."""
        if cls._instance is None:
            cls()
        assert cls._instance is not None
        return cls._instance

    # ── Brain Access ──────────────────────────────────────────────────────

    def get_brain(self, brain_type: str) -> nx.Graph:
        """Get the isolated graph for a specific brain type.

        Raises:
            KeyError: If *brain_type* is not a registered brain.
        """
        if brain_type not in self.brains:
            raise KeyError(
                f"Unknown brain type '{brain_type}'. "
                f"Available: {', '.join(self.brains.keys())}"
            )
        return self.brains[brain_type]

    def get_lock(self, brain_type: str) -> threading.Lock:
        """Get the thread lock for a specific brain type."""
        return self._locks[brain_type]

    def is_valid_brain(self, brain_type: str) -> bool:
        """Check if *brain_type* is a registered brain."""
        return brain_type in self.brains

    def list_brains(self) -> list[dict[str, Any]]:
        """Return metadata for all registered brains with stats.

        Returns:
            List of dicts with keys: ``type``, ``label``, ``description``,
            ``color``, ``neon_glow``, ``icon``, ``nodes``, ``edges``.
        """
        results: list[dict[str, Any]] = []
        for brain_type, meta in BRAIN_REGISTRY.items():
            graph = self.brains[brain_type]
            results.append({
                "type": brain_type,
                "label": meta["label"],
                "description": meta["description"],
                "color": meta["color"],
                "neon_glow": meta["neon_glow"],
                "icon": meta["icon"],
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
            })
        return results

    # ── Direct Triplet Insertion ──────────────────────────────────────────

    def add_triplet(
        self,
        brain_type: str,
        subject: str,
        relation: str,
        object_: str,
    ) -> None:
        """Add a single triplet to a specific brain.

        Args:
            brain_type: Which brain to add to (e.g. ``"ai_chats"``).
            subject: Source entity name.
            relation: Relationship type (``UPPERCASE_SNAKE_CASE``).
            object_: Target entity name.
        """
        if brain_type not in self.brains:
            logger.warning("Ignoring triplet for unknown brain '%s'", brain_type)
            return

        subj = subject.strip().lower()[:80]
        obj = object_.strip().lower()[:80]
        rel = relation.strip().upper().replace(" ", "_") or "RELATED_TO"

        if not subj or not obj:
            return

        graph = self.brains[brain_type]
        lock = self._locks[brain_type]
        is_new_edge = False

        with lock:
            graph.add_node(subj, label=subj)
            graph.add_node(obj, label=obj)
            if graph.has_edge(subj, obj):
                existing_rel = graph.edges[subj, obj].get("relation", "")
                if rel not in existing_rel:
                    graph.edges[subj, obj]["relation"] = (
                        f"{existing_rel},{rel}" if existing_rel else rel
                    )
                graph.edges[subj, obj]["weight"] = (
                    graph.edges[subj, obj].get("weight", 1) + 1
                )
            else:
                graph.add_edge(subj, obj, relation=rel, weight=1)
                is_new_edge = True

        # Record timeline entry (outside graph lock, under timeline lock)
        with self._timeline_lock:
            # Produce a JS-friendly ISO timestamp with 'Z' suffix (no +00:00 offset)
            _ts_iso = datetime.now(timezone.utc).isoformat()
            if _ts_iso.endswith("+00:00"):
                _ts_iso = _ts_iso[:-6] + "Z"
            entry: TimelineEntry = {
                "timestamp": _ts_iso,
                "brain_type": brain_type,
                "subject": subj,
                "relation": rel,
                "object_": obj,
                "is_new_edge": is_new_edge,
            }
            self._timeline.append(entry)
            # Trim oldest entries if exceeding max
            if len(self._timeline) > self._max_timeline_entries:
                self._timeline = self._timeline[-self._max_timeline_entries:]

    # ── Visualisation / Serialisation ─────────────────────────────────────

    def visualize(self, brain_type: str) -> dict[str, Any]:
        """Return the brain's graph in node-link format for the frontend.

        The response has the shape:
        ``{"nodes": [...], "links": [...], "_meta": {...}}``

        This matches the schema that ``react-force-graph-2d`` consumes.

        Args:
            brain_type: Which brain to visualise (e.g. ``"ai_chats"``).

        Raises:
            KeyError: If *brain_type* is not registered.
        """
        graph = self.get_brain(brain_type)
        lock = self._locks[brain_type]

        with lock:
            data: dict[str, Any] = json_graph.node_link_data(graph, edges="links")

        data.setdefault("nodes", [])
        data.setdefault("links", [])

        # Attach brain metadata
        meta = BRAIN_REGISTRY.get(brain_type, {})
        data["_meta"] = {
            "brain_type": brain_type,
            "label": meta.get("label", brain_type),
            "color": meta.get("color", "#818cf8"),
            "neon_glow": meta.get("neon_glow", "rgba(129,140,248,0.5)"),
            "nodes": len(data["nodes"]),
            "edges": len(data["links"]),
        }

        return data

    # ── Persistence ───────────────────────────────────────────────────────

    def set_data_dir(self, directory: str) -> None:
        """Set the base data directory for saving/loading brain files."""
        self._data_dir = directory

    def save_all(self, directory: str | None = None) -> dict[str, int]:
        """Save all brains to individual JSON files.

        Args:
            directory: Target directory. Falls back to ``_data_dir`` if set,
                       otherwise ``"data/brains"`` relative to the project.

        Returns:
            Dict mapping brain type → number of nodes saved.
        """
        base = directory or self._data_dir or "data/brains"
        path = Path(base)
        path.mkdir(parents=True, exist_ok=True)

        results: dict[str, int] = {}
        for brain_type, graph in self.brains.items():
            lock = self._locks[brain_type]
            with lock:
                data = json_graph.node_link_data(graph, edges="links")
                data["_meta"] = {
                    "brain_type": brain_type,
                    "version": 1,
                    "nodes": graph.number_of_nodes(),
                    "edges": graph.number_of_edges(),
                }
            file_path = path / f"{brain_type}.json"
            file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            results[brain_type] = graph.number_of_nodes()
            logger.debug("Brain '%s' saved to %s", brain_type, file_path)

        total = sum(results.values())
        logger.info(
            "Saved %d brains (%d total nodes) to %s",
            len(results), total, path,
        )

        # Also persist the timeline alongside brain data
        self.save_timeline(directory=base)

        return results

    def load_all(self, directory: str | None = None) -> dict[str, bool]:
        """Load all brains from individual JSON files.

        Args:
            directory: Source directory. Falls back to ``_data_dir`` if set,
                       otherwise ``"data/brains"``.

        Returns:
            Dict mapping brain type → whether it was loaded successfully.
        """
        base = directory or self._data_dir or "data/brains"
        path = Path(base)
        if not path.exists():
            logger.info("No brain data directory found at %s — starting fresh", path)
            return {}

        results: dict[str, bool] = {}
        for brain_type in self.brains:
            file_path = path / f"{brain_type}.json"
            if not file_path.exists():
                results[brain_type] = False
                continue

            try:
                raw = file_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                loaded_graph: nx.Graph = json_graph.node_link_graph(data, edges="links")
                self.brains[brain_type] = loaded_graph
                results[brain_type] = True
                logger.debug(
                    "Brain '%s' loaded from %s (%d nodes, %d edges)",
                    brain_type, file_path,
                    loaded_graph.number_of_nodes(),
                    loaded_graph.number_of_edges(),
                )
            except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
                logger.warning(
                    "Failed to load brain '%s' from %s: %s",
                    brain_type, file_path, exc,
                )
                results[brain_type] = False

        loaded = sum(1 for v in results.values() if v)
        logger.info("Loaded %d/%d brains from %s", loaded, len(results), path)

        # Also restore timeline alongside brain data
        self.load_timeline(directory=base)

        return results

    def save_brain(self, brain_type: str, directory: str | None = None) -> bool:
        """Save a single brain to disk.

        Args:
            brain_type: Which brain to save.
            directory: Target directory (default: ``_data_dir``).

        Returns:
            True if saved successfully.
        """
        if brain_type not in self.brains:
            return False

        base = directory or self._data_dir or "data/brains"
        path = Path(base)
        path.mkdir(parents=True, exist_ok=True)

        graph = self.brains[brain_type]
        lock = self._locks[brain_type]
        with lock:
            data = json_graph.node_link_data(graph, edges="links")
            data["_meta"] = {
                "brain_type": brain_type,
                "version": 1,
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
            }

        file_path = path / f"{brain_type}.json"
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Brain '%s' saved to %s", brain_type, file_path)
        return True

    def load_brain(self, brain_type: str, directory: str | None = None) -> bool:
        """Load a single brain from disk.

        Args:
            brain_type: Which brain to load.
            directory: Source directory (default: ``_data_dir``).

        Returns:
            True if loaded successfully.
        """
        if brain_type not in self.brains:
            return False

        base = directory or self._data_dir or "data/brains"
        file_path = Path(base) / f"{brain_type}.json"
        if not file_path.exists():
            return False

        try:
            raw = file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            loaded_graph = json_graph.node_link_graph(data, edges="links")
            self.brains[brain_type] = loaded_graph
            logger.info(
                "Brain '%s' loaded from %s (%d nodes, %d edges)",
                brain_type, file_path,
                loaded_graph.number_of_nodes(),
                loaded_graph.number_of_edges(),
            )
            return True
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
            logger.warning(
                "Failed to load brain '%s' from %s: %s",
                brain_type, file_path, exc,
            )
            return False

    # ── Timeline Persistence ───────────────────────────────────────────

    def save_timeline(self, directory: str | None = None) -> bool:
        """Save the timeline event log to a JSON file alongside brain data.

        Writes to ``{directory}/_timeline.json``.  This file is loaded
        back by ``load_all()`` so history survives app restarts.

        Args:
            directory: Target directory. Falls back to ``_data_dir`` if set,
                       otherwise ``"data/brains"``.

        Returns:
            True if saved successfully.
        """
        base = directory or self._data_dir or "data/brains"
        path = Path(base)
        path.mkdir(parents=True, exist_ok=True)

        with self._timeline_lock:
            data = list(self._timeline)
            meta = {
                "_meta": {
                    "version": 1,
                    "count": len(data),
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                }
            }
            payload = json.dumps(meta | {"entries": data}, indent=2, default=str)

        file_path = path / "_timeline.json"
        file_path.write_text(payload, encoding="utf-8")
        logger.info("Timeline saved to %s (%d entries)", file_path, len(data))
        return True

    def load_timeline(self, directory: str | None = None) -> bool:
        """Load the timeline event log from a JSON file.

        Reads ``{directory}/_timeline.json`` and replaces the in-memory
        timeline (does not append).  If the file doesn't exist or is
        corrupt, the timeline remains empty (no crash).

        Args:
            directory: Source directory. Falls back to ``_data_dir`` if set,
                       otherwise ``"data/brains"``.

        Returns:
            True if loaded successfully (missing file = True).
        """
        base = directory or self._data_dir or "data/brains"
        file_path = Path(base) / "_timeline.json"

        if not file_path.exists():
            logger.debug("No timeline file found at %s — starting fresh", file_path)
            return True  # Not an error; just means no history yet

        try:
            raw = file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            entries = data.get("entries", [])

            if not isinstance(entries, list):
                logger.warning(
                    "Timeline file %s has invalid format (entries is not a list)",
                    file_path,
                )
                return False

            with self._timeline_lock:
                self._timeline = entries[-self._max_timeline_entries:]

            logger.info(
                "Timeline loaded from %s (%d entries)",
                file_path, len(entries),
            )
            return True

        except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
            logger.warning(
                "Failed to load timeline from %s: %s",
                file_path, exc,
            )
            return False

    # ── Timeline / History ──────────────────────────────────────────────

    def get_timeline(
        self,
        brain_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TimelineEntry]:
        """Return the timeline event log, newest first.

        Args:
            brain_type: If set, filter to this brain only.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip (for pagination).

        Returns:
            List of ``TimelineEntry`` dicts, newest first.
        """
        with self._timeline_lock:
            entries = list(reversed(self._timeline))

        if brain_type:
            entries = [e for e in entries if e.get("brain_type") == brain_type]

        return entries[offset:offset + limit]

    def get_timeline_summary(self) -> list[dict[str, Any]]:
        """Return per-brain activity summary (counts per brain).

        Returns:
            List of dicts with keys: ``brain_type``, ``label``, ``color``,
            ``total_events``, ``latest_timestamp``, ``new_edges``.
        """
        with self._timeline_lock:
            entries = list(self._timeline)

        summary: dict[str, dict[str, Any]] = {}
        for e in entries:
            bt = e["brain_type"]
            if bt not in summary:
                meta = BRAIN_REGISTRY.get(bt, {})
                summary[bt] = {
                    "brain_type": bt,
                    "label": meta.get("label", bt),
                    "color": meta.get("color", "#818cf8"),
                    "total_events": 0,
                    "new_edges": 0,
                    "latest_timestamp": e["timestamp"],
                }
            s = summary[bt]
            s["total_events"] += 1
            if e.get("is_new_edge"):
                s["new_edges"] += 1
            if e["timestamp"] > s["latest_timestamp"]:
                s["latest_timestamp"] = e["timestamp"]

        # Sort by latest activity (most recent first)
        result = sorted(
            summary.values(),
            key=lambda x: x["latest_timestamp"],
            reverse=True,
        )
        return result

    def clear_timeline(self, brain_type: Optional[str] = None) -> int:
        """Clear the timeline event log.

        Args:
            brain_type: If set, clear only entries for this brain.

        Returns:
            Number of entries removed.
        """
        with self._timeline_lock:
            if brain_type is None:
                removed = len(self._timeline)
                self._timeline.clear()
            else:
                before = len(self._timeline)
                self._timeline = [
                    e for e in self._timeline
                    if e.get("brain_type") != brain_type
                ]
                removed = before - len(self._timeline)
        return removed

    # ── Utility ──────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Clear all brains (removes all nodes and edges)."""
        for brain_type, graph in self.brains.items():
            lock = self._locks[brain_type]
            with lock:
                graph.clear()
        logger.info("All brains cleared")

    def clear_brain(self, brain_type: str) -> bool:
        """Clear a single brain.

        Returns:
            True if the brain was cleared.
        """
        if brain_type not in self.brains:
            return False
        lock = self._locks[brain_type]
        with lock:
            self.brains[brain_type].clear()
        logger.info("Brain '%s' cleared", brain_type)
        return True

    def get_statistics(self, brain_type: str) -> dict[str, Any]:
        """Return aggregate statistics for a specific brain.

        Args:
            brain_type: Which brain to inspect.

        Raises:
            KeyError: If *brain_type* is not registered.
        """
        graph = self.get_brain(brain_type)
        lock = self._locks[brain_type]

        with lock:
            n = graph.number_of_nodes()
            e = graph.number_of_edges()
            if n == 0:
                stats: dict[str, Any] = {
                    "brain_type": brain_type,
                    "nodes": 0,
                    "edges": 0,
                    "density": 0.0,
                    "connected_components": 0,
                    "top_entities": [],
                }
                return stats

            density = nx.density(graph)
            components = nx.number_connected_components(graph)
            cent = nx.degree_centrality(graph)
            top = sorted(cent.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "brain_type": brain_type,
            "nodes": n,
            "edges": e,
            "density": round(density, 6),
            "connected_components": components,
            "top_entities": [
                {"entity": e, "centrality": round(c, 6)} for e, c in top
            ],
        }


# ─── Module-level singleton (matching project convention) ────────────────────

multi_brain_manager: MultiBrainManager = MultiBrainManager.get_instance()
