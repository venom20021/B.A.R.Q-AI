"""
AI Job Matcher — scores job descriptions against the user's resume using Ollama.

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


class JobMatcher:
    """Matches job descriptions against the user's resume using a local LLM."""

    def __init__(self):
        self.settings = get_settings()

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
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert career matching AI. Score how well a candidate's "
                            "resume fits a job description. Be honest and specific. "
                            "Return ONLY valid JSON with the scoring breakdown."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                format="json",
                options={"temperature": 0.3},
            )

            result = json.loads(response["message"]["content"])
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

    def _fallback_match(self, job: dict[str, Any], resume: dict[str, Any]) -> dict[str, Any]:
        """Fallback keyword-based matching when LLM is unavailable."""
        title = job.get("title", "").lower()
        description = job.get("description", "").lower()
        resume_skills = [s.lower() for s in resume.get("skills", [])]

        matching = [s for s in resume_skills if s in title or s in description]
        missing = [s for s in resume_skills if s not in title and s not in description]

        skill_pct = int((len(matching) / max(len(resume_skills), 1)) * 100)

        return {
            "job_id": job.get("id", ""),
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "overall_score": skill_pct,
            "breakdown": {
                "skills_match": skill_pct,
                "experience_match": 50,
                "location_match": 50,
                "salary_match": 50,
            },
            "missing_skills": missing,
            "matching_skills": matching,
            "fit_summary": "Fallback keyword-based evaluation (LLM unavailable). "
                           f"Found {len(matching)} matching skills out of {len(resume_skills)}.",
            "recommended_actions": ["Run LLM-based evaluation when Ollama is available"],
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

