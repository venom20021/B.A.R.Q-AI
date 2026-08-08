"""
FastAPI routes for BARQ Agentic Workflows.

Endpoints:
  Workflow runtime (W1):
    GET    /agent/workflows              - list registered workflows
    POST   /agent/workflows              - register a workflow definition
    DELETE /agent/workflows/{name}       - unregister a workflow
    POST   /agent/workflows/{name}/run   - run a workflow (sync or background)
    GET    /agent/workflows/runs         - list recent runs
    GET    /agent/workflows/runs/{id}    - run status
  Checkpoints (W2):
    GET    /agent/checkpoints            - list persisted checkpoints
    POST   /agent/checkpoints/{key}/resume - resume an agent execution
  Workflow modules:
    POST   /agent/briefing/run           - W4 morning briefing
    POST   /agent/memory/conversation    - W5 conversation memory
    POST   /agent/research/to-brain      - W6 research -> knowledge graph
    POST   /agent/content/critic         - W7 content critic loop
    POST   /agent/review/weekly          - W11 weekly review report
"""

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter()

# Live run-progress WebSocket clients (Workflows page).
_ws_clients: set[WebSocket] = set()


async def _broadcast_run_event(message: dict[str, Any]) -> None:
    """Push a message to every connected run-progress WebSocket client."""
    dead: set[WebSocket] = set()
    for client in list(_ws_clients):
        try:
            await client.send_json(message)
        except Exception:
            dead.add(client)
    for client in dead:
        _ws_clients.discard(client)


def _make_progress_cb(run_id: str):
    """Build a runtime progress callback that broadcasts the live run state."""
    async def _cb(step_id: str, status: str, result: Any) -> None:
        from .workflow_runtime import get_workflow_runtime
        run = get_workflow_runtime().get_run(run_id)
        if run:
            await _broadcast_run_event({"type": "run", "run": run})
    return _cb


@router.websocket("/workflows/ws")
async def workflow_progress_ws(websocket: WebSocket):
    """Stream live workflow run progress (instant step updates).

    Protocol (server → client):
      {"type": "run", "run": {run_id, workflow, status, results, ...}}
    Client may send ``ping`` → server replies ``{"type": "pong"}``.
    """
    await websocket.accept()
    _ws_clients.add(websocket)
    # Snapshot: immediately send currently-active runs so a newly connected
    # client sees in-flight progress without waiting for the next event.
    try:
        from .workflow_runtime import get_workflow_runtime
        runtime = get_workflow_runtime()
        for run in runtime.list_runs(limit=20):
            if run.get("status") in ("queued", "running"):
                full = runtime.get_run(run["run_id"]) or run
                await websocket.send_json({"type": "run", "run": full})
    except Exception:
        pass
    try:
        while True:
            raw = await websocket.receive_text()
            if raw == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)


# ─── Models ────────────────────────────────────────────────────────────────


class WorkflowRegisterRequest(BaseModel):
    name: str
    description: str = ""
    steps: list[dict[str, Any]] = []
    trigger: str = "manual"
    cron: Optional[str] = None
    timeout_seconds: int = 600


class WorkflowRunRequest(BaseModel):
    context: dict[str, Any] = {}
    background: bool = False


class ConversationMemoryRequest(BaseModel):
    user_text: str
    ai_text: str = ""


class ContentCriticRequest(BaseModel):
    draft: str
    topic: str = ""
    platform: str = "linkedin_post"
    min_score: int = 80
    max_iterations: int = 2


class ResearchToBrainRequest(BaseModel):
    topic: str
    report: str


# ─── Workflow Runtime (W1) ──────────────────────────────────────────────────


@router.get("/workflows", summary="List registered workflows")
async def list_workflows():
    from .workflow_runtime import get_workflow_runtime
    return {"workflows": get_workflow_runtime().list_workflows()}


@router.post("/workflows", summary="Register a workflow definition")
async def register_workflow(request: WorkflowRegisterRequest):
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Workflow name is required")
    if not request.steps:
        raise HTTPException(status_code=400, detail="Workflow must define at least one step")

    from .workflow_runtime import get_workflow_runtime
    wf = get_workflow_runtime().load_from_dict(request.model_dump())
    return {"status": "registered", "workflow": wf.to_dict()}


