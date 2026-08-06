"""
BARQ Feature Bridge — connects the voice/audio pipeline to every BARQ feature.

The voice function registry (``voice/function_executor.py``) historically only
exposed OS / browser / vision / media helpers. This module adds a generic
bridge so spoken commands can reach *every* BARQ feature:

- ``barq_api`` — call any BARQ backend HTTP endpoint (jobs, social, memory,
  brain, workflows, notifications, analytics, settings, knowledge, ...).
- ``barq_skills_list`` — discover which agent skills are registered.
- ``barq_skill`` — invoke any registered agent skill by name.
- Curated convenience wrappers for the most common voice intents
  (remember/recall memory, brain summary, notify, job matches, social trends,
  workflow run/status, briefing, weekly review, analytics).

All functions are **synchronous** because the voice executor runs registry
functions via ``asyncio.to_thread``. Each returns a dict with a ``status`` key
(``"success"`` / ``"error"``) matching the rest of the voice registry.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

# ─── Low-level self-HTTP dispatcher ─────────────────────────────────────


def _barq_base_url() -> str:
    """Build the base URL of BARQ's own backend from config settings."""
    from config import get_settings

    settings = get_settings()
    return f"http://{settings.host}:{settings.port}"


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform a synchronous HTTP call to BARQ's own backend.

    Returns a dict with a ``status`` key — never raises.
    """
    import httpx

    url = _barq_base_url() + path
    try:
        with httpx.Client(timeout=15.0) as client:
            if method.upper() == "GET":
                resp = client.get(url, params=payload or {})
            else:
                resp = client.post(url, json=payload or {})
        try:
            data: Any = resp.json()
        except Exception:
            data = resp.text[:2000]
        if resp.status_code >= 400:
            detail = data.get("detail", data) if isinstance(data, dict) else data
            return {"status": "error", "detail": f"HTTP {resp.status_code}: {detail}"}
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "detail": f"BARQ backend unreachable: {e}"}


def _run_coro(coro: Any) -> Any:
    """Run a coroutine synchronously from a worker-thread context."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception:
        return asyncio.run(coro)


# ─── Generic dispatcher ──────────────────────────────────────────────────


