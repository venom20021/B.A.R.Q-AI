"""
Tests for the agentic workflow skills (W1/W4-W7 registration) plus the
pure logic of the conversation memory and content critic workflows.
"""

import pytest

from agent.agentic_skills import register_agentic_skills
from agent.skill_registry import SkillRegistry
from agent.workflows.conversation_memory import _parse_extraction
from agent.workflows.content_critic import ContentCritic

EXPECTED_SKILLS = {
    "query_memory", "memory_snapshot", "run_workflow", "morning_briefing",
    "conversation_memory", "research_to_brain", "content_critic", "weekly_review",
}


def test_register_agentic_skills_idempotent():
    reg = SkillRegistry()
    register_agentic_skills(reg)
    register_agentic_skills(reg)  # second call must not raise
    names = set(reg.names())
    assert EXPECTED_SKILLS.issubset(names)
    assert reg.get("query_memory").category == "memory"
    assert reg.get("content_critic").category == "content"


def test_register_agentic_skills_uses_handlers():
    reg = SkillRegistry()
    register_agentic_skills(reg)
    # All agentic skills are handler-based (no HTTP dispatch dependency)
    for name in EXPECTED_SKILLS:
        skill = reg.get(name)
        assert skill.handler is not None, f"{name} should have a handler"


# ─── Conversation memory (W5) ─────────────────────────────────────────────


def test_parse_extraction_extracts_json():
    raw = '```json\n{"action_items": [{"text": "ship v2", "due": ""}], "facts": [{"key": "stack", "value": ".NET", "category": "preferences"}], "entities": [{"name": "Acme", "type": "company", "note": "talks to them"}], "summary": "planning release"}\n```'
    data = _parse_extraction(raw)
    assert data["action_items"][0]["text"] == "ship v2"
    assert data["facts"][0]["key"] == "stack"
    assert data["entities"][0]["name"] == "Acme"
    assert data["summary"] == "planning release"


def test_parse_extraction_handles_no_content():
    assert _parse_extraction("nothing here") == {}


def test_parse_extraction_handles_garbage():
    assert _parse_extraction("garbage !!!") == {}


# ─── Content critic (W7) ──────────────────────────────────────────────────


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def chat(self, messages):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


LOW = '{"score": 60, "strengths": [], "issues": ["weak hook"], "feedback": ["strengthen the opening hook"]}'
HIGH = '{"score": 95, "strengths": ["strong"], "issues": [], "feedback": []}'


@pytest.mark.asyncio
async def test_content_critic_passes_immediately():
    critic = ContentCritic(min_score=80, client=FakeClient([HIGH]))
    result = await critic.critique_and_improve("draft", "topic", "linkedin_post")
    assert result["passed"] is True
    assert result["final_score"] == 95
    assert result["revised"] is False
    assert result["iterations"] == 1


@pytest.mark.asyncio
async def test_content_critic_revises_until_pass():
    # Call order: critique(LOW) → revise → critique(HIGH)
    critic = ContentCritic(min_score=80, client=FakeClient([
        LOW,
        "Revised draft addressing feedback about the opening hook.",
        HIGH,
    ]))
    result = await critic.critique_and_improve("weak draft", "topic", "linkedin_post")
    assert result["passed"] is True
    assert result["revised"] is True
    assert result["iterations"] == 2
    assert "Revised draft" in result["final_draft"]


@pytest.mark.asyncio
async def test_content_critic_best_effort_when_never_passes():
    critic = ContentCritic(min_score=95, max_iterations=1, client=FakeClient([LOW]))
    result = await critic.critique_and_improve("draft", "topic", "linkedin_post")
    assert result["passed"] is False
    assert result["final_score"] == 60
