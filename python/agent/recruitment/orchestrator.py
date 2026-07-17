"""
BARQ Recruitment Orchestrator — Coordinates the multi-agent pipeline.

Runs the full pipeline: Extract → Match → Write with:
- Progress tracking via PipelineProgress
- Intermediate result passing between agents
- Error recovery at each stage
- Timing and metrics collection
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from config import get_settings
from jobs.resume_parser import parse_resume
from utils.ollama_client import OllamaClient

from .extractor import ExtractorAgent, ExtractionResult
from .matcher import MatcherAgent, MatchResult
from .writer import WriterAgent, WriterResult


# ─── Progress Tracking ─────────────────────────────────────────────────────

@dataclass
class PipelineProgress:
    """Tracking state for the recruitment pipeline."""
    status: str = "idle"  # idle → extracting → matching → writing → complete | error
    phase: str = ""
    progress_pct: int = 0
    message: str = ""
    started_at: Optional[float] = None
    elapsed_seconds: float = 0.0

    # Results (populated as pipeline progresses)
    extraction: Optional[dict[str, Any]] = None
    match: Optional[dict[str, Any]] = None
    writer: Optional[dict[str, Any]] = None
    cover_letter: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "phase": self.phase,
            "progress_pct": self.progress_pct,
            "message": self.message,
            "started_at": self.started_at,
            "elapsed_seconds": self.elapsed_seconds if self.started_at else 0,
            "extraction": self.extraction,
            "match": self.match,
            "writer": self.writer,
            "cover_letter": self.cover_letter,
        }


# ─── Orchestrator ──────────────────────────────────────────────────────────

class RecruitmentOrchestrator:
    """Orchestrates the multi-agent recruitment pipeline."""

    def __init__(self):
        self.extractor = ExtractorAgent()
        self.matcher = MatcherAgent()
        self.writer = WriterAgent()
        self._progress = PipelineProgress()

    def get_progress(self) -> PipelineProgress:
        """Get current pipeline progress."""
        if self._progress.started_at:
            self._progress.elapsed_seconds = time.time() - self._progress.started_at
        return self._progress

    def _update(self, status: str, phase: str, pct: int, message: str):
        self._progress.status = status
        self._progress.phase = phase
        self._progress.progress_pct = pct
        self._progress.message = message
        if self._progress.started_at:
            self._progress.elapsed_seconds = time.time() - self._progress.started_at

    def _reset(self):
        self._progress = PipelineProgress()
        self._progress.started_at = time.time()

    async def run_full_pipeline(
        self,
        job_description: str,
        title_hint: str = "",
        company_hint: str = "",
        resume_path: Optional[str] = None,
        generate_cover_letter: bool = True,
    ) -> PipelineProgress:
        """Run the full Extractor → Matcher → Writer pipeline.

        Args:
            job_description: Raw job description text.
            title_hint: Optional job title hint.
            company_hint: Optional company name hint.
            resume_path: Optional custom resume path.
            generate_cover_letter: Whether to also generate a cover letter.

        Returns:
            PipelineProgress with all results.
        """
        self._reset()
        self._update("extracting", "Extracting job requirements...", 5,
                      "Analyzing job description with ExtractorAgent")

        # ── Phase 1: Extract ──────────────────────────────────────────────
        try:
            extraction: ExtractionResult = await self.extractor.extract(
                job_description, title_hint, company_hint
            )
            self._progress.extraction = extraction.to_dict()
            self._update("matching", "Matching against resume...", 30,
                         f"Extracted {len(extraction.must_have_skills)} must-have skills")
        except Exception as e:
            self._progress.status = "error"
            self._progress.message = f"Extraction failed: {e}"
            return self._progress

        # ── Phase 2: Match ────────────────────────────────────────────────
        try:
            resume = parse_resume(resume_path)
            if resume.get("_error"):
                self._update("error", "Resume error", 35,
                             f"Resume not found: {resume['_error']}")
                return self._progress

            match: MatchResult = await self.matcher.match(extraction, resume)
            self._progress.match = match.to_dict()
            self._update("writing", "Generating optimized documents...", 55,
                         f"Match score: {match.overall_score}/100 — {len(match.missing_skills)} gaps")
        except Exception as e:
            self._progress.status = "error"
            self._progress.message = f"Matching failed: {e}"
            return self._progress

        # ── Phase 3: Write ────────────────────────────────────────────────
        try:
            resume_md = resume.get("raw_md", "")

            writer: WriterResult = await self.writer.write_resume(
                extraction, match, resume_md
            )
            self._progress.writer = writer.to_dict()

            # Optional cover letter
            if generate_cover_letter:
                self._update("writing", "Generating cover letter...", 80,
                             "Crafting tailored cover letter")
                cover = await self.writer.write_cover_letter(
                    extraction, match, resume_md, writer.optimized_resume
                )
                self._progress.cover_letter = cover

            self._update("complete", "Pipeline complete", 100,
                         f"Pipeline finished. Score: {match.overall_score}/100. "
                         f"Resume: {'✅' if writer.optimized_resume else '❌'} "
                         f"Cover letter: {'✅' if self._progress.cover_letter else '❌'}")

        except Exception as e:
            self._progress.status = "error"
            self._progress.message = f"Document generation failed: {e}"

        self._progress.elapsed_seconds = time.time() - self._progress.started_at
        return self._progress

    async def run_extract_only(self, job_description: str, title_hint: str = "",
                                company_hint: str = "") -> ExtractionResult:
        """Run only the extraction phase."""
        return await self.extractor.extract(job_description, title_hint, company_hint)

    async def run_match_only(self, extraction: ExtractionResult,
                              resume_path: Optional[str] = None) -> MatchResult:
        """Run only the matching phase."""
        resume = parse_resume(resume_path)
        return await self.matcher.match(extraction, resume)
