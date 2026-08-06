"""
BARQ Research → Brain Agent (W6) — Orchestrator-Workers pattern.

When a Deep Research session completes, this workflow mines the final report
for knowledge triplets and commits them to the knowledge graph (multi-brain),
so every research session compounds into BARQ's long-term memory.

    report ──→ TripletExtractor (LLM) ──→ knowledge graph (brain 'research')
              └──→ MemoryBus category 'research' (pointer)

Blocking graph writes run via ``asyncio.to_thread`` — never blocks the loop.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional


async def extract_research_to_brain(
    topic: str,
    report: str,
    brain_type: str = "research",
) -> dict[str, Any]:
    """Extract knowledge triplets from a research report into the knowledge graph.

    Args:
        topic: The research topic.
        report: The final research report markdown.
        brain_type: Knowledge graph brain to write into.

    Returns:
        dict with triplets count, brain, and status.
    """
    if not report or len(report.strip()) < 80:
        return {"status": "skipped", "reason": "report too short"}

    try:
        from memory_knowledge.ingestion import get_extractor

        extractor = get_extractor()
        # process_document is synchronous blocking (LLM call) → run in thread
        count = await asyncio.to_thread(
            extractor.process_document, brain_type, report[:8000]
        )
    except Exception as e:
        print(f"[ResearchToBrain] Graph extraction failed: {e}")
        count = 0

    # Also store a pointer memory so the brain entry is discoverable
    try:
        from memory.memory_bus import get_memory_bus
        stable_key = re.sub(r"\W+", "_", topic.lower())[:50] or "research"
        await get_memory_bus().store(
            f"research_{stable_key}",
            topic[:200],
            category="research",
            source="agent",
            tags=["research", "knowledge-graph"],
            ttl_seconds=None,
        )
    except Exception as e:
        print(f"[ResearchToBrain] Memory pointer failed: {e}")

    try:
        from database import analytics_dao
        await analytics_dao.log_activity(
            "research", "research_to_brain",
            f"Extracted {count} triplets from research '{topic[:80]}' into brain '{brain_type}'",
        )
    except Exception as e:
        print(f"[ResearchToBrain] Activity log failed: {e}")

    return {
        "status": "completed" if count else "empty",
        "brain": brain_type,
        "topic": topic,
        "triplets_extracted": count,
    }


async def research_to_brain_skill(**kwargs: Any) -> str:
    """Skill handler for the planner/executor."""
    topic = kwargs.get("topic", "untitled research")
    report = kwargs.get("report", "")
    result = await extract_research_to_brain(topic, report)
    if result["status"] == "skipped":
        return "Research report too short to extract knowledge."
    return (
        f"Extracted {result.get('triplets_extracted', 0)} knowledge triplets from "
        f"'{topic[:60]}' into the {result.get('brain')} brain."
    )
