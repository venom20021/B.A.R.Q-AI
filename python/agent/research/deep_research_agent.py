"""
BARQ Deep Research Agent — multi-agent iterative research loop.

Architecture (inspired by ai_deep_research_agent pattern):

  1. Gatherer Phase:   For each depth level, search web → extract → find gaps → refine query → re-search
  2. Elaborator Phase: Take gathered facts, add depth, case studies, expert context via LLM
  3. Editor Phase:     Polish, structure, and format the final report

Each phase produces typed progress cards that the frontend renders
as a live-updating research workspace.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from utils.ollama_client import OllamaClient

# ─── Depth Levels ─────────────────────────────────────────────────────

class ResearchDepth(str, Enum):
    BASIC = "basic"       # 1 round, 3 queries
    STANDARD = "standard" # 2 rounds, 6 queries
    DEEP = "deep"         # 3 rounds, 9 queries


DEPTH_CONFIG = {
    ResearchDepth.BASIC: {"rounds": 1, "queries_per_round": 3, "max_sources": 5},
    ResearchDepth.STANDARD: {"rounds": 2, "queries_per_round": 4, "max_sources": 10},
    ResearchDepth.DEEP: {"rounds": 3, "queries_per_round": 5, "max_sources": 15},
}


# ─── Research Phase Enum ──────────────────────────────────────────────

class ResearchPhase(str, Enum):
    GATHERING = "gathering"
    ELABORATING = "elaborating"
    EDITING = "editing"
    COMPLETE = "complete"
    FAILED = "failed"


# ─── Card Types ───────────────────────────────────────────────────────

class ResearchCard:
    """A single progress card shown in the research workspace."""

    def __init__(
        self,
        phase: str,
        title: str,
        content: str,
        status: str = "pending",  # pending, active, complete, error
        card_type: str = "info",  # info, search, quote, finding, gap, insight
        metadata: Optional[dict] = None,
    ):
        self.id = f"card_{uuid.uuid4().hex[:12]}"
        self.phase = phase
        self.title = title
        self.content = content
        self.status = status
        self.card_type = card_type
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phase": self.phase,
            "title": self.title,
            "content": self.content,
            "status": self.status,
            "card_type": self.card_type,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


# ─── Progress State ───────────────────────────────────────────────────

class ResearchProgress:
    """Tracks the progress of an active research session."""

    def __init__(self, topic: str, depth: ResearchDepth):
        self.topic = topic
        self.depth = depth
        self.phase = ResearchPhase.GATHERING
        self.round = 0
        self.total_rounds = DEPTH_CONFIG[depth]["rounds"]
        self.cards: list[ResearchCard] = []
        self.gathered_facts: list[str] = []
        self.search_queries: list[str] = []
        self.final_report: str = ""
        self.error: Optional[str] = None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None

    def add_card(self, card: ResearchCard) -> None:
        self.cards.append(card)

    def update_card_status(self, card_id: str, status: str) -> None:
        for card in self.cards:
            if card.id == card_id:
                card.status = status
                break

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "depth": self.depth.value,
            "phase": self.phase.value,
            "round": self.round,
            "total_rounds": self.total_rounds,
            "cards": [c.to_dict() for c in self.cards],
            "gathered_facts": self.gathered_facts,
            "search_queries": self.search_queries,
            "final_report": self.final_report,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ─── Research Result ──────────────────────────────────────────────────

class ResearchResult:
    """The final output of a research session."""

    def __init__(
        self,
        topic: str,
        report: str,
        sources: list[dict],
        facts: list[str],
        depth: ResearchDepth,
        cards: list[ResearchCard],
    ):
        self.topic = topic
        self.report = report
        self.sources = sources
        self.facts = facts
        self.depth = depth
        self.cards = cards

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "report": self.report,
            "sources": self.sources,
            "facts_count": len(self.facts),
            "depth": self.depth.value,
            "cards_count": len(self.cards),
        }


# ─── Web Search Helper ────────────────────────────────────────────────

async def _search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web via BARQ's existing web search endpoint."""
    import httpx

    from config import get_settings

    settings = get_settings()
    url = f"http://{settings.host}:{settings.port}/web/browse/search"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"query": query}, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                return results[:max_results]
    except Exception:
        pass
    return []


# ─── LLM Prompts ──────────────────────────────────────────────────────

