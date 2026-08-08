"""
BARQ Agentic Skills — registers the agentic workflow capabilities as planner
skills so the AgentPlanner/AgentExecutor can invoke them.

Registered skills:
  - query_memory        (Tool-Use): read-only SQL over the local memory bus
  - memory_snapshot     (Tool-Use): real-time memory bus state without SQL
  - run_workflow        (Orchestrator/Chaining): run a JSON workflow by name
  - morning_briefing    (Prompt-Chaining, W4)
  - conversation_memory (Orchestrator-Workers, W5)
  - research_to_brain   (Orchestrator-Workers, W6)
  - content_critic      (Evaluator-Optimizer, W7)
  - weekly_review       (Analytics/Self-reflection, W11)

All handlers lazy-import their modules to avoid circular imports.
"""

from __future__ import annotations

from typing import Any, Optional

from .skill_registry import Skill, SkillParameter, get_skill_registry


# ─── Handlers (thin, lazy-import wrappers) ──────────────────────────────────


async def _sql_query_skill(**kwargs: Any) -> str:
    from .sql_tool import run_sql_query
    query = kwargs.get("query", "")
    if not query:
        return "No SQL query provided. Use SELECT / WITH / PRAGMA statements."
    limit = int(kwargs.get("limit", 50) or 50)
    try:
        return await run_sql_query(query, limit=limit)
    except Exception as e:
        return f"SQL query rejected: {e}"


async def _memory_snapshot_skill(**kwargs: Any) -> str:
    from .sql_tool import memory_snapshot
    return await memory_snapshot()


async def _run_workflow_skill(**kwargs: Any) -> str:
    from .workflow_runtime import run_workflow_skill
    return await run_workflow_skill(name=kwargs.get("name", ""), context=kwargs.get("context") or kwargs)


async def _morning_briefing_skill(**kwargs: Any) -> str:
    from .workflows.morning_briefing import morning_briefing_skill
    return await morning_briefing_skill(**kwargs)


async def _conversation_memory_skill(**kwargs: Any) -> str:
    from .workflows.conversation_memory import conversation_memory_skill
    return await conversation_memory_skill(**kwargs)


async def _research_to_brain_skill(**kwargs: Any) -> str:
    from .workflows.research_to_brain import research_to_brain_skill
    return await research_to_brain_skill(**kwargs)


async def _content_critic_skill(**kwargs: Any) -> str:
    from .workflows.content_critic import content_critic_skill
    return await content_critic_skill(**kwargs)


async def _weekly_review_skill(**kwargs: Any) -> str:
    from .workflows.weekly_review import weekly_review_skill
    return await weekly_review_skill(**kwargs)


# ─── Registration ────────────────────────────────────────────────────────────


def register_agentic_skills(registry: Optional[Any] = None) -> Any:
    """Register all agentic workflow skills (idempotent)."""
    reg = registry or get_skill_registry()

    skills: list[Skill] = [
        # ── Tool-Use Pattern (execution-focused) ────────────────────
        Skill(
            name="query_memory",
            description="Execute a read-only SQL query (SELECT/WITH/EXPLAIN/read-only PRAGMA) against BARQ's local SQLite memory bus to fetch real-time state before responding. Use to check stored facts, recent memories, categories, or any memory_entries data.",
            parameters=[
                SkillParameter("query", "string", True, "Read-only SQL SELECT/WITH/PRAGMA statement"),
                SkillParameter("limit", "number", False, "Max rows to return (default 50)"),
            ],
            critical=False,
            category="memory",
            handler=_sql_query_skill,
        ),
        Skill(
            name="memory_snapshot",
            description="Get a compact real-time snapshot of BARQ's memory bus: entry counts per category and recent entries. No SQL needed.",
            parameters=[],
            critical=False,
            category="memory",
            handler=_memory_snapshot_skill,
        ),
        # ── Prompt-Chaining / Orchestrator-Workers ──────────────────
        Skill(
            name="run_workflow",
            description="Run a registered workflow by name (e.g. 'evening_research', 'weather_and_trends'). Optional context dict supplies ${context.*} placeholders. Workflows chain and parallelize other skills.",
            parameters=[
                SkillParameter("name", "string", True, "Registered workflow name"),
                SkillParameter("context", "object", False, "Context values for ${context.*} placeholders"),
            ],
            critical=False,
            category="workflow",
            handler=_run_workflow_skill,
        ),
        Skill(
            name="morning_briefing",
            description="Generate the user's morning briefing: weather, today's scheduled content, pending job applications/interviews, and memory highlights, synthesized into a natural spoken-ready summary.",
            parameters=[],
            critical=False,
            category="workflow",
            handler=_morning_briefing_skill,
        ),
        Skill(
            name="conversation_memory",
            description="Extract durable memories (action items, facts, entities, summary) from a conversation turn and store them in BARQ's memory bus.",
            parameters=[
                SkillParameter("user_text", "string", True, "The user's message from the conversation"),
                SkillParameter("ai_text", "string", False, "The assistant's reply (optional)"),
            ],
            critical=False,
            category="memory",
            handler=_conversation_memory_skill,
        ),
        Skill(
            name="research_to_brain",
            description="Extract knowledge triplets from a research report into BARQ's knowledge graph so research compounds into long-term memory.",
            parameters=[
                SkillParameter("topic", "string", True, "The research topic"),
                SkillParameter("report", "string", True, "The research report text"),
            ],
            critical=False,
            category="research",
            handler=_research_to_brain_skill,
        ),
        # ── Evaluator-Optimizer Pattern (quality control) ───────────
        Skill(
            name="content_critic",
            description="Quality-gate a social media draft: a critic LLM scores it against the topic and platform rules; below the threshold it is revised in a loop until it passes. Returns the final approved draft.",
            parameters=[
                SkillParameter("draft", "string", True, "The draft script/post to critique"),
                SkillParameter("topic", "string", False, "The topic the draft covers"),
                SkillParameter("platform", "string", False, "Platform: linkedin_post, twitter_thread, tiktok_short, youtube_shorts, instagram_reel, blog_post"),
                SkillParameter("min_score", "number", False, "Quality gate (0-100, default 80)"),
            ],
            critical=False,
            category="content",
            handler=_content_critic_skill,
        ),
        # ── Analytics / Self-reflection ────────────────────────────
        Skill(
            name="weekly_review",
            description="Generate the user's weekly review report: career funnel, social performance, revenue, skill success rates, activity log, and memory highlights synthesized into a markdown summary with actionable recommendations.",
            parameters=[
                SkillParameter("days", "number", False, "Review period in days (default 7)"),
            ],
            critical=False,
            category="workflow",
            handler=_weekly_review_skill,
        ),
    ]

    for skill in skills:
        try:
            reg.register(skill)
        except ValueError:
            pass  # already registered

    return reg


# Auto-register on import (mirrors register_builtin_skills behavior)
register_agentic_skills()