@router.delete("/workflows/{name}", summary="Unregister a workflow")
async def unregister_workflow(name: str):
    from .workflow_runtime import get_workflow_runtime
    removed = get_workflow_runtime().remove(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return {"status": "removed", "workflow": name}


@router.post("/workflows/{name}/run", summary="Run a workflow")
async def run_workflow(name: str, request: WorkflowRunRequest):
    from .workflow_runtime import get_workflow_runtime
    runtime = get_workflow_runtime()

    if runtime.get(name) is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")

    if request.background:
        run_id = f"workflow:{__import__('uuid').uuid4().hex[:8]}"
        runtime._runs[run_id] = {
            "run_id": run_id, "workflow": name, "status": "queued",
            "started_at": __import__("time").time(), "results": [],
        }
        progress_cb = _make_progress_cb(run_id)
        # Push the queued state immediately
        await _broadcast_run_event({"type": "run", "run": runtime._runs[run_id]})

        async def _bg():
            try:
                result = await runtime.run(
                    name, context=request.context, run_id=run_id, progress_cb=progress_cb
                )
                await _broadcast_run_event({"type": "run", "run": result})
            except Exception as e:
                run = runtime._runs.get(run_id)
                if run:
                    run["status"] = "failed"
                    run["error"] = str(e)
                    await _broadcast_run_event({"type": "run", "run": run})

        asyncio.create_task(_bg())
        return {"status": "queued", "run_id": run_id}

    run_id = f"workflow:{__import__('uuid').uuid4().hex[:8]}"
    progress_cb = _make_progress_cb(run_id)
    result = await runtime.run(
        name, context=request.context, run_id=run_id, progress_cb=progress_cb
    )
    await _broadcast_run_event({"type": "run", "run": result})
    return result


@router.get("/workflows/runs", summary="List recent workflow runs")
async def list_runs(limit: int = 20):
    from .workflow_runtime import get_workflow_runtime
    return {"runs": get_workflow_runtime().list_runs(limit=limit)}


@router.get("/workflows/runs/{run_id}", summary="Get workflow run status")
async def get_run(run_id: str):
    from .workflow_runtime import get_workflow_runtime
    run = get_workflow_runtime().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


# ─── Checkpoints (W2) ───────────────────────────────────────────────────────


@router.get("/checkpoints", summary="List persisted agent/workflow checkpoints")
async def list_checkpoints(limit: int = 50):
    from .checkpoint_store import get_checkpoint_store
    store = get_checkpoint_store()
    rows = await store.list_with_parsed_data(limit=limit)
    # Enrich each row with parsed progress so the UI can show what the
    # checkpoint is about (goal / workflow name + step counts).
    enriched = []
    for row in rows:
        state = row.get("data") or {}
        plan = state.get("plan") or {}
        plan_steps = plan.get("steps", []) if isinstance(plan, dict) else []
        completed = state.get("completed_steps") or []
        enriched.append({
            "checkpoint_key": row["checkpoint_key"],
            "agent_type": row["agent_type"],
            "status": row["status"],
            "updated_at": row.get("updated_at"),
            "goal": (state.get("goal") or state.get("workflow") or "")[:160],
            "completed_steps": len(completed) if isinstance(completed, list) else 0,
            "total_steps": len(plan_steps) if isinstance(plan_steps, list) else 0,
        })
    return {"checkpoints": enriched, "count": len(enriched)}


@router.post("/checkpoints/{checkpoint_key}/resume", summary="Resume an agent execution from a checkpoint")
async def resume_checkpoint(checkpoint_key: str):
    from .checkpoint_store import get_checkpoint_store
    store = get_checkpoint_store()
    state = await store.load(checkpoint_key)
    if not state:
        raise HTTPException(status_code=404, detail=f"Checkpoint '{checkpoint_key}' not found")

    # Workflow checkpoints resume through the workflow runtime (run_id = key),
    # which auto-loads the persisted step state and continues from there.
    if checkpoint_key.startswith("workflow:"):
        from .workflow_runtime import get_workflow_runtime
        name = state.get("workflow", "")
        if not name:
            raise HTTPException(status_code=400, detail="Workflow checkpoint is missing its workflow name")
        try:
            result = await get_workflow_runtime().run(name, run_id=checkpoint_key)
            return {"status": result.get("status", "completed"), "checkpoint": checkpoint_key, "result": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    from .agent_executor import AgentExecutor
    executor = AgentExecutor()
    try:
        result = await executor.execute(goal=state.get("goal", ""), resume_from=checkpoint_key)
        return {"status": "completed", "checkpoint": checkpoint_key, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Workflow modules ───────────────────────────────────────────────────────


@router.post("/briefing/run", summary="W4 — Generate the morning briefing")
async def run_briefing(notify: bool = True):
    from .workflows.morning_briefing import run_morning_briefing
    try:
        result = await run_morning_briefing(notify=notify)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/conversation", summary="W5 — Extract memory from a conversation turn")
async def extract_conversation_memory(request: ConversationMemoryRequest):
    from .workflows.conversation_memory import process_conversation_turn
    if not request.user_text.strip():
        raise HTTPException(status_code=400, detail="user_text is required")
    try:
        return await process_conversation_turn(request.user_text, request.ai_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research/to-brain", summary="W6 — Extract research report into the knowledge graph")
async def research_to_brain(request: ResearchToBrainRequest):
    from .workflows.research_to_brain import extract_research_to_brain
    if not request.report.strip():
        raise HTTPException(status_code=400, detail="report is required")
    try:
        return await extract_research_to_brain(request.topic, request.report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/content/critic", summary="W7 — Quality-gate a social draft (evaluator-optimizer)")
async def content_critic(request: ContentCriticRequest):
    from .workflows.content_critic import ContentCritic
    if not request.draft.strip():
        raise HTTPException(status_code=400, detail="draft is required")
    try:
        critic = ContentCritic(min_score=request.min_score, max_iterations=request.max_iterations)
        return await critic.critique_and_improve(request.draft, request.topic, request.platform)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review/weekly", summary="W11 — Generate the weekly review report")
async def weekly_review(notify: bool = True, days: int = 7):
    from .workflows.weekly_review import run_weekly_review
    try:
        return await run_weekly_review(notify=notify, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
