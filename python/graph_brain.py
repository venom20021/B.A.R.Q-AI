"""
BARQ Graph Brain — Local Knowledge Graph for Entity Relationship Extraction.

Uses NetworkX for in-memory graph operations and a local Ollama LLM
to extract subject-relation-object triplets from unstructured text.
Thread-safe singleton so the same brain instance is shared across all
FastAPI endpoints and background tasks.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

import httpx
import networkx as nx
from networkx.readwrite import json_graph

from config import get_settings

logger = logging.getLogger("barq.graph_brain")

# ─── Default Ollama extraction prompt ────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a knowledge graph extraction engine.
Your job is to read the text below and output a JSON array of triplets in the
format [["Subject", "RELATIONSHIP", "Object"], ...].

Rules:
- Each triplet must have exactly 3 elements: Subject, RELATIONSHIP, Object.
- RELATIONSHIP should be UPPERCASE_SNAKE_CASE (e.g. WORKS_AT, HAS_SKILL, LOCATED_IN).
- Keep entity names concise: 1-3 words, lowercased, stripped of punctuation.
- If the text does not contain any clear relationships, output an empty array [].
- NEVER add explanations before or after the JSON — output only the JSON array.

Example:
Input: "Python is used for data science at Google"
Output: [["python", "USED_FOR", "data science"], ["python", "USED_AT", "google"]]

Now extract triplets from the following text:"""


