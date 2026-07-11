"""Tests for the BARQ Agent Planner.

Tests the agent_planner.py module's create_plan() and replan() functions.
The LLM (OllamaClient) is mocked to return controlled JSON responses.
"""

import json
from unittest.mock import AsyncMock, patch

from agent.agent_planner import _fallback_plan, create_plan, replan

# ─── Fixtures ──────────────────────────────────────────────────────────────

VALID_PLAN_JSON = json.dumps({
    "goal": "Research quantum computing",
    "steps": [
        {
            "step": 1,
            "tool": "web_search",
            "description": "Search for quantum computing basics",
            "parameters": {"query": "quantum computing basics"},
            "critical": True,
        },
        {
            "step": 2,
            "tool": "create_file",
            "description": "Save research to file",
            "parameters": {"path": "/tmp/quantum.txt", "content": ""},
            "critical": True,
        },
    ],
})


# ─── _fallback_plan ────────────────────────────────────────────────────────

class TestFallbackPlan:
    """Tests for the synchronous fallback plan generator."""

    def test_returns_dict_with_goal(self):
        plan = _fallback_plan("test goal")
        assert plan["goal"] == "test goal"

    def test_returns_single_step(self):
        plan = _fallback_plan("test goal")
        assert len(plan["steps"]) == 1

    def test_step_uses_web_search(self):
        plan = _fallback_plan("test goal")
        assert plan["steps"][0]["tool"] == "web_search"

    def test_step_is_critical(self):
        plan = _fallback_plan("test goal")
        assert plan["steps"][0]["critical"] is True

    def test_step_contains_goal_in_description(self):
        plan = _fallback_plan("custom goal")
        assert "custom goal" in plan["steps"][0]["description"]


# ─── create_plan ───────────────────────────────────────────────────────────

class TestCreatePlan:
    """Tests for the async create_plan() function with mocked LLM."""

    @patch("agent.agent_planner.OllamaClient")
    async def test_valid_plan_returned(self, mock_ollama):
        """A valid JSON response should be parsed and returned."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=VALID_PLAN_JSON)

        plan = await create_plan("Research quantum computing")
        assert plan["goal"] == "Research quantum computing"
        assert len(plan["steps"]) == 2
        assert plan["steps"][0]["tool"] == "web_search"

    @patch("agent.agent_planner.OllamaClient")
    async def test_markdown_code_fence_stripped(self, mock_ollama):
        """Markdown ```json fences around the JSON should be stripped."""
        fenced = f"```json\n{VALID_PLAN_JSON}\n```"
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=fenced)

        plan = await create_plan("Research")
        assert len(plan["steps"]) == 2

    @patch("agent.agent_planner.OllamaClient")
    async def test_backtick_fence_stripped(self, mock_ollama):
        """Plain ``` fences should also be stripped."""
        fenced = f"```\n{VALID_PLAN_JSON}\n```"
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=fenced)

        plan = await create_plan("Research")
        assert len(plan["steps"]) == 2

    @patch("agent.agent_planner.OllamaClient")
    async def test_invalid_json_falls_back(self, mock_ollama):
        """Invalid JSON from the LLM should trigger the fallback plan."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value="not valid json at all")

        plan = await create_plan("test")
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["tool"] == "web_search"

    @patch("agent.agent_planner.OllamaClient")
    async def test_missing_steps_array_falls_back(self, mock_ollama):
        """Valid JSON without a 'steps' array should trigger fallback."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=json.dumps({"goal": "test"}))

        plan = await create_plan("test")
        assert len(plan["steps"]) == 1

    @patch("agent.agent_planner.OllamaClient")
    async def test_empty_steps_list_is_valid(self, mock_ollama):
        """JSON with an empty steps list is valid (not a fallback trigger)."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=json.dumps({"goal": "test", "steps": []}))

        plan = await create_plan("test")
        assert len(plan["steps"]) == 0  # Empty list is kept as-is

    @patch("agent.agent_planner.OllamaClient")
    async def test_exception_during_llm_call_falls_back(self, mock_ollama):
        """Any exception from the LLM should trigger the fallback plan."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        plan = await create_plan("test")
        assert len(plan["steps"]) == 1

    @patch("agent.agent_planner.OllamaClient")
    async def test_context_passed_to_llm(self, mock_ollama):
        """Additional context should be included in the LLM prompt."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=VALID_PLAN_JSON)

        await create_plan("Research", context="User is a physicist")
        # Verify chat was called
        instance.chat.assert_awaited_once()
        messages = instance.chat.await_args[0][0]
        user_msg = messages[1]["content"]
        assert "User is a physicist" in user_msg

    @patch("agent.agent_planner.OllamaClient")
    async def test_steps_have_required_fields(self, mock_ollama):
        """Each step should have step, tool, description, parameters, critical."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=VALID_PLAN_JSON)

        plan = await create_plan("Research")
        for step in plan["steps"]:
            assert "step" in step
            assert "tool" in step
            assert "description" in step
            assert "parameters" in step


# ─── replan ────────────────────────────────────────────────────────────────

class TestReplan:
    """Tests for the async replan() function."""

    VALID_REPLAN_JSON = json.dumps({
        "goal": "Research quantum computing",
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": "Try alternative search query",
                "parameters": {"query": "quantum computing for beginners"},
                "critical": True,
            },
        ],
    })

    @patch("agent.agent_planner.OllamaClient")
    async def test_replan_returns_plan(self, mock_ollama):
        """Replan should return a valid plan on success."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=self.VALID_REPLAN_JSON)

        plan = await replan(
            goal="Research",
            completed_steps=[{"step": 1, "tool": "web_search"}],
            failed_step={"step": 2, "tool": "create_file", "description": "Save file"},
            error="Permission denied",
        )
        assert len(plan["steps"]) == 1

    @patch("agent.agent_planner.OllamaClient")
    async def test_replan_fallback_on_error(self, mock_ollama):
        """When replan LLM call fails, fallback plan should be returned."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(side_effect=RuntimeError("LLM error"))

        plan = await replan(
            goal="Research",
            completed_steps=[],
            failed_step={"step": 1, "tool": "web_search", "description": "Search"},
            error="Error",
        )
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["tool"] == "web_search"

    @patch("agent.agent_planner.OllamaClient")
    async def test_replan_includes_completed_steps(self, mock_ollama):
        """The prompt for replan should include completed steps."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value=self.VALID_REPLAN_JSON)

        await replan(
            goal="Research",
            completed_steps=[{"step": 1, "tool": "web_search", "description": "Initial search"}],
            failed_step={"step": 2, "tool": "create_file", "description": "Save"},
            error="Disk full",
        )
        instance.chat.assert_awaited_once()
        messages = instance.chat.await_args[0][0]
        user_msg = messages[1]["content"]
        assert "DONE" in user_msg
        assert "Disk full" in user_msg