GATHERER_SYSTEM_PROMPT = """You are BARQ's Research Gatherer Agent. Your job is to:
1. Analyze search results on a topic
2. Extract key facts, findings, and data points
3. Identify gaps in the information
4. Suggest follow-up search queries to fill those gaps

Be concise and factual. Output ONLY valid JSON.

Output format:
{
  "findings": ["key finding 1", "key finding 2", ...],
  "gaps": ["what's missing", ...],
  "follow_up_queries": ["refined query 1", ...],
  "key_sources": ["source title", ...]
}"""

ELABORATOR_SYSTEM_PROMPT = """You are BARQ's Research Elaborator Agent. Your job is to:
1. Take the gathered facts and findings from the research
2. Add expert context, explanations, and depth
3. Include relevant case studies or real-world examples
4. Connect related concepts and draw insights
5. Note contradictory findings or debates in the field

Think like a senior analyst adding depth to raw research.

Output format:
{
  "elaborations": [
    {"concept": "...", "depth_added": "...", "source_type": "expert_analysis|case_study|context"},
    ...
  ],
  "insights": ["key insight 1", ...],
  "contradictions": ["debate or conflicting view", ...]
}"""

EDITOR_SYSTEM_PROMPT = """You are BARQ's Research Editor Agent. Your job is to:
1. Take the gathered facts and elaborations
2. Structure them into a well-organized, readable report
3. Use markdown formatting with headers, bullet points, and emphasis
4. Include a TL;DR summary at the top
5. End with key takeaways and recommended next steps for further research

The report should be comprehensive but concise — about 500-1500 words depending on depth.

Use this structure:
- # <Title>
- **TL;DR:** 2-3 sentence summary
- ## Key Findings
- ## Deep Dive (elaborated insights)
- ## Sources & References
- ## Key Takeaways
- ## Next Steps for Further Research

Output the full markdown report as a single string."""  # noqa: E501


# ─── Deep Research Agent ──────────────────────────────────────────────

