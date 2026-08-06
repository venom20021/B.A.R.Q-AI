"""
BARQ Weekly Review Agent (W11) — analytics + skill success rates + memory → weekly report.

Scheduled weekly (default Sunday 09:00, see config.weekly_review_*) or on demand.
Chains parallel data gathering into a single synthesized markdown report:

    analytics ─┐
    social    ─┼─→ LLM synthesize → weekly report (memory + notify)
    skills    ─┤
    activity  ─┤
    memory    ─┘

Runs via APScheduler (see main.start_scheduler), by voice/API, or as a
``weekly_review`` skill through the planner.

All data sources are guarded — a failure in any one never blocks the rest.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from utils.ollama_client import OllamaClient

WEEKLY_REVIEW_SYSTEM_PROMPT = """You are BARQ's weekly review synthesizer. Turn the raw weekly
data below into a concise markdown report (max ~350 words) the user can skim.

Structure:
# Weekly Review
## Week at a Glance — 2-3 sentence executive summary of the week.
## Career Pulse — funnel movement (scans -> matches -> applications -> interviews -> offers).
## Content & Social — what performed, per platform if present.
## Revenue — totals and any notable sources.
## Agent Health — skill execution stats: success rates, problem skills, top errors.
## Memory & Reminders — anything worth acting on from memory highlights.
## Recommendations — 2-4 concrete, actionable suggestions for next week.

