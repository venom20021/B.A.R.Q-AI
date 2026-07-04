"""
AI job evaluation using local LLM (Ollama/Llama 3.1).
Scores jobs on fit, culture, compensation, and red flags.
"""

import json
from typing import Any

from config import get_settings


class JobEvaluator:
    """Evaluates job listings against user preferences using a local LLM."""

    def __init__(self):
        self.settings = get_settings()

    async def evaluate(self, job: dict[str, Any], user_profile: dict[str, Any]) -> dict[str, Any]:
        """
        Score a job listing on multiple dimensions.

        Args:
            job: Job listing dict with title, company, location, salary, description
            user_profile: User's preferences (skills, experience, salary expectations, etc.)

        Returns:
            Evaluation with scores (0-5) and reasoning
        """
        prompt = self._build_evaluation_prompt(job, user_profile)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a career advisor AI. Evaluate the job listing against the "
                            "user's profile. Return ONLY a JSON object with scores and reasoning."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                format="json",
                options={"temperature": 0.3},
            )

            result = json.loads(response["message"]["content"])
            return self._normalize_evaluation(result, job)

        except Exception as e:
            print(f"[Evaluator] LLM evaluation failed: {e}")
            return self._fallback_evaluation(job, user_profile)

    def _build_evaluation_prompt(self, job: dict[str, Any], profile: dict[str, Any]) -> str:
        return f"""
Job Listing:
- Title: {job.get('title', 'Unknown')}
- Company: {job.get('company', 'Unknown')}
- Location: {job.get('location', 'Unknown')}
- Salary: {job.get('salary', 'Not specified')}
- Description: {job.get('description', '')[:1000]}

User Profile:
- Skills: {', '.join(profile.get('skills', []))}
- Experience Level: {profile.get('experience_level', 'Mid')}
- Target Salary: {profile.get('target_salary', 'Not specified')}
- Preferred Locations: {', '.join(profile.get('preferred_locations', []))}
- Remote Preference: {profile.get('remote_preference', 'Any')}
- Industry: {profile.get('industry', 'Technology')}

Evaluate this job on:
1. Role Fit (0-5): How well does the role match the user's skills and experience?
2. Culture Score (0-5): Likelihood of good culture fit based on company and role type
3. Compensation Score (0-5): How well does the compensation match expectations?
4. Growth Potential (0-5): Career growth and learning opportunities
5. Red Flags (0-5): Lower is better. Flag any concerns (unpaid, unrealistic requirements, etc.)

Return format:
{{"role_fit": <score>, "culture_score": <score>, "compensation_score": <score>, "growth_potential": <score>, "red_flags": <score>, "overall": <average_score>, "reasoning": "<brief explanation>", "pros": ["<pro1>", "<pro2>"], "cons": ["<con1>", "<con2>"]}}
"""

    def _normalize_evaluation(
        self, result: dict[str, Any], job: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize LLM output to a consistent format."""
        return {
            "job_id": job.get("id", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "overall_score": min(max(float(result.get("overall", 0)), 0), 5),
            "scores": {
                "role_fit": min(max(float(result.get("role_fit", 0)), 0), 5),
                "culture": min(max(float(result.get("culture_score", 0)), 0), 5),
                "compensation": min(max(float(result.get("compensation_score", 0)), 0), 5),
                "growth": min(max(float(result.get("growth_potential", 0)), 0), 5),
                "red_flags": min(max(float(result.get("red_flags", 0)), 0), 5),
            },
            "reasoning": result.get("reasoning", ""),
            "pros": result.get("pros", []),
            "cons": result.get("cons", []),
            "match_percentage": round(
                min(max(float(result.get("overall", 0)), 0), 5) * 20, 1
            ),
        }

    def _fallback_evaluation(
        self, job: dict[str, Any], profile: dict[str, Any]
    ) -> dict[str, Any]:
        """Fallback evaluation when LLM is unavailable."""
        # Simple keyword-based scoring
        title = job.get("title", "").lower()
        description = job.get("description", "").lower()
        skills = [s.lower() for s in profile.get("skills", [])]

        matching_skills = sum(1 for skill in skills if skill in title or skill in description)
        skill_score = min(matching_skills / max(len(skills), 1) * 5, 5)

        return {
            "job_id": job.get("id", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "overall_score": skill_score,
            "scores": {
                "role_fit": skill_score,
                "culture": 3.0,
                "compensation": 3.0,
                "growth": 3.0,
                "red_flags": 0.0,
            },
            "reasoning": "Fallback evaluation (LLM unavailable). Based on keyword matching.",
            "pros": [],
            "cons": ["LLM evaluation unavailable"],
            "match_percentage": round(skill_score * 20, 1),
        }
