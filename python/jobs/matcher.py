"""
AI Job Matcher — scores job descriptions against the user's resume using OllamaClient
(supports LM Studio, Groq fallback).

Scoring criteria (0-100):
- Skills match percentage
- Experience level match
- Location/remote compatibility
- Salary alignment
- Overall fit impression

Returns: overall score, breakdown, missing skills, fit summary
"""

import json
import re
from typing import Any

from config import get_settings
from utils.ollama_client import OllamaClient


class JobMatcher:
    """Matches job descriptions against the user's resume using a local LLM."""

    def __init__(self):
        self.settings = get_settings()
        self._llm = OllamaClient(temperature=0.3)

    async def match(self, job: dict[str, Any], resume: dict[str, Any]) -> dict[str, Any]:
        """
        Score a job against the user's resume.

        Args:
            job: Job listing dict (title, company, description, location, salary, etc.)
            resume: Parsed resume dict (skills, experience, education, etc.)

        Returns:
            Dict with overall_score (0-100), breakdown, missing_skills, fit_summary
        """
        prompt = self._build_match_prompt(job, resume)

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert career matching AI. Score how well a candidate's "
                        "resume fits a job description. Be honest and specific. "
                        "Return ONLY valid JSON with the scoring breakdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ]

            response_text = await self._llm.chat(messages)

            # Extract JSON from response (LLM may wrap in markdown code blocks)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [line for line in lines if not line.startswith("```")]
                response_text = "\n".join(lines)

            result = json.loads(response_text)
            return self._normalize(result, job, resume)

        except Exception as e:
            print(f"[Matcher] LLM match failed: {e}")
            return self._fallback_match(job, resume)

    def _build_match_prompt(self, job: dict[str, Any], resume: dict[str, Any]) -> str:
        return f"""
Job Description:
- Title: {job.get('title', 'Unknown')}
- Company: {job.get('company', 'Unknown')}
- Location: {job.get('location', 'Unknown')}
- Salary: {self._format_salary(job)}
- Remote: {job.get('remote_status', 'unknown')}
- Description: {job.get('description', '')[:1500]}

Candidate Resume:
- Skills: {', '.join(resume.get('skills', []))}
- Experience Level: {self._infer_experience_level(resume)}
- Years of Experience: ~{self._count_experience_years(resume)}
- Summary: {resume.get('summary', '')[:300]}
- Recent Roles: {self._format_recent_roles(resume)}

Please evaluate on these criteria (0-100 scale):
1. skills_match: What percentage of required skills does the candidate have?
2. experience_match: How well does experience level align? (consider years + seniority)
3. location_match: Is location/remote compatible?
4. salary_match: Does salary range align (if data available)?
5. overall_fit: Holistic impression of candidacy fit

Return format:
{{
    "overall_score": <0-100>,
    "skills_match": <0-100>,
    "experience_match": <0-100>,
    "location_match": <0-100>,
    "salary_match": <0-100>,
    "missing_skills": ["skill1", "skill2"],
    "matching_skills": ["skill1", "skill2"],
    "fit_summary": "<2-3 sentence explanation>",
    "recommended_actions": ["action1", "action2"]
}}
"""

    def _normalize(self, result: dict, job: dict, resume: dict) -> dict[str, Any]:
        """Normalize and validate the LLM response."""
        return {
            "job_id": job.get("id", ""),
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "overall_score": max(0, min(100, int(result.get("overall_score", 0)))),
            "breakdown": {
                "skills_match": max(0, min(100, int(result.get("skills_match", 0)))),
                "experience_match": max(0, min(100, int(result.get("experience_match", 0)))),
                "location_match": max(0, min(100, int(result.get("location_match", 0)))),
                "salary_match": max(0, min(100, int(result.get("salary_match", 0)))),
            },
            "missing_skills": result.get("missing_skills", []),
            "matching_skills": result.get("matching_skills", []),
            "fit_summary": result.get("fit_summary", ""),
            "recommended_actions": result.get("recommended_actions", []),
            "evaluated_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _extract_flat_skills(skills_raw: list) -> list:
        """Extract clean skill keywords from resume skills that may have
        markdown formatting like '- **Backend:** Python'."""
        flat = []
        for s in skills_raw:
            if not s:
                continue
            cleaned = s.lower().replace("**", "").strip().lstrip("- ").lstrip("* ")
            if ":" in cleaned:
                cleaned = cleaned.split(":")[-1].strip()
            for part in cleaned.split(","):
                p = part.strip().split("(")[0].strip()
                if p and len(p) > 1:
                    flat.append(p)
        return flat

    def _fallback_match(self, job: dict[str, Any], resume: dict[str, Any]) -> dict[str, Any]:
        """Fallback keyword-based matching when LLM is unavailable.

        Uses weighted scoring: title matches count more than description-only
        matches. Caps at 65% to indicate LLM would give more accurate results.
        Avoids the "all skills match because descriptions contain every buzzword" bug.
        """
        title = (job.get("title", "") or "").lower()
        description = (job.get("description", "") or "").lower()
        desc_head = description[:500]
        resume_skills = self._extract_flat_skills(resume.get("skills", []))

        if not resume_skills:
            return {
                "job_id": job.get("id", ""), "job_title": job.get("title", ""),
                "company": job.get("company", ""), "overall_score": 40,
                "breakdown": {"skills_match": 40, "experience_match": 40, "location_match": 40, "salary_match": 40},
                "missing_skills": [], "matching_skills": [],
                "fit_summary": "No resume skills data available for matching.",
                "recommended_actions": ["Upload a complete resume with skills listed"],
                "evaluated_at": __import__("datetime").datetime.utcnow().isoformat(),
            }

        # Score based on matched skills: title matches = 15% each, desc matches = 5% each
        title_matches = []
        desc_matches = []
        no_match = []
        for skill in resume_skills:
            if skill and len(skill) > 1:
                if skill in title:
                    title_matches.append(skill)
                elif skill in desc_head:
                    desc_matches.append(skill)
                else:
                    no_match.append(skill)

        raw_score = len(title_matches) * 15 + len(desc_matches) * 5
        final_score = min(raw_score, 65)

        return {
            "job_id": job.get("id", ""),
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "overall_score": final_score,
            "breakdown": {
                "skills_match": final_score,
                "experience_match": 50,
                "location_match": 50,
                "salary_match": 50,
            },
            "missing_skills": no_match,
            "matching_skills": title_matches + desc_matches,
            "fit_summary": f"Fallback weighted evaluation (LLM unavailable). "
                           f"Matched {len(title_matches + desc_matches)} skill(s): "
                           f"{', '.join((title_matches + desc_matches)[:8])}.",
            "recommended_actions": ["Enable LM Studio/Ollama for accurate AI-based scoring"],
            "evaluated_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

    def _format_salary(self, job: dict) -> str:
        """Format salary range."""
        if job.get("salary_min") and job.get("salary_max"):
            return f"${job['salary_min']:,} - ${job['salary_max']:,}"
        return "Not specified"

    def _infer_experience_level(self, resume: dict) -> str:
        """Infer experience level from resume data."""
        years = self._count_experience_years(resume)
        if years < 2:
            return "Entry"
        elif years < 5:
            return "Mid"
        elif years < 10:
            return "Senior"
        return "Lead/Executive"

    def _count_experience_years(self, resume: dict) -> int:
        """Estimate total years of experience from resume entries."""
        total = 0
        for exp in resume.get("experience", []):
            date_str = exp.get("date_range", "")
            if not date_str:
                continue
            # Look for year patterns
            years = re.findall(r"\b(20\d{2})\b", date_str)
            if len(years) >= 2:
                try:
                    total += int(years[-1]) - int(years[0])
                except (ValueError, IndexError):
                    total += 1
            elif len(years) == 1:
                total += 1
        return max(total, 1)

    def _format_recent_roles(self, resume: dict) -> str:
        """Format recent experience for the prompt."""
        roles = []
        for exp in resume.get("experience", [])[:3]:
            roles.append(f"- {exp.get('role', 'Unknown')} at {exp.get('company', 'Unknown')}")
        return "\n".join(roles) if roles else "No experience listed"
