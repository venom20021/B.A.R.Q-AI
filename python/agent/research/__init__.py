"""
BARQ Deep Research Agent — multi-agent iterative research loop.

Inspired by the ai_deep_research_agent pattern:
  - Gatherer Agent:  Iterative web search with query refinement
  - Elaborator Agent: Adds depth, context, and case studies
  - Editor Agent:     Polishes and formats the final report

Each phase produces progress cards that the frontend displays as
live-updating workspace cards.
"""

from .deep_research_agent import (
    DeepResearchAgent,
    ResearchProgress,
    ResearchCard,
    ResearchResult,
)

__all__ = [
    "DeepResearchAgent",
    "ResearchProgress",
    "ResearchCard",
    "ResearchResult",
]
