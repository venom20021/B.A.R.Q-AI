"""
Tests for the BARQ Feature Bridge (voice/feature_bridge.py).

The feature bridge gives the voice/audio pipeline access to every BARQ feature:
generic self-HTTP dispatch (barq_api), the SkillRegistry bridge (barq_skill),
and curated convenience wrappers (memory, notifications, jobs, social,
workflows, briefing, analytics).

These tests are pure unit tests — they mock the HTTP layer so no backend
server is required.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Ensure python directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import voice.feature_bridge as fb
from voice.feature_bridge import (
    FEATURE_FUNCTIONS,
    FEATURE_SCHEMAS,
    barq_analytics,
    barq_api,
    barq_brain_summary,
    barq_briefing,
    barq_job_matches,
    barq_notify,
    barq_recall,
    barq_remember,
    barq_skill,
    barq_skills_list,
    barq_social_trends,
    barq_weekly_review,
    barq_workflow_run,
    barq_workflow_status,
)


# ─── Schema / Registry consistency ───────────────────────────────────────


def test_feature_schemas_match_feature_functions():
    """Every feature function must have a schema, and vice versa."""
    schema_names = {s["name"] for s in FEATURE_SCHEMAS}
    function_names = set(FEATURE_FUNCTIONS.keys())
    assert schema_names == function_names, (
        f"Schema/function mismatch: schemas-only={schema_names - function_names} "
        f"functions-only={function_names - schema_names}"
    )


def test_feature_schemas_have_required_structure():
    """Each schema needs a name, description, and parameters object."""
    for schema in FEATURE_SCHEMAS:
        assert schema["name"].startswith("barq_")
        assert schema["description"]
        assert schema["parameters"]["type"] == "object"
        assert isinstance(schema["parameters"]["properties"], dict)


def test_feature_bridge_registered_in_function_executor():
    """The bridge functions must be merged into the voice FUNCTION_REGISTRY."""
    from voice.function_executor import FUNCTION_REGISTRY, get_function_schemas

    for name in FEATURE_FUNCTIONS:
        assert name in FUNCTION_REGISTRY, f"{name} missing from FUNCTION_REGISTRY"

    schema_names = [s["name"] for s in get_function_schemas()]
    for name in FEATURE_FUNCTIONS:
        assert name in schema_names, f"{name} missing from get_function_schemas()"


# ─── barq_api (generic dispatcher) ───────────────────────────────────────


@patch("voice.feature_bridge._request")
def test_barq_api_get_dispatches_correctly(mock_request):
    mock_request.return_value = {"status": "success", "data": {"matches": []}}
    result = barq_api("GET", "/jobs/matches", {"limit": 5})
    assert result["status"] == "success"
    mock_request.assert_called_once_with("GET", "/jobs/matches", {"limit": 5})


@patch("voice.feature_bridge._request")
def test_barq_api_post_dispatches_correctly(mock_request):
    mock_request.return_value = {"status": "success", "data": {"run_id": "r1"}}
    result = barq_api("POST", "/agent/briefing/run", {"notify": True})
    assert result["status"] == "success"
    mock_request.assert_called_once_with("POST", "/agent/briefing/run", {"notify": True})


def test_barq_api_normalizes_path():
    with patch("voice.feature_bridge._request", return_value={"status": "success"}) as mock_request:
        barq_api("GET", "jobs/matches")
        path = mock_request.call_args[0][1]
        assert path == "/jobs/matches"


def test_barq_api_rejects_unsupported_method():
    result = barq_api("DELETE", "/jobs/matches")
    assert result["status"] == "error"
    assert "method" in result["detail"].lower()


# ─── barq_skill (SkillRegistry bridge) ───────────────────────────────────


def test_barq_skill_requires_name():
    result = barq_skill("")
    assert result["status"] == "error"
    assert "name" in result["detail"].lower()


@patch("voice.feature_bridge._run_coro", new_callable=lambda: lambda coro: "research report text")
@patch("agent.skill_registry.get_skill_registry")
def test_barq_skill_invokes_registry(mock_registry, mock_run_coro):
    fake_skill = type("Skill", (), {"name": "deep_research"})
    fake_registry = type(
        "Registry",
        (),
        {
            "get": lambda n: fake_skill,
            "call": lambda name, **kw: "research report text",
        },
    )
    mock_registry.return_value = fake_registry

    result = barq_skill("deep_research", '{"topic": "AI"}')
    assert result["status"] == "success"
    assert "research report" in result["detail"]


@patch("agent.skill_registry.get_skill_registry")
def test_barq_skill_unknown_skill(mock_registry):
    fake_registry = type("Registry", (), {"get": lambda n: None})
    mock_registry.return_value = fake_registry

    result = barq_skill("nonexistent_skill")
    assert result["status"] == "error"
    assert "Unknown skill" in result["detail"]


def test_barq_skill_rejects_invalid_json_params():
    with patch("voice.feature_bridge._run_coro") as mock_run_coro:
        result = barq_skill("web_search", "not-json{")
        assert result["status"] == "error"
        mock_run_coro.assert_not_called()


def test_barq_skills_list_returns_registered_skills():
    fake_skill = type(
        "Skill",
        (),
        {
            "name": "web_search",
            "description": "Search the web",
            "category": "web",
        },
    )
    fake_registry = type("Registry", (), {"list": lambda self, cat=None: [fake_skill]})
    with patch("agent.skill_registry.get_skill_registry", return_value=fake_registry):
        result = barq_skills_list()
    assert result["status"] == "success"
    assert result["data"]["count"] == 1
    assert result["data"]["skills"][0]["name"] == "web_search"


# ─── Curated wrappers ────────────────────────────────────────────────────


@patch("voice.feature_bridge._request")
def test_barq_remember(mock_request):
    mock_request.return_value = {"status": "stored", "key": "k"}
    result = barq_remember("user_birthday", "Jan 1")
    assert result["status"] == "stored"
    mock_request.assert_called_once_with(
        "POST", "/memory/memory", {"key": "user_birthday", "value": "Jan 1", "category": "general"}
    )


def test_barq_remember_requires_fields():
    assert barq_remember("", "v")["status"] == "error"
    assert barq_remember("k", "")["status"] == "error"


@patch("voice.feature_bridge._request")
def test_barq_recall(mock_request):
    mock_request.return_value = {"status": "success", "results": []}
    result = barq_recall("birthday")
    mock_request.assert_called_once_with(
        "GET", "/memory/memory/search", {"query": "birthday", "limit": 10}
    )
    assert result["status"] == "success"


def test_barq_recall_requires_query():
    assert barq_recall("")["status"] == "error"


@patch("voice.feature_bridge._request")
def test_barq_notify(mock_request):
    mock_request.return_value = {"status": "success", "success": True}
    result = barq_notify("Title", "Body", priority="high", channel="telegram")
    assert result["status"] == "success"
    kwargs = mock_request.call_args[0][2]
    assert kwargs["title"] == "Title"
    assert kwargs["priority"] == "high"
    assert kwargs["channel"] == "telegram"


def test_barq_notify_requires_fields():
    assert barq_notify("", "body")["status"] == "error"
    assert barq_notify("title", "")["status"] == "error"


@patch("voice.feature_bridge._request")
def test_barq_job_matches(mock_request):
    mock_request.return_value = {"status": "success", "matches": []}
    result = barq_job_matches(min_score=4.0, limit=5)
    mock_request.assert_called_once_with("GET", "/jobs/matches", {"min_score": 4.0, "limit": 5})
    assert result["status"] == "success"


@patch("voice.feature_bridge._request")
def test_barq_social_trends(mock_request):
    mock_request.return_value = {"status": "success", "trends": []}
    result = barq_social_trends()
    mock_request.assert_called_once_with("GET", "/social/trends")
    assert result["status"] == "success"


@patch("voice.feature_bridge._request")
def test_barq_workflow_run(mock_request):
    mock_request.return_value = {"status": "success", "run_id": "w1"}
    result = barq_workflow_run("weekly_review", {"days": 7}, background=True)
    mock_request.assert_called_once_with(
        "POST", "/agent/workflows/weekly_review/run", {"context": {"days": 7}, "background": True}
    )
    assert result["status"] == "success"


def test_barq_workflow_run_requires_name():
    assert barq_workflow_run("")["status"] == "error"


@patch("voice.feature_bridge._request")
def test_barq_workflow_status(mock_request):
    mock_request.return_value = {"status": "success", "state": "completed"}
    result = barq_workflow_status("w1")
    mock_request.assert_called_once_with("GET", "/agent/workflows/runs/w1")
    assert result["status"] == "success"


def test_barq_workflow_status_requires_run_id():
    assert barq_workflow_status("")["status"] == "error"


@patch("voice.feature_bridge._request")
def test_barq_briefing(mock_request):
    mock_request.return_value = {"status": "success", "briefing": "..."}
    result = barq_briefing(notify=True)
    mock_request.assert_called_once_with("POST", "/agent/briefing/run", {"notify": True})
    assert result["status"] == "success"


@patch("voice.feature_bridge._request")
def test_barq_weekly_review(mock_request):
    mock_request.return_value = {"status": "success"}
    result = barq_weekly_review(notify=False, days=14)
    mock_request.assert_called_once_with(
        "POST", "/agent/review/weekly", {"notify": False, "days": 14}
    )
    assert result["status"] == "success"


@patch("voice.feature_bridge._request")
def test_barq_analytics_activity(mock_request):
    mock_request.return_value = {"status": "success", "activity": []}
    result = barq_analytics("activity", limit=10)
    mock_request.assert_called_once_with("GET", "/analytics/activity", {"limit": 10})
    assert result["status"] == "success"


@patch("voice.feature_bridge._request")
def test_barq_analytics_career(mock_request):
    mock_request.return_value = {"status": "success"}
    result = barq_analytics("career")
    mock_request.assert_called_once_with("GET", "/analytics/career")
    assert result["status"] == "success"


# ─── Error handling ──────────────────────────────────────────────────────


@patch("voice.feature_bridge._request")
def test_request_error_propagates_as_status(mock_request):
    """Errors from the backend should surface as error status dicts, not exceptions."""
    mock_request.return_value = {"status": "error", "detail": "HTTP 500: boom"}
    result = barq_social_trends()
    assert result["status"] == "error"
    assert "boom" in result["detail"]


@patch("voice.feature_bridge._barq_base_url", return_value="http://127.0.0.1:8956")
def test_request_exception_handled(mock_base_url):
    """Unreachable backend must not raise out of the bridge."""
    with patch("httpx.Client", side_effect=Exception("connection refused")):
        result = barq_api("GET", "/jobs/matches")
    assert result["status"] == "error"
    assert "unreachable" in result["detail"].lower()
