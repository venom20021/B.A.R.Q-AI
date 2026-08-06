"""
Tests for the EvaluatorAgent (Feature 2) — Reflection / Evaluator-Optimizer.

Uses a fake LLM client so tests never hit a real model:
- JSON parsing of evaluation responses
- Threshold pass/fail logic
- Revision loop on the markdown resume path
- Revision loop on the cover letter path
- Preserves profile rules (no fabrication instruction present in prompts)
"""

import pytest

from jobs.evaluator_agent import EvaluatorAgent, PROFILE_RULES

SAMPLE_JOB = {
    "title": "Backend Engineer",
    "company": "Acme Corp",
    "description": "Looking for a Fullstack Developer with strong backend focus in "
                   ".NET Core and Python, AWS experience, microservices, REST APIs.",
}

SAMPLE_RESUME = (
    "# Sai Prabhat\n"
    "Fullstack Developer (backend-focused) at Coinmint — .NET Core, AWS, Python.\n"
    "Computer Science Teacher at National Public Inter College.\n"
    "BSc Computer Science, University of Windsor.\n"
)


class FakeClient:
    """Returns scripted responses per call index."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def chat(self, messages):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


def _low_score_response():
    return '{"score": 55, "strengths": ["good structure"], "weaknesses": ["missing backend keywords"], "missing_keywords": [".NET", "AWS"], "feedback": ["Add .NET Core and AWS keywords", "Reorder bullets to emphasize backend"]}'


def _high_score_response():
    return '{"score": 92, "strengths": ["great match"], "weaknesses": [], "missing_keywords": [], "feedback": []}'


@pytest.mark.asyncio
async def test_evaluate_parses_json_and_flags_pass():
    agent = EvaluatorAgent(threshold=80, client=FakeClient([_high_score_response()]))
    result = await agent.evaluate("draft text", SAMPLE_JOB)
    assert result["score"] == 92
    assert result["passed"] is True


@pytest.mark.asyncio
async def test_evaluate_flags_fail_below_threshold():
    agent = EvaluatorAgent(threshold=80, client=FakeClient([_low_score_response()]))
    result = await agent.evaluate("draft text", SAMPLE_JOB)
    assert result["score"] == 55
    assert result["passed"] is False
    assert result["feedback"]


@pytest.mark.asyncio
async def test_evaluate_handles_garbage_output():
    agent = EvaluatorAgent(threshold=80, client=FakeClient(["not json at all"]))
    result = await agent.evaluate("draft text", SAMPLE_JOB)
    assert result["score"] == 0
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_ensure_resume_markdown_revises_then_passes():
    """Low score → revision via optimizer → high score."""
    class FakeOptimizer:
        async def optimize(self, resume_md, job, match_analysis=None, feedback=None):
            assert feedback  # evaluator feedback must be forwarded
            return {"optimized_md": (
                "# Sai Prabhat\n"
                "Fullstack Developer (backend-focused) at Coinmint with strong "
                ".NET Core, AWS, and Python expertise — resume revised to "
                "emphasize backend microservices work."
            )}

    # Call 1: evaluation (low) → optimizer revise → Call 2: evaluation (high)
    agent = EvaluatorAgent(
        threshold=80,
        client=FakeClient([_low_score_response(), _high_score_response()]),
    )
    result = await agent.ensure_resume_markdown(
        "initial optimized md", SAMPLE_RESUME, SAMPLE_JOB, FakeOptimizer()
    )
    assert result["passed"] is True
    assert result["final_score"] == 92
    assert result["revised"] is True
    assert result["iterations"] == 2


@pytest.mark.asyncio
async def test_ensure_resume_markdown_passes_without_revision():
    class FakeOptimizer:
        async def optimize(self, *a, **kw):
            raise AssertionError("optimizer should not be called when already passing")

    agent = EvaluatorAgent(threshold=80, client=FakeClient([_high_score_response()]))
    result = await agent.ensure_resume_markdown(
        "good resume", SAMPLE_RESUME, SAMPLE_JOB, FakeOptimizer()
    )
    assert result["passed"] is True
    assert result["revised"] is False


@pytest.mark.asyncio
async def test_ensure_cover_letter_revises_until_pass():
    # Call order: evaluate(LOW) → revise → evaluate(HIGH)
    agent = EvaluatorAgent(
        threshold=80,
        client=FakeClient([
            _low_score_response(),
            "Revised cover letter addressing evaluator feedback.",
            _high_score_response(),
        ]),
    )
    result = await agent.ensure_cover_letter("draft cover letter", SAMPLE_JOB)
    assert result["passed"] is True
    assert result["iterations"] == 2
    assert "Revised cover letter" in result["final_document"]


@pytest.mark.asyncio
async def test_ensure_resume_json_revises_through_optimizer():
    class FakeOptimizer:
        async def optimize_latex(self, resume_md, job, match_analysis=None, feedback=None):
            assert feedback
            return {"_mode": "latex_json", "json_data": {"summary": "revised", "skills": [".NET", "AWS"]}}

    initial_json = {"summary": "old", "skills": ["python"]}
    agent = EvaluatorAgent(
        threshold=80,
        client=FakeClient([_low_score_response(), _high_score_response()]),
    )
    result = await agent.ensure_resume_json(initial_json, SAMPLE_RESUME, SAMPLE_JOB, FakeOptimizer())
    assert result["passed"] is True
    assert result["final_json"]["summary"] == "revised"
    assert result["revised"] is True


def test_profile_rules_present_in_revisor_prompt():
    """Guardrail: the profile framing rules must survive in the revisor prompt."""
    assert "Fullstack" in PROFILE_RULES
    assert "backend" in PROFILE_RULES.lower()
    assert "NEVER add skills" in PROFILE_RULES
