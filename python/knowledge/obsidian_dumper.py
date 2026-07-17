"""
BARQ Obsidian Dumper — writes agent findings, evaluations, and research reports
as YAML-frontmatter .md files directly into a designated Obsidian vault.

This enables zero-plugin Obsidian sync: every agent output, job evaluation,
research report, and graph brain snapshot is automatically available as a
tagged, formatted note in the user's Obsidian vault.

Vault path is configured via settings (key: "obsidian_vault_path").
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class ObsidianDumper:
    """Writes structured markdown files into an Obsidian vault."""

    def __init__(self, vault_path: Optional[str] = None):
        self._vault_path: Optional[str] = vault_path

    # ── Configuration ─────────────────────────────────────────────

    @property
    def vault_path(self) -> Optional[str]:
        return self._vault_path

    @vault_path.setter
    def vault_path(self, path: str) -> None:
        self._vault_path = path

    def is_configured(self) -> bool:
        """Check if a vault path is set and writable."""
        if not self._vault_path:
            return False
        p = Path(self._vault_path)
        return p.exists() and p.is_dir()

    def ensure_subdir(self, subdir: str) -> Optional[Path]:
        """Ensure a subdirectory exists inside the vault.

        Args:
            subdir: Subdirectory name (e.g. "research", "jobs", "memory").

        Returns:
            Path to the subdirectory, or None if vault is not configured.
        """
        if not self._vault_path:
            return None
        path = Path(self._vault_path) / "BARQ" / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ── Markdown Builder ──────────────────────────────────────────

    @staticmethod
    def build_frontmatter(tags: list[str], metadata: dict[str, Any]) -> str:
        """Build YAML frontmatter string.

        Args:
            tags: List of Obsidian tags.
            metadata: Dict of key-value pairs for frontmatter.

        Returns:
            YAML frontmatter block string.
        """
        lines = ["---"]
        if tags:
            lines.append(f"tags: [{', '.join(tags)}]")
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                lines.append(f"{key}: {value}")
            elif isinstance(value, str):
                # Escape double quotes in value
                escaped = value.replace('"', '\\"')
                lines.append(f'{key}: "{escaped}"')
            elif isinstance(value, (list, dict)):
                lines.append(f"{key}: {json.dumps(value)}")
            else:
                lines.append(f'{key}: "{str(value)}"')
        lines.append("---")
        return "\n".join(lines)

    @staticmethod
    def build_note(
        title: str,
        body: str,
        tags: Optional[list[str]] = None,
        **metadata: Any,
    ) -> str:
        """Build a complete Obsidian note with frontmatter.

        Args:
            title: Note title (used in frontmatter and as H1).
            body: Markdown body content.
            tags: Optional list of tags.
            **metadata: Additional frontmatter key-value pairs.

        Returns:
            Complete markdown string ready to write to file.
        """
        fm = ObsidianDumper.build_frontmatter(tags or [], {
            "title": title,
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            **metadata,
        })
        return f"{fm}\n\n# {title}\n\n{body}\n"

    # ── Dump Methods ──────────────────────────────────────────────

    def dump_research_report(
        self,
        topic: str,
        report: str,
        depth: str = "standard",
        sources_count: int = 0,
        facts_count: int = 0,
    ) -> Optional[str]:
        """Dump a deep research report as an Obsidian note.

        Args:
            topic: Research topic.
            report: Full markdown report body.
            depth: Research depth level.
            sources_count: Number of sources.
            facts_count: Number of gathered facts.

        Returns:
            File path of the written note, or None if vault not configured.
        """
        subdir = self.ensure_subdir("research")
        if not subdir:
            return None

        slug = topic.strip().lower().replace(" ", "_").replace("/", "_")[:40]
        safe_slug = "".join(c for c in slug if c.isalnum() or c in "_-")
        filename = f"{datetime.now().strftime('%Y%m%d')}_{safe_slug}.md"
        filepath = subdir / filename

        note = self.build_note(
            title=f"Research: {topic}",
            body=report,
            tags=["deep-research", depth, "barq"],
            depth=depth,
            sources=sources_count,
            facts=facts_count,
        )

        filepath.write_text(note, encoding="utf-8")
        print(f"[Obsidian] Dumped research report: {filepath}")
        return str(filepath)

    def dump_job_evaluation(
        self,
        job_title: str,
        company: str,
        match_score: float,
        reasoning: str,
        pros: Optional[list[str]] = None,
        cons: Optional[list[str]] = None,
        job_url: str = "",
    ) -> Optional[str]:
        """Dump a job evaluation as an Obsidian note.

        Args:
            job_title: Job title.
            company: Company name.
            match_score: Match score (0-100).
            reasoning: Evaluation reasoning text.
            pros: List of pros/matching skills.
            cons: List of cons/missing skills.
            job_url: URL to the job listing.

        Returns:
            File path or None.
        """
        subdir = self.ensure_subdir("jobs")
        if not subdir:
            return None

        safe_name = f"{company}_{job_title}".replace(" ", "_").replace("/", "_")[:50]
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
        filename = f"{datetime.now().strftime('%Y%m%d')}_{safe_name}.md"
        filepath = subdir / filename

        body_parts = []
        body_parts.append(f"**Match Score:** {match_score:.0f}%")
        if job_url:
            body_parts.append(f"**URL:** [{job_url}]({job_url})")
        body_parts.append(f"\n## Reasoning\n{reasoning}")
        if pros:
            body_parts.append("\n## ✅ Matching Skills\n" + "\n".join(f"- {p}" for p in pros))
        if cons:
            body_parts.append("\n## ❌ Gaps\n" + "\n".join(f"- {c}" for c in cons))

        note = self.build_note(
            title=f"Job Evaluation: {job_title} @ {company}",
            body="\n\n".join(body_parts),
            tags=["job-evaluation", "barq"],
            company=company,
            match_score=round(match_score, 1),
        )

        filepath.write_text(note, encoding="utf-8")
        print(f"[Obsidian] Dumped job evaluation: {filepath}")
        return str(filepath)

    def dump_agent_finding(
        self,
        title: str,
        content: str,
        agent_name: str = "unknown",
        category: str = "general",
        tags: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Dump an agent finding or memory as an Obsidian note.

        Args:
            title: Finding title.
            content: Markdown content.
            agent_name: Name of the agent that produced this.
            category: Category for subdirectory.
            tags: Additional tags.

        Returns:
            File path or None.
        """
        subdir = self.ensure_subdir(category)
        if not subdir:
            return None

        slug = title.strip().lower().replace(" ", "_").replace("/", "_")[:40]
        safe_slug = "".join(c for c in slug if c.isalnum() or c in "_-")
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe_slug}.md"
        filepath = subdir / filename

        all_tags = ["barq", f"agent-{agent_name}"] + (tags or [])
        note = self.build_note(
            title=title,
            body=content,
            tags=all_tags,
            agent=agent_name,
            category=category,
        )

        filepath.write_text(note, encoding="utf-8")
        print(f"[Obsidian] Dumped agent finding: {filepath}")
        return str(filepath)

    def dump_graph_snapshot(
        self,
        nodes_count: int,
        edges_count: int,
        top_entities: list[dict],
        summary: str = "",
    ) -> Optional[str]:
        """Dump a knowledge graph snapshot as an Obsidian note.

        Args:
            nodes_count: Number of nodes in the graph.
            edges_count: Number of edges.
            top_entities: List of top entities with centrality.
            summary: Optional summary text.

        Returns:
            File path or None.
        """
        subdir = self.ensure_subdir("graph")
        if not subdir:
            return None

        filename = f"graph_snapshot_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        filepath = subdir / filename

        body = f"**Nodes:** {nodes_count}  \n**Edges:** {edges_count}  \n\n"
        if summary:
            body += f"{summary}\n\n"
        if top_entities:
            body += "## Top Entities\n\n"
            body += "| Entity | Centrality |\n|--------|------------|\n"
            for e in top_entities:
                body += f"| {e.get('entity', '?')} | {e.get('centrality', 0)} |\n"

        note = self.build_note(
            title=f"Graph Snapshot ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            body=body,
            tags=["graph-brain", "barq"],
            nodes=nodes_count,
            edges=edges_count,
        )

        filepath.write_text(note, encoding="utf-8")
        print(f"[Obsidian] Dumped graph snapshot: {filepath}")
        return str(filepath)


# ─── Module-level singleton ─────────────────────────────────────────────

_obsidian_dumper: Optional[ObsidianDumper] = None


def get_obsidian_dumper() -> ObsidianDumper:
    """Get or create the global ObsidianDumper singleton."""
    global _obsidian_dumper
    if _obsidian_dumper is None:
        _obsidian_dumper = ObsidianDumper()
    return _obsidian_dumper
