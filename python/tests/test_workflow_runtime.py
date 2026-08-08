"""
Tests for the Workflow Runtime (W1) — agent.workflow_runtime.

Covers:
- Sequential chaining with ${step.<id>} context injection
- ${context.<key>} placeholder resolution
- Parallel step groups (Orchestrator-Workers)
- Failure handling (critical step failure → workflow failed)
- Checkpointing persists run progress
"""


import pytest

from agent.skill_registry import Skill, get_skill_registry
from agent.workflow_runtime import Workflow, WorkflowRuntime, WorkflowStep

_log: list[str] = []


async def _mock_echo_skill(**kwargs):
    _log.append(f"echo:{kwargs.get('message', '')}")
    return f"echoed:{kwargs.get('message', '')}"


async def _mock_pass_skill(**kwargs):
    _log.append(f"pass:{kwargs.get('id', '')}")
    return f"ok-{kwargs.get('id', '')}"


async def _mock_fail_skill(**kwargs):
    raise RuntimeError("boom")


@pytest.fixture
def runtime():
    """Fresh runtime with mock skills registered (cleaned up after)."""
    registry = get_skill_registry()
    registry.register_or_replace(Skill(name="mock_echo", handler=_mock_echo_skill, critical=False, category="test"))
    registry.register_or_replace(Skill(name="mock_pass", handler=_mock_pass_skill, critical=False, category="test"))
    registry.register_or_replace(Skill(name="mock_fail", handler=_mock_fail_skill, critical=False, category="test"))
    _log.clear()
    rt = WorkflowRuntime()
    yield rt
    for name in ("mock_echo", "mock_pass", "mock_fail"):
        try:
            registry.unregister(name)
        except KeyError:
            pass


@pytest.mark.asyncio
async def test_sequential_chain_with_context_injection(runtime):
    wf = Workflow(
        name="chain_test",
        steps=[
            WorkflowStep(id="a", skill="mock_echo", params={"message": "hello"}, description="step a"),
            WorkflowStep(id="b", skill="mock_echo", params={"message": "${step.a}"}, description="step b"),
            WorkflowStep(id="c", skill="mock_echo", params={"message": "${context.suffix}"}, description="step c"),
        ],
    )
    runtime.register(wf)
    result = await runtime.run("chain_test", context={"suffix": "from-context"}, checkpoint=False)

    assert result["status"] == "completed"
    assert result["step_results"]["b"] == "echoed:echoed:hello"
    assert result["step_results"]["c"] == "echoed:from-context"
    # Execution order: a → b → c
    assert _log == ["echo:hello", "echo:echoed:hello", "echo:from-context"]


@pytest.mark.asyncio
async def test_parallel_group_runs_siblings(runtime):
    wf = Workflow(
        name="parallel_test",
        steps=[
            WorkflowStep(id="w", skill="mock_echo", params={"message": "weather"}, description="weather"),
            WorkflowStep(id="t", skill="mock_echo", params={"message": "trends"}, description="trends",
                         parallel_with=["w"]),
            WorkflowStep(id="s", skill="mock_echo", params={"message": "${step.w} | ${step.t}"}, description="summary"),
        ],
    )
    runtime.register(wf)
    result = await runtime.run("parallel_test", checkpoint=False)

    assert result["status"] == "completed"
    assert "echoed:weather" in result["step_results"]["s"]
    assert "echoed:trends" in result["step_results"]["s"]
    assert result["step_results"]["w"] == "echoed:weather"
    assert result["step_results"]["t"] == "echoed:trends"


@pytest.mark.asyncio
async def test_critical_step_failure_fails_workflow(runtime):
    wf = Workflow(
        name="fail_test",
        steps=[
            WorkflowStep(id="a", skill="mock_pass", params={"id": "a"}, description="a"),
            WorkflowStep(id="b", skill="mock_fail", params={}, description="b", critical=True),
            WorkflowStep(id="c", skill="mock_pass", params={"id": "c"}, description="c"),
        ],
    )
    runtime.register(wf)
    result = await runtime.run("fail_test", checkpoint=False)

    assert result["status"] == "failed"
    assert "boom" in result["error"]
    assert "c" not in result["step_results"]  # never reached


@pytest.mark.asyncio
async def test_non_critical_step_failure_continues(runtime):
    wf = Workflow(
        name="continue_test",
        steps=[
            WorkflowStep(id="a", skill="mock_fail", params={}, description="a", critical=False),
            WorkflowStep(id="b", skill="mock_pass", params={"id": "b"}, description="b"),
        ],
    )
    runtime.register(wf)
    result = await runtime.run("continue_test", checkpoint=False)

    assert result["status"] == "completed"
    assert result["step_results"]["b"] == "ok-b"


@pytest.mark.asyncio
async def test_unknown_workflow_raises(runtime):
    with pytest.raises(ValueError, match="Unknown workflow"):
        await runtime.run("does_not_exist", checkpoint=False)


@pytest.mark.asyncio
async def test_failure_route_loop_is_caught(runtime):
    """A next_on_failure route that loops back must fail instead of spinning."""
    wf = Workflow(
        name="loop_test",
        steps=[
            WorkflowStep(id="a", skill="mock_fail", params={}, description="a", critical=True,
                         next_on_failure="a"),  # routes to itself → infinite loop
        ],
    )
    runtime.register(wf)
    result = await runtime.run("loop_test", checkpoint=False)
    assert result["status"] == "failed"
    assert "loop" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_progress_cb_fires_per_step(runtime):
    """progress_cb receives running → completed events for every step."""
    events: list[tuple[str, str]] = []

    async def cb(step_id: str, status: str, result) -> None:
        events.append((step_id, status))

    wf = Workflow(
        name="progress_test",
        steps=[
            WorkflowStep(id="a", skill="mock_pass", params={"id": "a"}, description="a"),
            WorkflowStep(id="b", skill="mock_pass", params={"id": "b"}, description="b"),
        ],
    )
    runtime.register(wf)
    result = await runtime.run("progress_test", progress_cb=cb, checkpoint=False)

    assert result["status"] == "completed"
    assert ("a", "running") in events
    assert ("a", "completed") in events
    assert ("b", "running") in events
    assert ("b", "completed") in events


@pytest.mark.asyncio
async def test_progress_cb_fires_on_failure(runtime):
    """progress_cb receives running → failed for a step that errors."""
    events: list[tuple[str, str]] = []

    async def cb(step_id: str, status: str, result) -> None:
        events.append((step_id, status))

    wf = Workflow(
        name="progress_fail",
        steps=[
            WorkflowStep(id="a", skill="mock_fail", params={}, description="a", critical=True),
        ],
    )
    runtime.register(wf)
    result = await runtime.run("progress_fail", progress_cb=cb, checkpoint=False)

    assert result["status"] == "failed"
    assert ("a", "running") in events
    assert ("a", "failed") in events


@pytest.mark.asyncio
async def test_run_is_checkpointed(runtime):
    """Workflow runs persist progress via the checkpoint store."""
    wf = Workflow(
        name="checkpoint_test",
        steps=[
            WorkflowStep(id="a", skill="mock_pass", params={"id": "a"}, description="a"),
            WorkflowStep(id="b", skill="mock_pass", params={"id": "b"}, description="b"),
        ],
    )
    runtime.register(wf)
    result = await runtime.run("checkpoint_test", checkpoint=True)

    assert result["status"] == "completed"
    from agent.checkpoint_store import get_checkpoint_store
    state = await get_checkpoint_store().load(result["run_id"])
    assert state is not None
    assert len(state.get("step_results", {})) == 2
