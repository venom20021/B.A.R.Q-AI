"""
BARQ Morning Briefing Agent (W4) — Prompt-Chaining pattern.

Scheduled orchestration (default 08:00) that chains parallel data fetches
into a single synthesized, spoken-ready briefing:

    gather weather ─┐
    gather calendar ─┼─→ LLM synthesize → briefing text
    gather jobs    ─┤
    gather memory  ─┘

Runs via APScheduler (see main.start_scheduler), by voice/API, or as a
``morning_briefing`` skill through the planner.

All data sources are guarded — a failure in any one never blocks the rest.
"""

from __future__ import annotations

import asyncio
from typing import Any

from utils.ollama_client import OllamaClient

BRIEFING_SYSTEM_PROMPT = """You are BARQ's morning briefing synthesizer. Combine the raw
data below into a warm, natural, concise morning briefing (max ~200 words).

Structure:
- One greeting line with the date.
- "Today at a glance" — the single most important items (weather, interviews, deadlines).
- Short bullet highlights for the rest (job matches, scheduled content, memory reminders).
- End with one helpful suggestion or question.

Rules:
- Speak plainly, never robotic. No markdown headers — plain text only.
- If a section has no data, skip it (never invent data)."""


async def _gather_weather() -> str:
    """Fetch weather via the existing get_weather skill (tool-use reuse)."""
    try:
        from database import settings_dao
        city = await settings_dao.get_setting("weather_city") or "London"
        from agent.skill_registry import get_skill_registry
        result = await get_skill_registry().call("get_weather", city=city)
        return str(result).strip()
    except Exception as e:
        print(f"[Briefing] Weather unavailable: {e}")
        return ""


async def _gather_calendar() -> str:
    """Today's scheduled social/content posts."""
    try:
        from social.calendar import ContentCalendar
        posts = await ContentCalendar().get_upcoming_schedule(days=1)
        if not posts:
            return ""
        lines = []
        for p in posts[:5]:
            platform = p.get("platform", "unknown")
            title = (p.get("title") or p.get("description") or "content")[:60]
            when = (p.get("scheduled_at") or "")[:16]
            lines.append(f"  - [{platform}] {title} ({when})")
        return "Scheduled content today:\n" + "\n".join(lines)
    except Exception as e:
        print(f"[Briefing] Calendar unavailable: {e}")
        return ""


async def _gather_jobs() -> str:
    """Pending applications, interviews, and recent matches."""
    try:
        from database import db_connection
        from datetime import date
        today = date.today().isoformat()
        parts: list[str] = []

        row = await db_connection.fetch_one("SELECT COUNT(*) as count FROM job_listings")
        total = row["count"] if row else 0
        if total:
            parts.append(f"{total} jobs tracked")

        interviews = await db_connection.fetch_all(
            "SELECT j.company, a.interview_date FROM applications a "
            "JOIN job_listings j ON a.job_listing_id = j.id "
            "WHERE a.interview_date IS NOT NULL AND a.interview_date >= ? "
            "ORDER BY a.interview_date ASC LIMIT 3", (today,),
        )
        if interviews:
            for row in interviews:
                label = "today" if row["interview_date"] == today else f"on {row['interview_date']}"
                parts.append(f"interview: {row['company']} {label}")

        pending = await db_connection.fetch_one(
            "SELECT COUNT(*) as count FROM applications WHERE status IN ('queued','ready_for_review')"
        )
        if pending and pending["count"]:
            parts.append(f"{pending['count']} applications pending review")

        return "Career:\n" + "\n".join(f"  - {p}" for p in parts) if parts else ""
    except Exception as e:
        print(f"[Briefing] Jobs unavailable: {e}")
        return ""


async def _gather_memory() -> str:
    """Recent memory + active goals from the memory bus."""
    try:
        from memory.memory_bus import get_memory_bus
        bus = get_memory_bus()
        highlights = bus.format_for_prompt(category="preferences") or ""
        goals = bus.format_for_prompt(category="projects") or ""
        combined = (highlights + "\n" + goals).strip()
        return ("Memory highlights:\n" + combined) if combined else ""
    except Exception as e:
        print(f"[Briefing] Memory unavailable: {e}")
        return ""


async def gather_briefing_data() -> dict[str, str]:
    """Fetch all briefing sections in parallel (Orchestrator-Workers)."""
    weather, calendar, jobs, memory = await asyncio.gather(
        _gather_weather(), _gather_calendar(), _gather_jobs(), _gather_memory()
    )
    return {"weather": weather, "calendar": calendar, "jobs": jobs, "memory": memory}


async def synthesize_briefing(sections: dict[str, str]) -> str:
    """Synthesize gathered data into a natural briefing via the LLM."""
    from datetime import datetime
    now = datetime.now().strftime("%A, %B %d, %Y")

    context = f"Date: {now}\n\n"
    for label, value in sections.items():
        if value:
            context += f"{label.upper()}:\n{value}\n\n"

    try:
        llm = OllamaClient(temperature=0.6)
        messages = [
            {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]
        response = await llm.chat(messages)
        return response.strip()
    except Exception as e:
        print(f"[Briefing] Synthesis failed: {e}")
        # Plain fallback (no fabrication — only what we actually gathered)
        lines = [f"Good morning! Here is your briefing for {now}."]
        for label, value in sections.items():
            if value:
                lines.append(f"\n{label.title()}:\n{value}")
        return "\n".join(lines)


async def run_morning_briefing(notify: bool = True) -> dict[str, Any]:
    """Execute the full morning briefing workflow.

    Args:
        notify: Whether to push a desktop notification with the briefing.

    Returns:
        dict with briefing text, section counts, and notification result.
    """
    sections = await gather_briefing_data()
    briefing = await synthesize_briefing(sections)

    result: dict[str, Any] = {
        "briefing": briefing,
        "sections": {k: bool(v) for k, v in sections.items()},
        "notified": False,
    }

    # Store the briefing in memory (category 'briefings') for later recall
    try:
        from memory.memory_bus import get_memory_bus
        await get_memory_bus().store(
            "morning_briefing",
            briefing[:1000],
            category="briefings",
            source="agent",
            ttl_seconds=48 * 3600,
        )
    except Exception as e:
        print(f"[Briefing] Memory store failed: {e}")

    # Log activity
    try:
        from database import analytics_dao
        await analytics_dao.log_activity(
            "system", "morning_briefing",
            f"Morning briefing generated ({len(briefing)} chars)",
        )
    except Exception as e:
        print(f"[Briefing] Activity log failed: {e}")

    # Push a desktop notification so it surfaces even without voice
    if notify:
        try:
            from notifications.manager import notification_manager
            await notification_manager.send_notification(
                title="🌅 Morning Briefing",
                body=briefing[:500],
                priority="normal",
                category="system",
                channel="all",
            )
            result["notified"] = True
        except Exception as e:
            print(f"[Briefing] Notification failed: {e}")

    return result


async def morning_briefing_skill(**kwargs: Any) -> str:
    """Skill handler for the planner/executor."""
    result = await run_morning_briefing(notify=False)
    return result["briefing"]
