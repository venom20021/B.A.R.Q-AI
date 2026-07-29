"""
AI job evaluation using local LLM via OllamaClient (supports LM Studio, Groq fallback).
Scores jobs on fit, culture, compensation, and red flags.
"""

import json
from typing import Any

from config import get_settings
from utils.ollama_client import OllamaClient


class JobEvaluator:
    """Evaluates job listings against user preferences using a local LLM."""

    def __init__(self):
        self.settings = get_settings()
        self._llm = OllamaClient(temperature=0.3)

    async def evaluate(self, job: dict[str, Any], user_profile: dict[str, Any]) -> dict[str, Any]:
        """
        Score a job listing — concise evaluation.

        Args:
            job: Job listing dict with title, company, location, salary, description
            user_profile: User's preferences (skills, experience, salary expectations, etc.)

        Returns:
            Evaluation: match_score (0-5), pros (2-3 items), cons (2-3 items).
            No verbose reasoning, no conversational text.
        """
        prompt = self._build_concise_evaluation_prompt(job, user_profile)

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a career advisor AI. Evaluate the job listing against the "
                        "user's profile.\n"
                        "CRITICAL RULES:\n"
                        "1. Return ONLY a raw JSON object — no markdown, no code fences, no extra text.\n"
                        "2. Be brutally honest and concise.\n"
                        "3. No yapping, no conversational filler, no introductions or conclusions."
                    ),
                },
                {"role": "user", "content": prompt},
            ]

            response_text = await self._llm.chat(messages)

            # Strip any surrounding whitespace/code fences
            response_text = response_text.strip().strip("`").strip()
            if response_text.lower().startswith("json"):
                response_text = response_text[4:].strip().strip("`").strip()

            result = json.loads(response_text)
            return self._normalize_evaluation(result, job)

        except Exception as e:
            print(f"[Evaluator] LLM evaluation failed: {e}")
            return self._fallback_evaluation(job, user_profile)

    def _build_concise_evaluation_prompt(self, job: dict[str, Any], profile: dict[str, Any]) -> str:
        """Build a concise evaluation prompt requesting strict JSON output only."""
        return f"""Job Listing:
- Title: {job.get('title', 'Unknown')}
- Company: {job.get('company', 'Unknown')}
- Location: {job.get('location', 'Unknown')}
- Salary: {job.get('salary', 'Not specified')}
- Description: {job.get('description', '')[:1500]}

User Profile:
- Skills: {', '.join(profile.get('skills', [])[:15])}
- Experience Level: {profile.get('experience_level', 'Mid')}
- Target Salary: {profile.get('target_salary', 'Not specified')}
- Preferred Locations: {', '.join(profile.get('preferred_locations', []))}
- Remote Preference: {profile.get('remote_preference', 'Any')}

Return ONLY this exact JSON — no extra text:
{{
  "match_score": <0.0-5.0>,
  "pros": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "cons": ["<weakness 1>", "<weakness 2>", "<weakness 3>"]
}}

- match_score: Overall fit to the user's profile (0 = no fit, 5 = perfect).
- pros: 2-3 specific reasons why this job fits (skills match, growth, comp, culture).
- cons: 2-3 specific reasons of concern (missing skills, red flags, location, etc.).
"""

    def _normalize_evaluation(
        self, result: dict[str, Any], job: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize LLM output to a consistent format."""
        match_score = min(max(float(result.get("match_score", result.get("overall", 3.0))), 0), 5)
        pros = result.get("pros", [])
        cons = result.get("cons", [])
        return {
            "job_id": job.get("id", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "overall_score": match_score,
            "scores": {
                "role_fit": match_score,
                "culture": match_score,
                "compensation": match_score,
                "growth": match_score,
                "red_flags": 0.0,
            },
            "reasoning": "",
            "pros": pros,
            "cons": cons,
            "match_percentage": round(match_score * 20, 1),
        }

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

    @staticmethod
    def _extract_flat_skills(skills_raw: list) -> list:
        """Extract clean skill keywords from resume skills that may have
        markdown formatting like '- **Backend:** Python'."""
        flat = []
        for s in skills_raw:
            if not s:
                continue
            cleaned = s.lower().replace("**", "").strip().lstrip("- ").lstrip("* ")
            # If format is "category: skills" take the skills part after colon
            if ":" in cleaned:
                cleaned = cleaned.split(":")[-1].strip()
            # Split on commas for compound entries
            for part in cleaned.split(","):
                p = part.strip().split("(")[0].strip()
                if p and len(p) > 1:
                    flat.append(p)
        return flat

    def _fallback_evaluation(
        self, job: dict[str, Any], profile: dict[str, Any]
    ) -> dict[str, Any]:
        """Fallback evaluation when LLM is unavailable.

        Uses weighted keyword matching to avoid the "all skills match because
        descriptions contain every buzzword" bug. Skills found in the job
        TITLE count MORE than skills only found in the description body.
        Returns a conservative score (max 60%) so the user knows LLM eval
        would give better results.
        """
        title = (job.get("title", "") or "").lower()
        description = (job.get("description", "") or "").lower()
        desc_head = description[:500]

        skills_raw = profile.get("skills", []) or profile.get("tech_skills", [])
        skills = self._extract_flat_skills(skills_raw)
        if not skills:
            return {
                "job_id": job.get("id", ""),
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "overall_score": 2.5,
                "scores": {"role_fit": 2.5, "culture": 2.5, "compensation": 2.5, "growth": 2.5, "red_flags": 0.0},
                "reasoning": "Insufficient skill data for evaluation.",
                "pros": [], "cons": ["No resume data available for detailed matching"],
                "match_percentage": 50.0,
            }

        # Score based on matched skills: title matches = 15% each, desc matches = 5% each
        # This avoids the "dividing by 34 skills makes everything 0" problem
        title_matches = 0
        desc_matches = 0
        matched_skills = []
        for skill in skills:
            if skill and len(skill) > 1:
                if skill in title:
                    title_matches += 1
                    matched_skills.append(skill)
                elif skill in desc_head:
                    desc_matches += 1
                    matched_skills.append(skill)

        raw_score = title_matches * 15 + desc_matches * 5
        final_score_pct = min(raw_score, 60)
        overall = round(final_score_pct / 20, 1)  # Convert 0-60% to 0-3.0 / 5

        return {
            "job_id": job.get("id", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "overall_score": overall,
            "scores": {
                "role_fit": overall,
                "culture": 3.0,
                "compensation": 3.0,
                "growth": 3.0,
                "red_flags": 0.0,
            },
            "reasoning": "Fallback evaluation (LLM unavailable). Based on keyword matching. "
                           f"Matched {len(matched_skills)} skill(s): {', '.join(matched_skills[:8])}.",
            "pros": [f"{title_matches} skills found in job title"],
            "cons": ["LLM evaluation unavailable — install LM Studio or Ollama for accurate scoring"],
            "match_percentage": final_score_pct,
        }