class BARQGraphBrain:
    """Thread-safe singleton knowledge graph for entity relationship storage.

    Usage:
        >>> brain = BARQGraphBrain.get_instance()
        >>> brain.add_knowledge("Python is used for data science at Google")
        >>> brain.get_top_entities(3)
    """

    _instance: Optional[BARQGraphBrain] = None
    _class_lock = threading.Lock()

    # ── Singleton ─────────────────────────────────────────────────────────

    def __new__(cls) -> BARQGraphBrain:
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
            settings = get_settings()
            self.ollama_host: str = settings.ollama_host
            self.ollama_model: str = settings.ollama_model
            self.graph: nx.Graph = nx.Graph()
            self._graph_lock = threading.Lock()
            # Shared HTTP client with connection pooling
            self._http_client = httpx.Client(
                timeout=httpx.Timeout(60.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
            self._initialized = True
            logger.info(
                "BARQGraphBrain initialised (model=%s, host=%s)",
                self.ollama_model,
                self.ollama_host,
            )

    @classmethod
    def get_instance(cls) -> BARQGraphBrain:
        """Return or create the singleton graph brain."""
        if cls._instance is None:
            cls()
        assert cls._instance is not None
        return cls._instance

    # ── LLM Extraction ────────────────────────────────────────────────────

    def extract_triplets(self, text_content: str) -> list[tuple[str, str, str]]:
        """Query the local Ollama instance for relation triplets.

        Args:
            text_content: Raw unstructured text (job description, social post, etc.).

        Returns:
            List of (subject, relation, object) tuples. Empty list on failure.
        """
        if not text_content or not text_content.strip():
            return []

        payload = {
            "model": self.ollama_model,
            "system": EXTRACTION_SYSTEM_PROMPT,
            "prompt": text_content.strip()[:4000],  # cap input length
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "top_p": 0.9},
        }

        try:
            resp = self._http_client.post(
                f"{self.ollama_host}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "").strip()
        except httpx.HTTPStatusError as exc:
            logger.warning("Ollama returned HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return []
        except httpx.RequestError as exc:
            logger.warning("Ollama request failed: %s", exc)
            return []
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Ollama response parse error: %s", exc)
            return []

        # Parse the JSON array from Ollama's response
        triplets: list[tuple[str, str, str]] = []
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                logger.warning("Ollama response is not a JSON array: %s …", raw[:200])
                return []

            for item in parsed:
                if not isinstance(item, list) or len(item) != 3:
                    continue
                subj, rel, obj = item
                subj = self._normalize_entity(str(subj))
                obj = self._normalize_entity(str(obj))
                rel = str(rel).strip().upper().replace(" ", "_") or "RELATED_TO"
                if subj and obj:
                    triplets.append((subj, rel, obj))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to decode triplet JSON: %s\nRaw: %s …", exc, raw[:200])

        logger.debug("Extracted %d triplets from %d chars", len(triplets), len(text_content))
        return triplets

    # ── Normalisation ─────────────────────────────────────────────────────

    @staticmethod
    def _normalize_entity(name: str) -> str:
        """Normalise a node label to prevent redundant variants.

        - Lowercases
        - Strips leading/trailing whitespace and punctuation
        - Collapses internal whitespace
        - Truncates to 80 chars
        """
        name = name.strip().lower()
        # Strip leading/trailing punctuation but keep internal hyphens / dots
        name = name.strip(".,;:!?\"'“”‘’()[]{}<>")
        # Collapse multiple spaces
        parts = name.split()
        name = " ".join(parts)
        return name[:80]

    # ── Mutation / Ingestion ──────────────────────────────────────────────

    def add_knowledge(self, text: str) -> int:
        """Extract triplets from *text* and add them to the graph.

        Args:
            text: Unstructured text to mine for relationships.

        Returns:
            Number of triplets successfully added.
        """
        triplets = self.extract_triplets(text)

        if not triplets:
            return 0

        with self._graph_lock:
            for subj, rel, obj in triplets:
                # Add nodes (idempotent if already present)
                self.graph.add_node(subj, label=subj)
                self.graph.add_node(obj, label=obj)
                # Add edge with relationship type as an attribute
                if self.graph.has_edge(subj, obj):
                    existing_rel = self.graph.edges[subj, obj].get("relation", "")
                    if rel not in existing_rel:
                        self.graph.edges[subj, obj]["relation"] = (
                            f"{existing_rel},{rel}" if existing_rel else rel
                        )
                    self.graph.edges[subj, obj]["weight"] = (
                        self.graph.edges[subj, obj].get("weight", 1) + 1
                    )
                else:
                    self.graph.add_edge(subj, obj, relation=rel, weight=1)

        logger.info("Added %d triplets (graph now has %d nodes, %d edges)", len(triplets),
                     self.graph.number_of_nodes(), self.graph.number_of_edges())
        return len(triplets)

    def add_triplet(self, subject: str, relation: str, object_: str) -> None:
        """Directly add a single triplet without LLM extraction.

        Useful for programmatic inserts or testing.
        """
        subj = self._normalize_entity(subject)
        obj = self._normalize_entity(object_)
        rel = relation.strip().upper().replace(" ", "_") or "RELATED_TO"
        if not subj or not obj:
            return
        with self._graph_lock:
            self.graph.add_node(subj, label=subj)
            self.graph.add_node(obj, label=obj)
            if self.graph.has_edge(subj, obj):
                existing_rel = self.graph.edges[subj, obj].get("relation", "")
                if rel not in existing_rel:
                    self.graph.edges[subj, obj]["relation"] = (
                        f"{existing_rel},{rel}" if existing_rel else rel
                    )
                self.graph.edges[subj, obj]["weight"] = (
                    self.graph.edges[subj, obj].get("weight", 1) + 1
                )
            else:
                self.graph.add_edge(subj, obj, relation=rel, weight=1)

    def clear(self) -> None:
        """Remove all nodes and edges from the graph."""
        with self._graph_lock:
            self.graph.clear()
        logger.info("Graph cleared")

    # ── Persistence ───────────────────────────────────────────────────────

    def save_to_disk(self, file_path: str) -> None:
        """Serialize the graph to a JSON file using NetworkX node-link format.

        Args:
            file_path: Destination path (e.g. ``data/graph.json``).
        """
        with self._graph_lock:
            data: dict[str, Any] = json_graph.node_link_data(self.graph)
            # Add metadata
            data["_meta"] = {
                "version": 2,
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
            }

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Graph saved to %s (%d nodes, %d edges)",
                     file_path, data["_meta"]["nodes"], data["_meta"]["edges"])

    def load_from_disk(self, file_path: str) -> bool:
        """Rebuild the graph from a JSON file previously written by ``save_to_disk``.

        Args:
            file_path: Source path.

        Returns:
            True if the graph was successfully loaded, False otherwise.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("Graph file not found: %s", file_path)
            return False

        try:
            raw = path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read graph file %s: %s", file_path, exc)
            return False

        try:
            loaded: nx.Graph = json_graph.node_link_graph(data)
        except (KeyError, TypeError) as exc:
            logger.error("Invalid graph data in %s: %s", file_path, exc)
            return False

        with self._graph_lock:
            self.graph = loaded

        n = self.graph.number_of_nodes()
        e = self.graph.number_of_edges()
        logger.info("Graph loaded from %s (%d nodes, %d edges)", file_path, n, e)
        return True

    # ── Analytics & Traversal ──────────────────────────────────────────────

    def get_top_entities(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return the most central (best-connected) entities using degree centrality.

        Args:
            limit: Number of top entities to return.

        Returns:
            List of ``{"entity": str, "centrality": float}`` dicts sorted descending.
        """
        with self._graph_lock:
            if self.graph.number_of_nodes() == 0:
                return []
            cent = nx.degree_centrality(self.graph)
            # Sort by centrality descending
            ranked = sorted(cent.items(), key=lambda x: x[1], reverse=True)

        return [
            {"entity": entity, "centrality": round(score, 6)}
            for entity, score in ranked[:limit]
        ]

    def find_relationship_path(
        self, source: str, target: str
    ) -> dict[str, Any]:
        """Find the shortest path connecting two entities.

        Args:
            source: Starting entity name.
            target: Target entity name.

        Returns:
            A dict with keys:
            - ``"found"``: bool
            - ``"path"``: list of node names (or empty list)
            - ``"edges"``: list of {source, target, relation} dicts
            - ``"length"``: number of edges (0 if not found)
        """
        src = self._normalize_entity(source)
        tgt = self._normalize_entity(target)

        with self._graph_lock:
            if not self.graph.has_node(src):
                return {"found": False, "path": [], "edges": [], "length": 0,
                        "error": f"Source '{source}' not in graph"}
            if not self.graph.has_node(tgt):
                return {"found": False, "path": [], "edges": [], "length": 0,
                        "error": f"Target '{target}' not in graph"}

            try:
                path_nodes: list[str] = nx.shortest_path(self.graph, source=src, target=tgt)
            except nx.NetworkXNoPath:
                return {"found": False, "path": [], "edges": [], "length": 0,
                        "error": "No path exists between the two entities"}

            # Build edge list from the path
            edges = []
            for i in range(len(path_nodes) - 1):
                u, v = path_nodes[i], path_nodes[i + 1]
                edge_data = dict(self.graph.edges[u, v])
                edges.append({
                    "source": u,
                    "target": v,
                    "relation": edge_data.get("relation", "RELATED_TO"),
                    "weight": edge_data.get("weight", 1),
                })

        return {
            "found": True,
            "path": path_nodes,
            "edges": edges,
            "length": len(path_nodes) - 1,
        }

    def get_neighbours(self, entity: str, depth: int = 1) -> list[dict[str, Any]]:
        """Get all entities directly connected to *entity*.

        Args:
            entity: The entity name to expand from.
            depth: How many hops to traverse (1 = immediate neighbours only).

        Returns:
            List of {entity, relation, weight, distance} dicts.
        """
        name = self._normalize_entity(entity)
        with self._graph_lock:
            if not self.graph.has_node(name):
                return []

            if depth == 1:
                neighbours = list(self.graph.neighbors(name))
                results = []
                for nb in neighbours:
                    edge = self.graph.edges[name, nb]
                    results.append({
                        "entity": nb,
                        "relation": edge.get("relation", "RELATED_TO"),
                        "weight": edge.get("weight", 1),
                        "distance": 1,
                    })
                return results

            # Multi-hop BFS
            from collections import deque

            visited: set[str] = set()
            queue: deque[tuple[str, int]] = deque()
            queue.append((name, 0))
            visited.add(name)
            results: list[dict[str, Any]] = []

            while queue:
                current, dist = queue.popleft()
                if 0 < dist <= depth:
                    results.append({"entity": current, "distance": dist})

                if dist >= depth:
                    continue

                for nb in self.graph.neighbors(current):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append((nb, dist + 1))

            return results

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate graph statistics."""
        with self._graph_lock:
            n = self.graph.number_of_nodes()
            e = self.graph.number_of_edges()

            if n == 0:
                return {"nodes": 0, "edges": 0, "density": 0.0, "connected_components": 0}

            density = nx.density(self.graph)
            components = nx.number_connected_components(self.graph)
            # Top 3 most central entities
            cent = nx.degree_centrality(self.graph)
            top = sorted(cent.items(), key=lambda x: x[1], reverse=True)[:3]

        return {
            "nodes": n,
            "edges": e,
            "density": round(density, 6),
            "connected_components": components,
            "top_entities": [{"entity": e, "centrality": round(c, 6)} for e, c in top],
        }


# ── Module-level singleton (matching project convention) ──────────────────────

graph_brain: BARQGraphBrain = BARQGraphBrain.get_instance()
