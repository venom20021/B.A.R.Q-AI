"""
BARQ Extractor Agent — Parses raw job descriptions into structured data.

Uses the local LLM (Ollama) to extract:
- Required skills (must-have vs nice-to-have)
- Experience level and years required
- Education requirements
- Key responsibilities
- Company context (industry, size, culture clues)
- Salary range (if available)
- Remote/onsite/hybrid status

Outputs a structured ``ExtractionResult`` that the MatcherAgent consumes.
"""

import json
import re
from typing import Any, Optional

from utils.ollama_client import OllamaClient


# ─── Output Schema ─────────────────────────────────────────────────────────

class ExtractionResult:
    """Structured output from the ExtractorAgent."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.job_title: str = raw.get("job_title", "")
        self.company: str = raw.get("company", "")
        self.must_have_skills: list[str] = raw.get("must_have_skills", [])
        self.nice_to_have_skills: list[str] = raw.get("nice_to_have_skills", [])
        self.experience_years_required: int = raw.get("experience_years_required", 0)
        self.experience_level: str = raw.get("experience_level", "mid")
        self.education: str = raw.get("education", "Not specified")
        self.key_responsibilities: list[str] = raw.get("key_responsibilities", [])
        self.industry: str = raw.get("industry", "")
        self.salary_range: str = raw.get("salary_range", "Not specified")
        self.remote_status: str = raw.get("remote_status", "unknown")
        self.culture_clues: list[str] = raw.get("culture_clues", [])
        self.raw_description: str = raw.get("raw_description", "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_title": self.job_title,
            "company": self.company,
            "must_have_skills": self.must_have_skills,
            "nice_to_have_skills": self.nice_to_have_skills,
            "experience_years_required": self.experience_years_required,
            "experience_level": self.experience_level,
            "education": self.education,
            "key_responsibilities": self.key_responsibilities,
            "industry": self.industry,
            "salary_range": self.salary_range,
            "remote_status": self.remote_status,
            "culture_clues": self.culture_clues,
        }

    def __repr__(self) -> str:
        return f"ExtractionResult(job_title='{self.job_title}', skills={len(self.must_have_skills)+len(self.nice_to_have_skills)} total)"


# ─── System Prompt ─────────────────────────────────────────────────────────

EXTRACTOR_SYSTEM_PROMPT = """You are an expert Job Description Extractor Agent.

Your task: Parse a raw job description and extract structured information.
Be thorough and accurate. Distinguish between MUST-HAVE skills (explicitly required)
and NICE-TO-HAVE skills (preferred but not required).

Return ONLY valid JSON with no markdown formatting or explanation.

Schema:
{
  "job_title": "string — normalized title",
  "company": "string — company name",
  "must_have_skills": ["skill1", "skill2"],
  "nice_to_have_skills": ["skill3", "skill4"],
  "experience_years_required": number | 0 if not specified,
  "experience_level": "entry" | "mid" | "senior" | "lead" | "not specified",
  "education": "string — degree requirements or 'Not specified'",
  "key_responsibilities": ["responsibility1", "responsibility2"],
  "industry": "string — inferred industry or empty string",
  "salary_range": "string — e.g. '$100k-$150k' or 'Not specified'",
  "remote_status": "remote" | "hybrid" | "onsite" | "unknown",
  "culture_clues": ["clue1", "clue2"]
}

Rules:
- MUST-HAVE = explicitly required ("must have", "requires", "need", "proficient in")
- NICE-TO-HAVE = preferred ("preferred", "nice to have", "bonus", "plus")
- If a skill appears in both, put it in must_have_skills
- Be specific: extract "Python" not "programming languages"
- If a field has no data, use empty string / empty list / 0 as appropriate
"""


# ─── Extractor Agent ───────────────────────────────────────────────────────

class ExtractorAgent:
    """Parses raw job descriptions into structured extraction data using LLM."""

    def __init__(self):
        self.llm = OllamaClient()

    async def extract(self, job_description: str, title_hint: str = "", company_hint: str = "") -> ExtractionResult:
        """Extract structured data from a raw job description.

        Args:
            job_description: Raw job description text.
            title_hint: Optional job title hint for context.
            company_hint: Optional company name hint.

        Returns:
            ExtractionResult with structured fields.
        """
        context = ""
        if title_hint:
            context += f"Job Title: {title_hint}\n"
        if company_hint:
            context += f"Company: {company_hint}\n"

        user_prompt = f"{context}\nRaw Job Description:\n{job_description[:4000]}"

        messages = [
            {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self.llm.chat(messages)
            text = response.strip()
            # Strip markdown fences
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            data = json.loads(text)
            data["raw_description"] = job_description[:1000]
            result = ExtractionResult(data)
            print(f"[ExtractorAgent] Extracted {len(result.must_have_skills)} must-have + {len(result.nice_to_have_skills)} nice-to-have skills for '{result.job_title}'")
            return result

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[ExtractorAgent] LLM parsing failed: {e}")
            return self._fallback(job_description, title_hint, company_hint)

        except Exception as e:
            print(f"[ExtractorAgent] Unexpected error: {e}")
            return self._fallback(job_description, title_hint, company_hint)

    def _fallback(self, description: str, title_hint: str, company_hint: str) -> ExtractionResult:
        """Fallback: simple keyword-based extraction when LLM is unavailable."""
        desc_lower = description.lower()
        skills_keywords = [
            "python", "javascript", "typescript", "react", "node", "java", "c++", "go",
            "rust", "sql", "aws", "docker", "kubernetes", "git", "linux", "fastapi",
            "django", "flask", "machine learning", "ai", "data science",
        ]
        found = [s for s in skills_keywords if s in desc_lower]

        # Infer remote status
        remote_status = "unknown"
        if "remote" in desc_lower and "onsite" not in desc_lower:
            remote_status = "remote"
        elif "hybrid" in desc_lower:
            remote_status = "hybrid"
        elif "onsite" in desc_lower:
            remote_status = "onsite"

        raw = {
            "job_title": title_hint or "Unknown Position",
            "company": company_hint or "",
            "must_have_skills": found,
            "nice_to_have_skills": [],
            "experience_years_required": 0,
            "experience_level": "not specified",
            "education": "Not specified",
            "key_responsibilities": [],
            "industry": "",
            "salary_range": "Not specified",
            "remote_status": remote_status,
            "culture_clues": [],
            "raw_description": description[:1000],
        }
        print(f"[ExtractorAgent] Fallback: keyword extraction found {len(found)} skills")
        return ExtractionResult(raw)
