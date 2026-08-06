"""
Tests for the weekly review workflow (W11): data gathering, LLM synthesis
(with deterministic fallback), the full run pipeline, and skill registration.
"""

import pytest

from agent.agentic_skills import register_agentic_skills
from agent.skill_registry import SkillRegistry
from agent.workflows.weekly_review import (
    gather_review_data,
    run_weekly_review,
    synthesize_review,
)


class FakeLLM:
    """Deterministic LLM double — returns the configured response or raises."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    async def chat(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


def _patch_llm(monkeypatch, **kwargs):
    fake = FakeLLM(**kwargs)
    monkeypatch.setattr(
        "agent.workflows.weekly_review.OllamaClient", lambda **kw: fake
    )
    return fake


class FakeMemoryBus:
    """Memory bus double — records stores, returns empty highlights."""

    def __init__(self):
        self.stored = []

    async def store(self, *args, **kwargs):
        self.stored.append((args, kwargs))

    def format_for_prompt(self, **kwargs):
        return ""


def _patch_memory(monkeypatch):
    bus = FakeMemoryBus()
    monkeypatch.setattr("memory.memory_bus.get_memory_bus", lambda: bus)
    return bus


# ─── Data gathering ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gather_review_data_returns_all_sections():
    sections = await gather_review_data(days=7)
    assert set(sections.keys()) == {"analytics", "social", "skills", "activity", "memory"}
    assert all(isinstance(v, str) for v in sections.values())


# ─── Synthesis ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesize_review_uses_llm(monkeypatch):
    fake = _patch_llm(monkeypatch, response="# Weekly Review\n\nA solid, productive week with strong job pipeline progress.")
    sections = {"analytics": "Career & revenue:\n  - 5 jobs tracked", "social": "", "skills": "", "activity": "", "memory": ""}
    report = await synthesize_review(sections, days=7)
    assert "solid, productive week" in report
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_synthesize_review_falls_back_when_llm_fails(monkeypatch):
    _patch_llm(monkeypatch, error=RuntimeError("LLM down"))
    sections = {
        "analytics": "Career & revenue:\n  - 5 jobs tracked",
        "social": "",
        "skills": "Skill health:\n  - 12 executions, 91.7% success",
        "activity": "",
        "memory": "",
    }
    report = await synthesize_review(sections, days=7)
    assert "Weekly Review" in report
    assert "5 jobs tracked" in report
    assert "91.7% success" in report
    # Empty sections must not appear
    assert "Social" not in report


@pytest.mark.asyncio
async def test_synthesize_review_fallback_with_no_data(monkeypatch):
    _patch_llm(monkeypatch, error=RuntimeError("LLM down"))
    report = await synthesize_review({}, days=7)
    assert "Weekly Review" in report
    assert "No data gathered this week." in report


# ─── Full run ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_weekly_review_stores_memory_and_notifies(monkeypatch):
    _patch_llm(monkeypatch, response="# Weekly Review\n\nA solid, productive week overall.")
    bus = _patch_memory(monkeypatch)

    notified = {}

    async def fake_send(**kwargs):
        notified.update(kwargs)
        return {}

    monkeypatch.setattr(
        "notifications.manager.notification_manager.send_notification", fake_send
    )

    result = await run_weekly_review(notify=True, days=7)

    assert result["report"].startswith("# Weekly Review")
    assert result["period_days"] == 7
    assert set(result["sections"].keys()) == {"analytics", "social", "skills", "activity", "memory"}
    assert result["notified"] is True
    assert notified.get("title") == "📊 Weekly Review"
    # Report persisted to the memory bus (category 'reviews')
    assert bus.stored, "weekly report should be stored to memory"
    assert bus.stored[0][1].get("category") == "reviews"


@pytest.mark.asyncio
async def test_run_weekly_review_notify_failure_does_not_block(monkeypatch):
    _patch_llm(monkeypatch, response="# Weekly Review\n\nA solid, productive week overall.")
    _patch_memory(monkeypatch)

    async def boom(**kwargs):
        raise RuntimeError("notification channel down")

    monkeypatch.setattr(
        "notifications.manager.notification_manager.send_notification", boom
    )

    result = await run_weekly_review(notify=True, days=7)
    assert result["report"].startswith("# Weekly Review")
    assert result["notified"] is False


# ─── Skill registration ─────────────────────────────────────────────────────


def test_weekly_review_skill_registered():
    reg = SkillRegistry()
    register_agentic_skills(reg)
    skill = reg.get("weekly_review")
    assert skill is not None
    assert skill.handler is not None
    assert skill.category == "workflow"
    assert not skill.critical