class DeepResearchAgent:
    """Multi-agent iterative research system.

    Usage:
        agent = DeepResearchAgent()
        result = await agent.research("Quantum computing breakthroughs 2025", depth="standard")
    """

    def __init__(self):
        self.llm = OllamaClient()
        self._active_progress: Optional[ResearchProgress] = None

    # ── Public API ──────────────────────────────────────────────────

    async def research(self, topic: str, depth: str = "standard") -> ResearchResult:
        """Run a full multi-agent research session on a topic.

        Args:
            topic: The research topic or question.
            depth: "basic" | "standard" | "deep"

        Returns:
            A ResearchResult with the final report and all progress cards.
        """
        depth_enum = ResearchDepth(depth) if depth in ResearchDepth._value2member_map_ else ResearchDepth.STANDARD
        progress = ResearchProgress(topic, depth_enum)
        self._active_progress = progress

        try:
            # Phase 1: Gather
            await self._phase_gather(progress)

            if not progress.gathered_facts:
                progress.phase = ResearchPhase.FAILED
                progress.error = "No facts gathered from web search"
                return self._build_result(progress)

            # Phase 2: Elaborate
            await self._phase_elaborate(progress)

            # Phase 3: Edit
            await self._phase_edit(progress)

            progress.phase = ResearchPhase.COMPLETE
            progress.completed_at = datetime.now(timezone.utc).isoformat()

            return self._build_result(progress)

        except Exception as e:
            progress.phase = ResearchPhase.FAILED
            progress.error = str(e)
            progress.add_card(ResearchCard(
                phase="error",
                title="Research Failed",
                content=f"Error: {e}",
                status="error",
                card_type="info",
            ))
            return self._build_result(progress)
        finally:
            self._active_progress = None

    def get_progress(self) -> Optional[dict]:
        """Get the current progress of an active research session."""
        if self._active_progress:
            return self._active_progress.to_dict()
        return None

    # ── Phase 1: Gather ─────────────────────────────────────────────

    async def _phase_gather(self, progress: ResearchProgress) -> None:
        """Iterative gathering: search → extract → refine → repeat."""
        progress.phase = ResearchPhase.GATHERING
        depth_cfg = DEPTH_CONFIG[progress.depth]
        all_findings: list[str] = []
        used_queries: set[str] = set()

        # Initial query from topic
        queries = [topic.strip().rstrip(".?!") for topic in progress.topic.split("\n") if topic.strip()]
        if not queries:
            queries = [progress.topic]

        for round_num in range(1, depth_cfg["rounds"] + 1):
            progress.round = round_num
            round_cards: list[ResearchCard] = []

            for i, query in enumerate(queries[:depth_cfg["queries_per_round"]]):
                if query in used_queries or len(query) < 5:
                    continue
                used_queries.add(query)
                progress.search_queries.append(query)

                # Search card
                search_card = ResearchCard(
                    phase="gathering",
                    title=f'Searching: "{query[:80]}{"…" if len(query) > 80 else ""}"',
                    content=f"Round {round_num}/{progress.total_rounds} — query {i + 1} of {len(queries[:depth_cfg['queries_per_round']])}",
                    status="active",
                    card_type="search",
                    metadata={"round": round_num, "query": query},
                )
                progress.add_card(search_card)
                round_cards.append(search_card)

                # Execute search
                results = await _search_web(query, max_results=depth_cfg["max_sources"])

                if not results:
                    progress.update_card_status(search_card.id, "error")
                    search_card.content = f'No results for "{query[:60]}" — may need a more specific query'
                    continue

                progress.update_card_status(search_card.id, "complete")
                search_card.content = f"Found {len(results)} sources"

                # Extracted findings card
                combined_results = "\n\n".join(
                    f"Title: {r.get('title', '')}\nSnippet: {r.get('snippet', '')}"
                    for r in results[:4]
                )
                extracted = await self._extract_findings(query, combined_results)
                if extracted:
                    findings = extracted.get("findings", [])
                    gaps = extracted.get("gaps", [])
                    follow_ups = extracted.get("follow_up_queries", [])

                    all_findings.extend(findings)
                    progress.gathered_facts.extend(findings)

                    # Findings card
                    if findings:
                        findings_card = ResearchCard(
                            phase="gathering",
                            title="Key Findings",
                            content="\n".join(f"• {f}" for f in findings[:5]),
                            status="complete",
                            card_type="finding",
                            metadata={"source_query": query, "count": len(findings)},
                        )
                        progress.add_card(findings_card)
                        round_cards.append(findings_card)

                    # Gaps card
                    if gaps:
                        gap_card = ResearchCard(
                            phase="gathering",
                            title="Identified Gaps",
                            content="\n".join(f"🔍 {g}" for g in gaps[:3]),
                            status="complete",
                            card_type="gap",
                            metadata={"source_query": query},
                        )
                        progress.add_card(gap_card)
                        round_cards.append(gap_card)

                    # Add follow-up queries for the next round
                    if round_num < progress.total_rounds:
                        for fq in follow_ups:
                            if fq not in used_queries and fq not in queries:
                                queries.append(fq)

            # Round summary card
            summary_card = ResearchCard(
                phase="gathering",
                title=f"Round {round_num} Complete",
                content=f"Executed {len(round_cards)} searches, gathered {len(all_findings)} findings",
                status="complete",
                card_type="info",
                metadata={"round": round_num, "findings_count": len(all_findings)},
            )
            progress.add_card(summary_card)

    # ── Phase 2: Elaborate ──────────────────────────────────────────

    async def _phase_elaborate(self, progress: ResearchProgress) -> None:
        """Add depth, context, and case studies to gathered facts."""
        progress.phase = ResearchPhase.ELABORATING

        elab_card = ResearchCard(
            phase="elaborating",
            title="Elaborating Research",
            content=f"Adding expert context to {len(progress.gathered_facts)} findings…",
            status="active",
            card_type="info",
        )
        progress.add_card(elab_card)

        # Limit facts to avoid prompt overflow
        facts_text = "\n".join(f"• {f}" for f in progress.gathered_facts[:15])
        queries_text = "\n".join(f"• {q}" for q in progress.search_queries[:10])

        prompt = f"""Research Topic: {progress.topic}

Gathered Facts:
{facts_text}

Search Queries Used:
{queries_text}

Analyze these findings and add depth. Include expert context, real-world examples, and identify any contradictions or debates."""

        try:
            messages = [
                {"role": "system", "content": ELABORATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = await self.llm.chat(messages)
            text = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()
            data = json.loads(text) if text.startswith("{") else {"elaborations": [], "insights": []}

            elaborations = data.get("elaborations", [])
            insights = data.get("insights", [])
            contradictions = data.get("contradictions", [])

            # Elaboration cards
            for elab in elaborations[:6]:
                elab_card = ResearchCard(
                    phase="elaborating",
                    title=elab.get("concept", "Insight"),
                    content=elab.get("depth_added", ""),
                    status="complete",
                    card_type="insight",
                    metadata={"source_type": elab.get("source_type", "context")},
                )
                progress.add_card(elab_card)

            # Contradictions card
            if contradictions:
                contra_card = ResearchCard(
                    phase="elaborating",
                    title="Conflicting Views / Debates",
                    content="\n".join(f"⚡ {c}" for c in contradictions[:3]),
                    status="complete",
                    card_type="insight",
                    metadata={"type": "contradictions"},
                )
                progress.add_card(contra_card)

            progress.update_card_status(elab_card.id, "complete")
            elab_card.content = f"Added depth to {len(elaborations)} concepts and identified {len(insights)} key insights"

        except Exception as e:
            progress.update_card_status(elab_card.id, "error")
            elab_card.content = f"Elaboration encountered an issue: {e}"

    # ── Phase 3: Edit ───────────────────────────────────────────────

    async def _phase_edit(self, progress: ResearchProgress) -> None:
        """Generate the final polished report."""
        progress.phase = ResearchPhase.EDITING

        edit_card = ResearchCard(
            phase="editing",
            title="Compiling Final Report",
            content="Structuring and formatting the research report…",
            status="active",
            card_type="info",
        )
        progress.add_card(edit_card)

        # Build comprehensive context
        facts_text = "\n".join(f"• {f}" for f in progress.gathered_facts[:20])
        cards_summary = "\n".join(
            f"[{c.phase}] {c.title}: {c.content[:100]}"
            for c in progress.cards
            if c.status == "complete" and c.phase in ("gathering", "elaborating")
        )

        prompt = f"""Research Topic: {progress.topic}
Depth Level: {progress.depth.value}

Research Cards Generated:
{cards_summary}

Gathered Facts:
{facts_text}

Create a comprehensive, well-structured research report. Include a TL;DR, key findings, deep insights, sources, and next steps."""

        try:
            messages = [
                {"role": "system", "content": EDITOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            report = await self.llm.chat(messages)
            progress.final_report = report.strip()

            progress.update_card_status(edit_card.id, "complete")
            edit_card.content = f"Report generated ({len(report.split())} words)"

        except Exception as e:
            # Fallback: compile a simple report from gathered facts
            fallback_report = self._fallback_report(progress)
            progress.final_report = fallback_report

            progress.update_card_status(edit_card.id, "complete")
            edit_card.content = "Report compiled from gathered facts (LLM elaboration unavailable)"

    def _fallback_report(self, progress: ResearchProgress) -> str:
        """Generate a simple report when the LLM editor is unavailable."""
        facts = progress.gathered_facts[:15]
        lines = [
            f"# Research: {progress.topic}",
            f"\n**Depth:** {progress.depth.value} | **Queries:** {len(progress.search_queries)} | **Findings:** {len(progress.gathered_facts)}",
            "\n## Key Findings\n",
        ]
        for f in facts:
            lines.append(f"- {f}")
        if progress.search_queries:
            lines.append("\n## Search Queries\n")
            for q in progress.search_queries:
                lines.append(f"- {q}")
        lines.append(f"\n---\n*Generated by BARQ Deep Research Agent on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        return "\n".join(lines)

    # ── LLM Extraction Helper ───────────────────────────────────────

    async def _extract_findings(self, query: str, results_text: str) -> Optional[dict]:
        """Use LLM to extract structured findings from search results."""
        if len(results_text) < 50:
            return None

        try:
            messages = [
                {"role": "system", "content": GATHERER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Query: {query}\n\nResults:\n{results_text[:3000]}"},
            ]
            response = await self.llm.chat(messages)
            text = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()
            if text.startswith("{"):
                return json.loads(text)
            return None
        except Exception:
            # Simple fallback extraction
            return {
                "findings": [r.get("snippet", "")[:120] for r in self._parse_results(results_text)[:3]],
                "gaps": ["More specific data needed"],
                "follow_up_queries": [f"{query} 2025", query],
                "key_sources": [""],
            }

    def _parse_results(self, text: str) -> list[dict]:
        """Simple parser for search result text."""
        results = []
        for block in text.split("\n\n"):
            if "Title:" in block or "Snippet:" in block:
                results.append({"text": block[:200]})
        return results

    def _build_result(self, progress: ResearchProgress) -> ResearchResult:
        """Build the final ResearchResult from progress."""
        sources = []
        for card in progress.cards:
            if card.card_type == "search" and card.status == "complete":
                sources.append({"query": card.metadata.get("query", ""), "title": card.title})
        return ResearchResult(
            topic=progress.topic,
            report=progress.final_report or "No report generated",
            sources=sources,
            facts=progress.gathered_facts,
            depth=progress.depth,
            cards=progress.cards,
        )