def barq_api(method: str = "GET", path: str = "/", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call any BARQ feature endpoint by method + path.

    Examples:
        barq_api("GET", "/jobs/matches")
        barq_api("POST", "/agent/briefing/run", {"notify": True})

    Args:
        method: HTTP method — "GET" or "POST".
        path: Backend path (e.g. "/jobs/matches", "/social/trends").
        payload: For GET, query params. For POST, the JSON body.
    """
    method = (method or "GET").upper()
    if method not in ("GET", "POST"):
        return {"status": "error", "detail": "method must be 'GET' or 'POST'"}
    if not path.startswith("/"):
        path = "/" + path
    return _request(method, path, payload or {})


# ─── Skill Registry bridge ───────────────────────────────────────────────


def barq_skills_list(category: str = "") -> dict[str, Any]:
    """List all registered agent skills (optionally filtered by category)."""
    try:
        from agent.skill_registry import get_skill_registry

        registry = get_skill_registry()
        skills = [
            {"name": s.name, "description": s.description, "category": s.category}
            for s in registry.list(category or None)
        ]
        return {"status": "success", "data": {"skills": skills, "count": len(skills)}}
    except Exception as e:
        return {"status": "error", "detail": f"Failed to list skills: {e}"}


def barq_skill(name: str, params: str = "") -> dict[str, Any]:
    """Invoke any registered agent skill by name.

    Args:
        name: The skill name (see ``barq_skills_list`` for options).
        params: Optional JSON object string of keyword arguments,
                e.g. '{"query": "AI news"}'.
    """
    if not name:
        return {"status": "error", "detail": "Skill name is required."}
    try:
        from agent.skill_registry import get_skill_registry

        registry = get_skill_registry()
        if registry.get(name) is None:
            return {
                "status": "error",
                "detail": f"Unknown skill '{name}'. Use barq_skills_list to see available skills.",
            }

        kwargs: dict[str, Any] = {}
        if params:
            try:
                parsed = json.loads(params)
                if isinstance(parsed, dict):
                    kwargs = parsed
                else:
                    return {"status": "error", "detail": "params must be a JSON object string."}
            except json.JSONDecodeError:
                return {"status": "error", "detail": "params must be valid JSON, e.g. '{\"query\": \"AI news\"}'"}

        result = _run_coro(registry.call(name, **kwargs))
        return {"status": "success", "detail": str(result)[:2000]}
    except Exception as e:
        return {"status": "error", "detail": f"Skill '{name}' failed: {e}"}


# ─── Curated convenience wrappers ────────────────────────────────────────


def barq_remember(key: str, value: str, category: str = "general") -> dict[str, Any]:
    """Store a fact in BARQ's long-term memory.

    Args:
        key: Short unique name for the memory (e.g. 'user_birthday').
        value: The fact to remember.
        category: Optional category (default 'general').
    """
    if not key or not value:
        return {"status": "error", "detail": "Both 'key' and 'value' are required."}
    return _request("POST", "/memory/memory", {"key": key, "value": value, "category": category})


def barq_recall(query: str, limit: int = 10) -> dict[str, Any]:
    """Search BARQ's long-term memory for stored facts."""
    if not query:
        return {"status": "error", "detail": "A search 'query' is required."}
    return _request("GET", "/memory/memory/search", {"query": query, "limit": limit})


def barq_brain_summary() -> dict[str, Any]:
    """Get a summary of the knowledge brain (nodes/connections)."""
    return _request("GET", "/api/brain/list")


def barq_notify(
    title: str,
    body: str,
    priority: str = "normal",
    channel: str = "all",
    category: str = "general",
) -> dict[str, Any]:
    """Send a notification (telegram / email / desktop).

    Args:
        title: Notification title.
        body: Notification body text.
        priority: low, normal, high, or urgent.
        channel: telegram, email, desktop, or all.
        category: general, job_match, application, content, analytics, error, system.
    """
    if not title or not body:
        return {"status": "error", "detail": "Both 'title' and 'body' are required."}
    return _request(
        "POST",
        "/notifications/send",
        {
            "title": title,
            "body": body,
            "priority": priority,
            "channel": channel,
            "category": category,
        },
    )


def barq_job_matches(min_score: float = 3.0, limit: int = 20) -> dict[str, Any]:
    """Get the current job matches from the job scanner."""
    return _request("GET", "/jobs/matches", {"min_score": min_score, "limit": limit})


def barq_social_trends() -> dict[str, Any]:
    """Get the current social media trending topics."""
    return _request("GET", "/social/trends")


def barq_workflow_run(name: str, context: dict[str, Any] | None = None, background: bool = False) -> dict[str, Any]:
    """Run a registered agent workflow by name.

    Args:
        name: Workflow name (e.g. 'morning_briefing', 'weekly_review').
        context: Optional dict of inputs the workflow expects.
        background: Run asynchronously (returns immediately) if True.
    """
    if not name:
        return {"status": "error", "detail": "A workflow 'name' is required."}
    return _request(
        "POST",
        f"/agent/workflows/{name}/run",
        {"context": context or {}, "background": background},
    )


def barq_workflow_status(run_id: str) -> dict[str, Any]:
    """Get the status of a workflow run by its run_id."""
    if not run_id:
        return {"status": "error", "detail": "A 'run_id' is required."}
    return _request("GET", f"/agent/workflows/runs/{run_id}")


def barq_briefing(notify: bool = False) -> dict[str, Any]:
    """Generate the morning briefing report."""
    return _request("POST", "/agent/briefing/run", {"notify": notify})


def barq_weekly_review(notify: bool = False, days: int = 7) -> dict[str, Any]:
    """Generate the weekly review report (analytics + skill rates + memory)."""
    return _request("POST", "/agent/review/weekly", {"notify": notify, "days": days})


def barq_analytics(kind: str = "activity", limit: int = 50) -> dict[str, Any]:
    """Get an analytics snapshot.

    Args:
        kind: activity (default), career, social, or revenue.
        limit: Max rows for activity.
    """
    kind = (kind or "activity").lower()
    if kind in ("career", "social", "revenue"):
        return _request("GET", f"/analytics/{kind}")
    return _request("GET", "/analytics/activity", {"limit": limit})


# ─── Registry + Schema exports ───────────────────────────────────────────

FEATURE_FUNCTIONS: dict[str, Any] = {
    "barq_api": barq_api,
    "barq_skills_list": barq_skills_list,
    "barq_skill": barq_skill,
    "barq_remember": barq_remember,
    "barq_recall": barq_recall,
    "barq_brain_summary": barq_brain_summary,
    "barq_notify": barq_notify,
    "barq_job_matches": barq_job_matches,
    "barq_social_trends": barq_social_trends,
    "barq_workflow_run": barq_workflow_run,
    "barq_workflow_status": barq_workflow_status,
    "barq_briefing": barq_briefing,
    "barq_weekly_review": barq_weekly_review,
    "barq_analytics": barq_analytics,
}

FEATURE_SCHEMAS: list[dict] = [
    {
        "name": "barq_api",
        "description": "Call any BARQ feature by method and path. Use for jobs, social, memory, brain, workflows, notifications, analytics, settings, or any other backend endpoint. Examples: GET /jobs/matches, POST /agent/briefing/run.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "HTTP method: 'GET' or 'POST' (default GET)."},
                "path": {"type": "string", "description": "Backend path, e.g. '/jobs/matches' or '/social/trends'."},
                "payload": {"type": "object", "description": "Optional. For GET: query params. For POST: JSON body."},
            },
        },
    },
    {
        "name": "barq_skills_list",
        "description": "List all registered agent skills (web search, deep research, code helper, dev agent, recruitment, etc.) so you know what skills are available.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional category filter (web, system, files, research, developer, recruitment, social, communications)."},
            },
        },
    },
    {
        "name": "barq_skill",
        "description": "Invoke any registered agent skill by name, e.g. 'web_search', 'deep_research', 'code_helper', 'dev_agent'. Pass arguments as a JSON object string.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name (see barq_skills_list)."},
                "params": {"type": "string", "description": "JSON object string of keyword arguments, e.g. '{\"query\": \"AI news\"}'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "barq_remember",
        "description": "Store a fact in BARQ's long-term memory (key-value). Use when the user asks to remember something.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short unique name, e.g. 'user_birthday'."},
                "value": {"type": "string", "description": "The fact to remember."},
                "category": {"type": "string", "description": "Optional category (default 'general')."},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "barq_recall",
        "description": "Search BARQ's long-term memory for stored facts matching a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."},
                "limit": {"type": "integer", "description": "Max results (default 10)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "barq_brain_summary",
        "description": "Get a summary of the knowledge brain (concepts and connections).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "barq_notify",
        "description": "Send a notification through BARQ (telegram, email, or desktop).",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title."},
                "body": {"type": "string", "description": "Notification body text."},
                "priority": {"type": "string", "description": "low, normal, high, or urgent."},
                "channel": {"type": "string", "description": "telegram, email, desktop, or all."},
                "category": {"type": "string", "description": "general, job_match, application, content, analytics, error, system."},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "barq_job_matches",
        "description": "Get the current job matches from BARQ's job scanner.",
        "parameters": {
            "type": "object",
            "properties": {
                "min_score": {"type": "number", "description": "Minimum match score (default 3.0)."},
                "limit": {"type": "integer", "description": "Max matches (default 20)."},
            },
        },
    },
    {
        "name": "barq_social_trends",
        "description": "Get the current social media trending topics.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "barq_workflow_run",
        "description": "Run a registered agent workflow by name (e.g. 'morning_briefing', 'weekly_review').",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workflow name."},
                "context": {"type": "object", "description": "Optional dict of inputs the workflow expects."},
                "background": {"type": "boolean", "description": "Run asynchronously if True (default False)."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "barq_workflow_status",
        "description": "Get the status of a workflow run by its run_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "The run id returned by barq_workflow_run."},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "barq_briefing",
        "description": "Generate the morning briefing report.",
        "parameters": {
            "type": "object",
            "properties": {
                "notify": {"type": "boolean", "description": "Send the briefing via notification channels."},
            },
        },
    },
    {
        "name": "barq_weekly_review",
        "description": "Generate the weekly review report (analytics + skill success rates + memory).",
        "parameters": {
            "type": "object",
            "properties": {
                "notify": {"type": "boolean", "description": "Send the review via notification channels."},
                "days": {"type": "integer", "description": "Number of days to review (default 7)."},
            },
        },
    },
    {
        "name": "barq_analytics",
        "description": "Get an analytics snapshot: activity, career, social, or revenue.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "activity (default), career, social, or revenue."},
                "limit": {"type": "integer", "description": "Max rows for activity (default 50)."},
            },
        },
    },
]
