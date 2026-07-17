"""
BARQ Recruitment Agent Team — Multi-agent pipeline for job applications.

Inspired by the ai_recruitment_agent_team pattern from awesome-llm-apps.
Follows a sequential multi-agent workflow:

    1. ExtractorAgent  — Parses raw job descriptions → structured requirements
    2. MatcherAgent    — Compares extracted data against resume → match analysis
    3. WriterAgent     — Generates ATS-optimized resume + cover letter

Agents are independant LLM-powered workers with their own system prompts,
error recovery, and output schemas. The RecruitmentOrchestrator coordinates
the full pipeline with progress tracking and intermediate result passing.
"""

from .extractor import ExtractorAgent, ExtractionResult
from .matcher import MatcherAgent, MatchResult
from .orchestrator import RecruitmentOrchestrator, PipelineProgress
from .writer import WriterAgent, WriterResult

__all__ = [
    "ExtractorAgent", "ExtractionResult",
    "MatcherAgent", "MatchResult",
    "WriterAgent", "WriterResult",
    "RecruitmentOrchestrator", "PipelineProgress",
]
