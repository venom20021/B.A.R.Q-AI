"""Tests for the BARQ Agent Planner.

Tests the agent_planner.py module's create_plan() and replan() functions.
The LLM (OllamaClient) is mocked to return controlled JSON responses.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Override the conftest.py autouse DB fixture — these tests are pure
# function tests and do not need a database connection.
@pytest.fixture(autouse=True)
def setup_db():
    """Override conftest's autouse DB fixture — no DB needed for these tests."""
    return


from agent.agent_planner import _fallback_plan, create_plan, replan  # noqa: E402


@pytest.fixture
def mock_kernel():
    """Create a mock AgentKernel that returns controlled responses."""
    from agent.agent_kernel import AgentKernel
    kernel = MagicMock(spec=AgentKernel)
    kernel.chat = AsyncMock(return_value='{"goal":"test","steps":[]}')
    with patch("agent.agent_planner.get_agent_kernel", return_value=kernel):
        yield kernel


@pytest.fixture
def mock_kernel_valid():
    """Mock kernel returning VALID_PLAN_JSON."""
    from agent.agent_kernel import AgentKernel
    kernel = MagicMock(spec=AgentKernel)
    kernel.chat = AsyncMock(return_value=VALID_PLAN_JSON)
    with patch("agent.agent_planner.get_agent_kernel", return_value=kernel):
        yield kernel


@pytest.fixture
def mock_kernel_replan():
    """Mock kernel returning a 1-step replan response."""
    from agent.agent_kernel import AgentKernel
    replan_json = json.dumps({
        "goal": "Research",
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
    kernel = MagicMock(spec=AgentKernel)
    kernel.chat = AsyncMock(return_value=replan_json)
    with patch("agent.agent_planner.get_agent_kernel", return_value=kernel):
        yield kernel

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

    def test_step_uses_respond(self):
        plan = _fallback_plan("test goal")
        assert plan["steps"][0]["tool"] == "respond"

    def test_step_is_not_critical(self):
        plan = _fallback_plan("test goal")
        assert plan["steps"][0]["critical"] is False

    def test_step_has_conversational_description(self):
        plan = _fallback_plan("custom goal")
        assert "Respond conversationally" in plan["steps"][0]["description"]


# ─── create_plan ───────────────────────────────────────────────────────────

class TestCreatePlan:
    """Tests for the async create_plan() function with mocked LLM."""

    async def test_valid_plan_returned(self, mock_kernel_valid):
        """A valid JSON response should be parsed and returned."""
        plan = await create_plan("Research quantum computing")
        assert plan["goal"] == "Research quantum computing"
        assert len(plan["steps"]) == 2
        assert plan["steps"][0]["tool"] == "web_search"

    async def test_markdown_code_fence_stripped(self, mock_kernel):
        """Markdown ```json fences around the JSON should be stripped."""
        fenced = f"```json\n{VALID_PLAN_JSON}\n```"
        mock_kernel.chat = AsyncMock(return_value=fenced)

        plan = await create_plan("Research")
        assert len(plan["steps"]) == 2

    async def test_backtick_fence_stripped(self, mock_kernel):
        """Plain ``` fences should also be stripped."""
        fenced = f"```\n{VALID_PLAN_JSON}\n```"
        mock_kernel.chat = AsyncMock(return_value=fenced)

        plan = await create_plan("Research")
        assert len(plan["steps"]) == 2

    async def test_invalid_json_falls_back(self, mock_kernel):
        """Invalid JSON from the LLM should trigger the fallback plan."""
        mock_kernel.chat = AsyncMock(return_value="not valid json at all")

        plan = await create_plan("test")
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["tool"] == "respond"

    async def test_missing_steps_array_falls_back(self, mock_kernel):
        """Valid JSON without a 'steps' array should trigger fallback."""
        mock_kernel.chat = AsyncMock(return_value=json.dumps({"goal": "test"}))

        plan = await create_plan("test")
        assert len(plan["steps"]) == 1

    async def test_empty_steps_list_is_valid(self, mock_kernel):
        """JSON with an empty steps list is valid (not a fallback trigger)."""
        mock_kernel.chat = AsyncMock(return_value=json.dumps({"goal": "test", "steps": []}))

        plan = await create_plan("test")
        assert len(plan["steps"]) == 0  # Empty list is kept as-is

    async def test_exception_during_llm_call_falls_back(self, mock_kernel):
        """Any exception from the LLM should trigger the fallback plan."""
        mock_kernel.chat = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        plan = await create_plan("test")
        assert len(plan["steps"]) == 1

    async def test_context_passed_to_llm(self, mock_kernel_valid):
        """Additional context should be included in the LLM prompt."""
        await create_plan("Research", context="User is a physicist")
        mock_kernel_valid.chat.assert_awaited_once()
        messages = mock_kernel_valid.chat.await_args[0][0]
        user_msg = messages[1]["content"]
        assert "User is a physicist" in user_msg

    async def test_steps_have_required_fields(self, mock_kernel_valid):
        """Each step should have step, tool, description, parameters, critical."""
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

    async def test_replan_returns_plan(self, mock_kernel_replan):
        """Replan should return a valid plan on success."""
        plan = await replan(
            goal="Research",
            completed_steps=[{"step": 1, "tool": "web_search"}],
            failed_step={"step": 2, "tool": "create_file", "description": "Save file"},
            error="Permission denied",
        )
        assert len(plan["steps"]) == 1

    async def test_replan_fallback_on_error(self, mock_kernel):
        """When replan LLM call fails, fallback plan should be returned."""
        mock_kernel.chat = AsyncMock(side_effect=RuntimeError("LLM error"))

        plan = await replan(
            goal="Research",
            completed_steps=[],
            failed_step={"step": 1, "tool": "web_search", "description": "Search"},
            error="Error",
        )
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["tool"] == "respond"

    async def test_replan_includes_completed_steps(self, mock_kernel_valid):
        """The prompt for replan should include completed steps."""
        await replan(
            goal="Research",
            completed_steps=[{"step": 1, "tool": "web_search", "description": "Initial search"}],
            failed_step={"step": 2, "tool": "create_file", "description": "Save"},
            error="Disk full",
        )
        mock_kernel_valid.chat.assert_awaited_once()
        messages = mock_kernel_valid.chat.await_args[0][0]
        user_msg = messages[1]["content"]
        assert "DONE" in user_msg
        assert "Disk full" in user_msg
