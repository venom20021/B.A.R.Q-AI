"""Tests for the BARQ Agent Executor.

Tests the AgentExecutor class with mocked planner, tools, and error handler
to verify the execution flow, error recovery, cancellation, and summarization.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent.agent_executor import AgentExecutor

# ─── Fixtures ──────────────────────────────────────────────────────────────

SIMPLE_PLAN = {
    "goal": "Test goal",
    "steps": [
        {"step": 1, "tool": "web_search", "description": "Search test", "parameters": {"query": "test"}, "critical": True},
    ],
}

MULTI_STEP_PLAN = {
    "goal": "Multi-step goal",
    "steps": [
        {"step": 1, "tool": "web_search", "description": "First search", "parameters": {"query": "first"}, "critical": True},
        {"step": 2, "tool": "web_search", "description": "Second search", "parameters": {"query": "second"}, "critical": False},
    ],
}


@pytest.fixture
def executor():
    """Return an AgentExecutor with no custom HTTP client."""
    return AgentExecutor()


# ─── Basic Execution ──────────────────────────────────────────────────────

class TestExecute:
    """Tests for the main execute() method."""

    @patch("agent.agent_executor.create_plan", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_call_tool", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_summarize", new_callable=AsyncMock)
    async def test_simple_goal_executes(
        self, mock_summarize: AsyncMock, mock_call_tool: AsyncMock,
        mock_create_plan: AsyncMock, executor: AgentExecutor,
    ):
        """A single-step plan should execute the tool and summarize."""
        mock_create_plan.return_value = SIMPLE_PLAN
        mock_call_tool.return_value = "search results"
        mock_summarize.return_value = "Completed search test."

        result = await executor.execute("Test goal")

        mock_create_plan.assert_awaited_once_with("Test goal")
        mock_call_tool.assert_awaited_once()
        mock_summarize.assert_awaited_once()
        assert result == "Completed search test."

    @patch("agent.agent_executor.create_plan", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_call_tool", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_summarize", new_callable=AsyncMock)
    async def test_multi_step_executes_all(
        self, mock_summarize: AsyncMock, mock_call_tool: AsyncMock,
        mock_create_plan: AsyncMock, executor: AgentExecutor,
    ):
        """All steps in a multi-step plan should be executed."""
        mock_create_plan.return_value = MULTI_STEP_PLAN
        mock_call_tool.return_value = "result"
        mock_summarize.return_value = "Done."

        await executor.execute("Multi-step goal")

        assert mock_call_tool.await_count == 2

    @patch("agent.agent_executor.create_plan", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_call_tool", new_callable=AsyncMock)
    async def test_empty_plan_returns_error_message(
        self, mock_call_tool: AsyncMock, mock_create_plan: AsyncMock,
        executor: AgentExecutor,
    ):
        """A plan with no steps should return a helpful error message."""
        mock_create_plan.return_value = {"goal": "test", "steps": []}

        result = await executor.execute("test")
        assert "couldn't create" in result.lower()
        mock_call_tool.assert_not_awaited()

    @patch("agent.agent_executor.create_plan", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_call_tool", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_summarize", new_callable=AsyncMock)
    async def test_step_results_passed_to_summarize(
        self, mock_summarize: AsyncMock, mock_call_tool: AsyncMock,
        mock_create_plan: AsyncMock, executor: AgentExecutor,
    ):
        """Completed steps should be passed to _summarize."""
        mock_create_plan.return_value = SIMPLE_PLAN
        mock_call_tool.return_value = "some result"

        await executor.execute("Test goal")

        # Verify summarize was called with the completed steps
        args, _ = mock_summarize.call_args
        assert "Test goal" in args[0]
        assert len(args[1]) == 1


# ─── Error Recovery ───────────────────────────────────────────────────────

class TestErrorRecovery:
    """Tests for error recovery during execution."""

    @patch("agent.agent_executor.create_plan", new_callable=AsyncMock)
    @patch("agent.agent_executor.replan", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_call_tool", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_summarize", new_callable=AsyncMock)
    async def test_error_recovery_completes(
        self, mock_summarize: AsyncMock, mock_call_tool: AsyncMock,
        mock_replan: AsyncMock, mock_create_plan: AsyncMock,
        executor: AgentExecutor,
    ):
        """When a step fails repeatedly and fix also fails, replan is called."""
        mock_create_plan.return_value = SIMPLE_PLAN
        mock_replan.return_value = SIMPLE_PLAN
        # Two transient errors (RETRY then max-attempts REPLAN),
        # then the fix also fails, forcing replan() call,
        # then the replanned step succeeds
        mock_call_tool.side_effect = [
            RuntimeError("Connection timeout after 30s"),  # attempt 1 → RETRY
            RuntimeError("Connection timeout after 30s"),  # attempt 2 → REPLAN → fix attempt
            RuntimeError("fix also fails"),                 # fix fails → call replan()
            "search results",                               # replanned step succeeds
        ]

        result = await executor.execute("Test goal")
        assert result
        # Should have called replan since both transient errors and fix failed
        mock_replan.assert_awaited()
        # Should have called _call_tool 4 times (2 original + 1 fix + 1 replanned)
        assert mock_call_tool.await_count == 4


# ─── Cancellation ─────────────────────────────────────────────────────────

class TestCancellation:
    """Tests for task cancellation via cancel_flag."""

    @patch("agent.agent_executor.create_plan", new_callable=AsyncMock)
    @patch.object(AgentExecutor, "_call_tool", new_callable=AsyncMock)
    async def test_cancel_before_execution(
        self, mock_call_tool: AsyncMock, mock_create_plan: AsyncMock,
        executor: AgentExecutor,
    ):
        """If cancel_flag is set, task should cancel before running steps."""
        mock_create_plan.return_value = MULTI_STEP_PLAN

        cancel_flag = asyncio.Event()
        cancel_flag.set()

        result = await executor.execute("Test", cancel_flag=cancel_flag)
        assert result == "Task cancelled."
        mock_call_tool.assert_not_awaited()


# ─── _inject_context ──────────────────────────────────────────────────────

class TestInjectContext:
    """Tests for the _inject_context helper."""

    @pytest.fixture
    def executor(self):
        return AgentExecutor()

    async def test_no_results_returns_params_unchanged(self, executor):
        """With no step results, params should be returned unchanged."""
        params = {"path": "/tmp/test.txt"}
        result = await executor._inject_context(params, "create_file", {})
        assert result == params

    async def test_create_file_injects_content(self, executor):
        """For create_file tool, content from step results should be injected."""
        params = {"path": "/tmp/test.txt", "content": ""}
        step_results = {"1": "long research content " * 20}
        result = await executor._inject_context(params, "create_file", step_results)
        assert "research content" in result.get("content", "")

    async def test_create_file_skipped_if_content_already_set(self, executor):
        """If content is already provided, don't overwrite it."""
        params = {"path": "/tmp/test.txt", "content": "existing content"}
        step_results = {"1": "long research content " * 20}
        result = await executor._inject_context(params, "create_file", step_results)
        assert result["content"] == "existing content"

    async def test_non_create_file_ignores_context(self, executor):
        """For non-create_file tools, params should be returned unchanged."""
        params = {"query": "test"}
        step_results = {"1": "some result"}
        result = await executor._inject_context(params, "web_search", step_results)
        assert result == params


# ─── _summarize ───────────────────────────────────────────────────────────

class TestSummarize:
    """Tests for the _summarize helper."""

    @pytest.fixture
    def executor(self):
        return AgentExecutor()

    @patch("utils.ollama_client.OllamaClient")
    async def test_summarize_calls_llm(self, mock_ollama, executor):
        """_summarize should call the LLM with step descriptions."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(return_value="Great summary.")

        result = await executor._summarize("Test goal", [{"description": "Step 1", "step": 1, "tool": "test"}])
        assert result == "Great summary."

    @patch("utils.ollama_client.OllamaClient")
    async def test_summarize_fallback_on_error(self, mock_ollama, executor):
        """When the LLM fails, _summarize should return a fallback string."""
        instance = mock_ollama.return_value
        instance.chat = AsyncMock(side_effect=RuntimeError("LLM down"))

        result = await executor._summarize("Test goal", [{"description": "Step 1", "step": 1, "tool": "test"}])
        assert "Test goal" in result
        assert "1" in result or "steps" in result
