"""
BARQ Matcher Agent — Compares extracted job requirements against user's resume.

Produces a structured match analysis including:
- Overall fit score (0-100)
- Per-category breakdown (skills, experience, education, location)
- Missing skills with severity (critical / important / minor)
- Recommended actions to improve fit
- ATS keyword density analysis
"""

import json
import re
from typing import Any, Optional

from utils.ollama_client import OllamaClient
from .extractor import ExtractionResult


# ─── Output Schema ─────────────────────────────────────────────────────────

class MatchResult:
    """Structured match analysis between extraction and resume."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.overall_score: int = raw.get("overall_score", 0)
        self.breakdown: dict[str, int] = raw.get("breakdown", {})
        self.missing_skills: list[dict[str, str]] = raw.get("missing_skills", [])
        self.matching_skills: list[str] = raw.get("matching_skills", [])
        self.experience_gap: str = raw.get("experience_gap", "")
        self.education_gap: str = raw.get("education_gap", "")
        self.fit_summary: str = raw.get("fit_summary", "")
        self.recommended_actions: list[str] = raw.get("recommended_actions", [])
        self.ats_keywords_found: int = raw.get("ats_keywords_found", 0)
        self.ats_keywords_total: int = raw.get("ats_keywords_total", 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "breakdown": self.breakdown,
            "missing_skills": self.missing_skills,
            "matching_skills": self.matching_skills,
            "experience_gap": self.experience_gap,
            "education_gap": self.education_gap,
            "fit_summary": self.fit_summary,
            "recommended_actions": self.recommended_actions,
            "ats_keywords_found": self.ats_keywords_found,
            "ats_keywords_total": self.ats_keywords_total,
        }

    def __repr__(self) -> str:
        return f"MatchResult(score={self.overall_score}, missing={len(self.missing_skills)})"


# ─── System Prompt ─────────────────────────────────────────────────────────

MATCHER_SYSTEM_PROMPT = """You are an expert Career Match Analysis Agent.

Your task: Compare a candidate's resume against extracted job requirements and
produce a structured match analysis. Be brutally honest — overstating fit helps
no one.

Return ONLY valid JSON with no markdown formatting or explanation.

Schema:
{
  "overall_score": <0-100 integer>,
  "breakdown": {
    "skills_match": <0-100>,
    "experience_match": <0-100>,
    "education_match": <0-100>,
    "location_match": <0-100>
  },
  "missing_skills": [
    {"skill": "skill_name", "severity": "critical" | "important" | "minor", "note": "why this matters"}
  ],
  "matching_skills": ["skill1", "skill2"],
  "experience_gap": "string — describe any experience gap or 'None identified'",
  "education_gap": "string — describe any education gap or 'None identified'",
  "fit_summary": "2-3 sentence honest assessment",
  "recommended_actions": ["action1", "action2"],
  "ats_keywords_found": <number>,
  "ats_keywords_total": <number>
}

Rules:
- overall_score = weighted combination of all breakdown categories
- Skills are weighted ~50%, experience ~25%, education ~15%, location ~10%
- missing_skills.severity: critical = must-have skill missing, important = nice-to-have missing, minor = gap but compensatable
- ATS keywords: count how many of the must-have skills appear in the resume vs total
- Be honest: if there's a significant gap, say so
"""


# ─── Matcher Agent ─────────────────────────────────────────────────────────

class MatcherAgent:
    """Compares extracted job requirements against user's resume for deep analysis."""

    def __init__(self):
        self.llm = OllamaClient()

    async def match(
        self,
        extraction: ExtractionResult,
        resume: dict[str, Any],
    ) -> MatchResult:
        """Compare extraction against resume and produce match analysis.

        Args:
            extraction: Structured extraction from ExtractorAgent.
            resume: Parsed resume dict from resume_parser.

        Returns:
            MatchResult with scores, gaps, and recommendations.
        """
        prompt = self._build_prompt(extraction, resume)
        messages = [
            {"role": "system", "content": MATCHER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.llm.chat(messages)
            text = response.strip()
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            data = json.loads(text)
            result = MatchResult(data)
            print(f"[MatcherAgent] Score: {result.overall_score}/100 — {len(result.missing_skills)} gaps identified")
            return result

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[MatcherAgent] LLM parsing failed: {e}")
            return self._fallback(extraction, resume)

        except Exception as e:
            print(f"[MatcherAgent] Unexpected error: {e}")
            return self._fallback(extraction, resume)

    def _build_prompt(self, extraction: ExtractionResult, resume: dict[str, Any]) -> str:
        resume_skills = resume.get("skills", [])
        resume_summary = resume.get("summary", "")[:500]
        experience_entries = resume.get("experience", [])
        exp_text = "\n".join(
            f"- {e.get('role', '')} at {e.get('company', '')} ({e.get('date_range', '')})"
            for e in experience_entries[:5]
        )

        return f"""
EXTRACTED JOB REQUIREMENTS:
Title: {extraction.job_title}
Company: {extraction.company}
Must-Have Skills: {', '.join(extraction.must_have_skills)}
Nice-to-Have Skills: {', '.join(extraction.nice_to_have_skills)}
Experience Required: {extraction.experience_years_required} years ({extraction.experience_level})
Education: {extraction.education}
Remote: {extraction.remote_status}
Key Responsibilities: {'; '.join(extraction.key_responsibilities)}
Salary: {extraction.salary_range}

CANDIDATE RESUME:
Skills: {', '.join(resume_skills)}
Summary: {resume_summary}
Recent Experience:
{exp_text}
Education: {json.dumps(resume.get('education', []))}

Please evaluate the match.
"""

    def _fallback(self, extraction: ExtractionResult, resume: dict[str, Any]) -> MatchResult:
        """Fallback keyword-based matching when LLM is unavailable."""
        resume_skills = [s.lower() for s in resume.get("skills", [])]
        must_have = [s.lower() for s in extraction.must_have_skills]
        nice_have = [s.lower() for s in extraction.nice_to_have_skills]

        matching = [s for s in must_have if s in resume_skills]
        missing = [s for s in must_have if s not in resume_skills]
        nice_matching = [s for s in nice_have if s in resume_skills]

        score = int((len(matching) / max(len(must_have), 1)) * 70 +
                    (len(nice_matching) / max(len(nice_have), 1)) * 30)

        raw = {
            "overall_score": min(score, 100),
            "breakdown": {
                "skills_match": int((len(matching) / max(len(must_have), 1)) * 100),
                "experience_match": 50,
                "education_match": 50,
                "location_match": 50 if extraction.remote_status != "onsite" else 30,
            },
            "missing_skills": [
                {"skill": s, "severity": "critical", "note": "Must-have skill not found in resume"}
                for s in missing
            ],
            "matching_skills": matching + nice_matching,
            "experience_gap": "Not evaluated (LLM unavailable)",
            "education_gap": "Not evaluated (LLM unavailable)",
            "fit_summary": f"Fallback analysis: {len(matching)}/{len(must_have)} must-have skills matched.",
            "recommended_actions": ["Run LLM-based matching when Ollama is available"],
            "ats_keywords_found": len(matching),
            "ats_keywords_total": len(must_have),
        }
        return MatchResult(raw)