Rules:
- Only use data provided. Never invent numbers, platforms, or facts.
- If a section has no data, write a short "No data this week." line instead of inventing.
- Be specific and useful, not generic."""


async def _gather_analytics(days: int) -> str:
    """Career funnel + revenue for the period."""
    try:
        from database import analytics_dao
        funnel = await analytics_dao.compute_funnel_summary()
        revenue = await analytics_dao.get_total_revenue(days=days)

        lines: list[str] = []
        if funnel and any(funnel.values()):
            labels = (
                ("jobs_scanned", "jobs tracked"),
                ("matches_found", "matches found"),
                ("applications_sent", "applications sent"),
                ("interviews_scheduled", "interviews scheduled"),
                ("offers_received", "offers received"),
            )
            for key, label in labels:
                val = funnel.get(key, 0) or 0
                if val:
                    lines.append(f"  - {val} {label}")
        if revenue:
            lines.append(f"  - ${float(revenue):,.2f} revenue ({days}d)")
        return ("Career & revenue:\n" + "\n".join(lines)) if lines else ""
    except Exception as e:
        print(f"[WeeklyReview] Analytics unavailable: {e}")
        return ""


async def _gather_social() -> str:
    """Latest per-platform social snapshots."""
    try:
        from database import analytics_dao
        snapshots = await analytics_dao.get_latest_social_snapshots()
        if not snapshots:
            return ""
        lines = []
        for s in snapshots:
            platform = s.get("platform", "unknown")
            lines.append(
                f"  - {platform}: {s.get('followers', 0)} followers, "
                f"{s.get('total_views', 0)} views, {s.get('total_engagement', 0)} engagement, "
                f"${float(s.get('revenue', 0) or 0):,.2f} revenue"
            )
        return "Social:\n" + "\n".join(lines)
    except Exception as e:
        print(f"[WeeklyReview] Social unavailable: {e}")
        return ""


async def _gather_skill_stats() -> str:
    """Skill success rates from the SkillRegistry analytics."""
    try:
        from agent.skill_registry import get_skill_registry
        reg = get_skill_registry()
        stats = reg.get_all_stats()
        if not stats:
            return ""
        summary = reg.get_stats_summary()
        lines = [
            f"  - {summary.get('total_executions', 0)} total executions, "
            f"{summary.get('avg_success_rate_pct', 0)}% average success rate, "
            f"{summary.get('total_errors', 0)} errors across {summary.get('active_skills', 0)} skill(s)"
        ]
        for s in stats[:8]:
            flag = " (failing)" if s["error_count"] > 0 else ""
            lines.append(
                f"  - {s['skill']}: {s['total_calls']} calls, {s['success_rate_pct']}% success{flag}"
            )
        if summary.get("top_errors"):
            top = "; ".join(f"{k} (x{v})" for k, v in list(summary["top_errors"].items())[:3])
            lines.append(f"  - top errors: {top}")
        return "Skill health:\n" + "\n".join(lines)
    except Exception as e:
        print(f"[WeeklyReview] Skill stats unavailable: {e}")
        return ""


async def _gather_activity(days: int) -> str:
    """Activity log for the last N days, grouped by type."""
    try:
        from database import analytics_dao
        activities = await analytics_dao.get_recent_activity(limit=500)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = [a for a in activities if (a.get("created_at") or "")[:10] >= cutoff]
        if not recent:
            return ""

        counts: dict[str, int] = {}
        errors: list[str] = []
        for a in recent:
            atype = a.get("type") or "other"
            counts[atype] = counts.get(atype, 0) + 1
            if a.get("severity") == "error" or atype == "error":
                errors.append((a.get("action") or a.get("description") or "")[:80])

        lines = [f"  - {len(recent)} logged events in the last {days} days"]
        for atype, count in sorted(counts.items(), key=lambda x: -x[1]):
            lines.append(f"  - {atype}: {count}")
        if errors:
            lines.append("  - errors: " + "; ".join(errors[:3]))
        return "Activity:\n" + "\n".join(lines)
    except Exception as e:
        print(f"[WeeklyReview] Activity unavailable: {e}")
        return ""


async def _gather_memory() -> str:
    """Memory highlights (preferences + projects) from the memory bus."""
    try:
        from memory.memory_bus import get_memory_bus
        bus = get_memory_bus()
        combined = (
            (bus.format_for_prompt(category="preferences") or "")
            + "\n"
            + (bus.format_for_prompt(category="projects") or "")
        ).strip()
        return ("Memory highlights:\n" + combined) if combined else ""
    except Exception as e:
        print(f"[WeeklyReview] Memory unavailable: {e}")
        return ""


async def gather_review_data(days: int = 7) -> dict[str, str]:
    """Fetch all weekly review sections in parallel (Orchestrator-Workers)."""
    analytics, social, skills, activity, memory = await asyncio.gather(
        _gather_analytics(days),
        _gather_social(),
        _gather_skill_stats(),
        _gather_activity(days),
        _gather_memory(),
    )
    return {
        "analytics": analytics,
        "social": social,
        "skills": skills,
        "activity": activity,
        "memory": memory,
    }


async def synthesize_review(sections: dict[str, str], days: int = 7) -> str:
    """Synthesize gathered data into a markdown weekly report via the LLM."""
    end = datetime.now()
    start = end - timedelta(days=days)
    period = f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"

    context = f"Week: {period}\n\n"
    for label, value in sections.items():
        if value:
            context += f"{label.upper()}:\n{value}\n\n"

    try:
        llm = OllamaClient(temperature=0.5)
        messages = [
            {"role": "system", "content": WEEKLY_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]
        response = await llm.chat(messages)
        if response and len(response.strip()) > 40:
            return response.strip()
    except Exception as e:
        print(f"[WeeklyReview] Synthesis failed: {e}")

    # Plain fallback (no fabrication — only what we actually gathered)
    if not any(sections.values()):
        return f"# Weekly Review ({period})\n\nNo data gathered this week."
    lines = [f"# Weekly Review ({period})", ""]
    for label, value in sections.items():
        if value:
            lines.append(f"## {label.title()}")
            lines.append(value)
            lines.append("")
    return "\n".join(lines).strip()


async def run_weekly_review(notify: bool = True, days: int = 7) -> dict[str, Any]:
    """Execute the full weekly review workflow.

    Args:
        notify: Whether to push a desktop/telegram notification with the report.
        days: Review period in days (default 7).

    Returns:
        dict with the report, period, section presence, and notification result.
    """
    sections = await gather_review_data(days=days)
    report = await synthesize_review(sections, days=days)

    result: dict[str, Any] = {
        "report": report,
        "period_days": days,
        "sections": {k: bool(v) for k, v in sections.items()},
        "notified": False,
    }

    # Store the report in memory (category 'reviews') for later recall
    try:
        from memory.memory_bus import get_memory_bus
        await get_memory_bus().store(
            "weekly_review",
            report[:2000],
            category="reviews",
            source="agent",
            ttl_seconds=10 * 24 * 3600,
        )
    except Exception as e:
        print(f"[WeeklyReview] Memory store failed: {e}")

    # Log activity
    try:
        from database import analytics_dao
        await analytics_dao.log_activity(
            "analytics", "weekly_review",
            f"Weekly review generated ({len(report)} chars)",
        )
    except Exception as e:
        print(f"[WeeklyReview] Activity log failed: {e}")

    # Push a notification so it surfaces without voice
    if notify:
        try:
            from notifications.manager import notification_manager
            await notification_manager.send_notification(
                title="📊 Weekly Review",
                body=report[:500],
                priority="normal",
                category="analytics",
                channel="all",
            )
            result["notified"] = True
        except Exception as e:
            print(f"[WeeklyReview] Notification failed: {e}")

    return result


async def weekly_review_skill(**kwargs: Any) -> str:
    """Skill handler for the planner/executor."""
    days = int(kwargs.get("days", 7) or 7)
    result = await run_weekly_review(notify=False, days=days)
    return result["report"]
