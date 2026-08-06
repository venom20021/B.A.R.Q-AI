"""
Tests for the agent checkpoint routes (W2) — agent.workflow_routes.

Covers:
- GET /agent/checkpoints returns enriched rows (goal, step progress)
- POST /agent/checkpoints/{key}/resume resumes an agent checkpoint via AgentExecutor
- POST /agent/checkpoints/{key}/resume resumes a workflow checkpoint via the runtime
- Resume on a missing checkpoint returns 404
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.checkpoint_store import get_checkpoint_store


@pytest.fixture
def router():
    from agent import workflow_routes
    return workflow_routes.router


@pytest.mark.asyncio
async def test_list_checkpoints_enriched(client):
    """GET /checkpoints enriches each row with goal + step progress."""
    store = get_checkpoint_store()
    await store.save(
        "agent:rich1",
        {
            "goal": "Build a landing page",
            "plan": {"steps": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
            "completed_steps": [{"step": 1, "skill": "web_scrape"}],
        },
        agent_type="agent",
    )
    await store.save(
        "workflow:rich2",
        {"workflow": "evening_research", "step_results": {"a": "ok"}},
        agent_type="workflow",
    )

    response = await client.get("/checkpoints")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2

    agent_row = next(r for r in data["checkpoints"] if r["checkpoint_key"] == "agent:rich1")
    assert agent_row["goal"] == "Build a landing page"
    assert agent_row["agent_type"] == "agent"
    assert agent_row["completed_steps"] == 1
    assert agent_row["total_steps"] == 3

    wf_row = next(r for r in data["checkpoints"] if r["checkpoint_key"] == "workflow:rich2")
    # Workflow checkpoints surface their workflow name as the label
    assert wf_row["goal"] == "evening_research"
    assert wf_row["agent_type"] == "workflow"


@pytest.mark.asyncio
async def test_resume_agent_checkpoint(client):
    """Resume dispatches agent checkpoints to AgentExecutor with resume_from."""
    store = get_checkpoint_store()
    await store.save(
        "agent:resume1",
        {"goal": "Finish the report", "plan": {"steps": []}, "completed_steps": []},
        agent_type="agent",
    )

    with patch("agent.agent_executor.AgentExecutor") as mock_exec_cls:
        mock_exec = mock_exec_cls.return_value
        mock_exec.execute = AsyncMock(return_value="Resumed and finished the report.")
        response = await client.post("/checkpoints/agent:resume1/resume")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["checkpoint"] == "agent:resume1"
    assert "finished the report" in data["result"]
    # Executor got the checkpoint's goal + resume key
    mock_exec.execute.assert_awaited_once_with(goal="Finish the report", resume_from="agent:resume1")


@pytest.mark.asyncio
async def test_resume_workflow_checkpoint(client):
    """Resume dispatches workflow checkpoints to the runtime via run_id."""
    store = get_checkpoint_store()
    await store.save(
        "workflow:resume2",
        {"workflow": "evening_research", "step_results": {"a": "ok"}},
        agent_type="workflow",
    )

    fake_runtime = MagicMock()
    fake_runtime.run = AsyncMock(return_value={
        "run_id": "workflow:resume2", "status": "completed",
        "step_results": {"a": "ok", "b": "done"},
    })

    with patch("agent.workflow_runtime.get_workflow_runtime", return_value=fake_runtime) as mock_runtime:
        response = await client.post("/checkpoints/workflow:resume2/resume")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["result"]["status"] == "completed"
    # Resumed by run_id = checkpoint key so the runtime reloads persisted state
    fake_runtime.run.assert_awaited_once_with("evening_research", run_id="workflow:resume2")
    mock_runtime.assert_called_once()


@pytest.mark.asyncio
async def test_resume_missing_checkpoint_404(client):
    """Resuming a checkpoint that does not exist returns 404."""
    response = await client.post("/checkpoints/agent:ghost/resume")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


# ─── Run-progress WebSocket (live streaming) ────────────────────────────────


def test_workflow_ws_route_registered(router):
    """The live run-progress WebSocket route is mounted on the router."""
    paths = [getattr(r, "path", "") for r in router.routes]
    assert "/workflows/ws" in paths


@pytest.mark.asyncio
async def test_broadcast_run_event_sends_and_prunes_dead_clients():
    """Broadcast delivers to live clients and prunes broken ones."""
    from agent import workflow_routes

    live = AsyncMock()
    dead = AsyncMock()
    dead.send_json = AsyncMock(side_effect=RuntimeError("client gone"))

    workflow_routes._ws_clients.clear()
    workflow_routes._ws_clients.add(live)
    workflow_routes._ws_clients.add(dead)
    try:
        await workflow_routes._broadcast_run_event({"type": "run", "run": {"run_id": "workflow:abc"}})
        live.send_json.assert_awaited_once_with({"type": "run", "run": {"run_id": "workflow:abc"}})
        # Broken client was pruned, healthy one remains
        assert dead not in workflow_routes._ws_clients
        assert live in workflow_routes._ws_clients
    finally:
        workflow_routes._ws_clients.clear()
