"""
BARQ Content Critic Agent (W7) — Evaluator-Optimizer pattern.

Quality-control loop for social media drafts:

    draft ──→ Critic LLM (scores against platform rules + topic)
                  │ score < threshold?
                  ├── yes → revise (apply feedback) → re-critique (max N)
                  └── no  → return final approved draft

Works standalone (POST /agent/content/critic) or as a ``content_critic``
skill inside the planner so any pipeline can gate its output.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from utils.ollama_client import OllamaClient

# Platform-specific formatting constraints (character limits etc.)
PLATFORM_RULES = {
    "twitter_thread": "Tweets have a 280-char limit; threads should hook hard in tweet 1.",
    "linkedin_post": "Professional tone, 1300-char soft limit, strong opening line, clear CTA.",
    "tiktok_short": "Hook in the first 3 seconds; conversational; use text-on-screen cues.",
    "youtube_shorts": "Fast hook, retention-focused, one clear message.",
    "instagram_reel": "Trend-aware hook, concise captions, hashtag light.",
    "blog_post": "Strong H1, scannable headers, 600+ words, conclusion with CTA.",
}

CRITIC_SYSTEM_PROMPT = """You are BARQ's strict content critic. Evaluate a draft against
the topic and platform rules. Be genuinely critical — mediocre drafts must score low.

Score 0-100 based on: hook strength, clarity, relevance to topic, authenticity
(no hallucinated facts), platform fit, and call-to-action.

Output ONLY valid JSON:
{
  "score": 74,
  "strengths": ["..."],
  "issues": ["specific problem 1", "specific problem 2"],
  "feedback": ["concrete rewrite instruction 1", "concrete rewrite instruction 2"]
}
Feedback must be actionable for a rewrite pass."""

REVISER_SYSTEM_PROMPT = """You are a top-tier social media copywriter performing a REVISION
pass. Apply the critic's feedback to improve the draft's score. Preserve the core
message and facts — improve clarity, hooks, platform fit, and CTA.

Output ONLY the revised draft text. No commentary, no code fences."""


class ContentCritic:
    """Evaluator-Optimizer loop for social drafts."""

    def __init__(
        self,
        min_score: int = 80,
        max_iterations: int = 2,
        client: Optional[OllamaClient] = None,
    ):
        self.min_score = int(min_score)
        self.max_iterations = max(int(max_iterations), 1)
        self._client = client

    def _get_client(self) -> OllamaClient:
        if self._client is None:
            self._client = OllamaClient(temperature=0.4)
        return self._client

    async def critique(self, draft: str, topic: str, platform: str = "linkedin_post") -> dict[str, Any]:
        platform_rule = PLATFORM_RULES.get(platform, "")
        prompt = f"""Topic: {topic}
Platform: {platform}
{platform_rule}

Draft to critique:
{draft[:3000]}

Output ONLY the JSON evaluation."""

        try:
            messages = [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = await self._get_client().chat(messages)
            data = self._parse_json(response)
        except Exception as e:
            print(f"[ContentCritic] Critique failed: {e}")
            data = {}

        score = float(data.get("score", 0) or 0)
        feedback = data.get("feedback") or data.get("issues") or []
        if isinstance(feedback, str):
            feedback = [feedback]

        return {
            "score": round(score, 1),
            "passed": score >= self.min_score,
            "strengths": data.get("strengths", []),
            "issues": data.get("issues", []),
            "feedback": [str(f) for f in feedback][:6],
        }

    async def revise(self, draft: str, topic: str, platform: str, feedback: list[str]) -> str:
        feedback_text = "\n".join(f"- {f}" for f in feedback)
        prompt = f"""Topic: {topic}
Platform: {platform}

Critic feedback to address:
{feedback_text}

Current draft:
{draft[:3000]}

Rewrite the draft addressing ALL feedback. Output ONLY the revised draft."""

        try:
            messages = [
                {"role": "system", "content": REVISER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = await self._get_client().chat(messages)
            revised = response.strip()
            if revised.startswith("```"):
                revised = re.sub(r"```[a-zA-Z]*", "", revised).strip().strip("`").strip()
            return revised if len(revised) > 30 else draft
        except Exception as e:
            print(f"[ContentCritic] Revision failed: {e}")
            return draft

    async def critique_and_improve(
        self,
        draft: str,
        topic: str,
        platform: str = "linkedin_post",
    ) -> dict[str, Any]:
        """Run the full evaluator-optimizer loop."""
        history: list[dict[str, Any]] = []
        current = draft

        for iteration in range(1, self.max_iterations + 1):
            critique = await self.critique(current, topic, platform)
            history.append(critique)
            if critique["passed"]:
                break
            if not critique["feedback"]:
                break

            print(f"[ContentCritic] Score {critique['score']} < {self.min_score} — revising (iter {iteration})")
            current = await self.revise(current, topic, platform, critique["feedback"])

        return {
            "final_draft": current,
            "passed": critique["passed"],
            "final_score": critique["score"],
            "iterations": len(history),
            "history": history,
            "revised": current != draft,
        }

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`").strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        return json.loads(text)


async def content_critic_skill(**kwargs: Any) -> str:
    """Skill handler for the planner/executor."""
    draft = kwargs.get("draft") or kwargs.get("script") or ""
    topic = kwargs.get("topic", "")
    platform = kwargs.get("platform", "linkedin_post")
    min_score = int(kwargs.get("min_score", 80))
    max_iterations = int(kwargs.get("max_iterations", 2))

    if not draft:
        return "No draft provided to critique."

    critic = ContentCritic(min_score=min_score, max_iterations=max_iterations)
    result = await critic.critique_and_improve(draft, topic, platform)
    if result["passed"]:
        status = "PASSED quality gate"
    else:
        status = f"best effort after {result['iterations']} revision(s) (score {result['final_score']})"
    return f"Content critic: {status}.\n\nFinal draft:\n{result['final_draft']}"
