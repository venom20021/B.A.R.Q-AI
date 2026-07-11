"""
FastAPI routes for the BARQ Agent System.

Exposes the planner, executor, task queue, and memory manager
as REST endpoints that the Electron frontend can call directly.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from memory.agent_memory_manager import (
    extract_memory_async,
    forget,
    load_memory,
    remember,
    should_extract_memory_async,
    update_memory,
)

from .agent_executor import AgentExecutor
from .agent_planner import create_plan
from .skill_registry import get_skill_registry
from .task_queue import TaskPriority, get_task_queue

router = APIRouter()

executor = AgentExecutor()
task_queue = get_task_queue()


# ─── Models ───────────────────────────────────────────────────────────────────

class GoalRequest(BaseModel):
    goal: str
    priority: str = "normal"  # low, normal, high


class MemoryRequest(BaseModel):
    key: str
    value: str
    category: str = "notes"


class MemoryExtractRequest(BaseModel):
    user_text: str
    ai_text: str = ""


class AgentRouteRequest(BaseModel):
    goal: str
    context: Optional[str] = None


class SkillRegisterRequest(BaseModel):
    """Request body for registering a new skill at runtime."""
    name: str
    description: str = ""
    parameters: list[dict] = []
    route_method: str = "POST"
    route_path: str = ""
    route_payload: dict = {}
    critical: bool = True
    category: str = "custom"


# ─── Agent Execution ─────────────────────────────────────────────────────────

@router.post("/execute", summary="Execute a goal synchronously")
async def execute_goal(request: GoalRequest):
    """Execute a multi-step plan for a goal and return the result immediately.

    This is a synchronous (blocking) endpoint — the caller waits for the
    entire plan to complete.  For background execution, use ``/queue`` instead.
    """
    try:
        result = await executor.execute(goal=request.goal)
        return {"status": "completed", "goal": request.goal, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Task Queue ──────────────────────────────────────────────────────────────

@router.post("/queue", summary="Queue a goal for background execution")
async def queue_goal(request: GoalRequest):
    """Submit a goal to the background task queue.

    Returns immediately with a task ID.  Use ``/queue/{task_id}`` to
    check status and get the result when complete.
    """
    priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
    priority = priority_map.get(request.priority.lower(), TaskPriority.NORMAL)

    try:
        task_id = await task_queue.submit(goal=request.goal, priority=priority)
        return {"status": "queued", "task_id": task_id, "goal": request.goal}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/{task_id}", summary="Get task status")
async def get_task_status(task_id: str):
    """Get the current status of a queued task."""
    status = await task_queue.get_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@router.get("/queue", summary="List all tasks")
async def list_tasks():
    """List all tasks in the queue with their statuses."""
    tasks = await task_queue.get_all_statuses()
    pending = await task_queue.pending_count()
    return {"tasks": tasks, "pending_count": pending}


@router.post("/queue/{task_id}/cancel", summary="Cancel a task")
async def cancel_task(task_id: str):
    """Cancel a queued or running task."""
    cancelled = await task_queue.cancel(task_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Task not found or already completed")
    return {"status": "cancelled", "task_id": task_id}


# ─── Planning ────────────────────────────────────────────────────────────────

@router.post("/plan", summary="Create a step-by-step plan for a goal")
async def plan_goal(request: AgentRouteRequest):
    """Generate a step-by-step plan for a goal without executing it.

    Useful for previewing what the agent will do before running.
    """
    try:
        plan = await create_plan(request.goal, context=request.context or "")
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Memory ──────────────────────────────────────────────────────────────────

@router.get("/memory", summary="Get all stored memory")
async def get_memory():
    """Retrieve all long-term memory data."""
    memory = load_memory()
    return {
        "memory": memory,
        "categories": list(memory.keys()),
    }


@router.post("/memory", summary="Store a fact in memory")
async def store_memory(request: MemoryRequest):
    """Store a single fact in long-term memory."""
    msg = remember(request.key, request.value, request.category)
    return {"status": "stored", "message": msg}


@router.delete("/memory/{category}/{key}", summary="Forget a fact")
async def forget_memory(category: str, key: str):
    """Remove a specific fact from memory."""
    msg = forget(key, category)
    return {"status": "forgotten", "message": msg}


# ─── Skill Registry ───────────────────────────────────────────────────────────

@router.get("/skills", summary="List all registered skills")
async def list_skills():
    """List all skills registered in the SkillRegistry.

    Returns a summary of each skill including name, description,
    parameters, and category.  This is the dynamic replacement for
    the old hardcoded ``tool_map``.
    """
    registry = get_skill_registry()
    return {
        "skills": registry.summary(),
        "count": registry.count(),
    }


@router.post("/skills", summary="Register a new skill at runtime")
async def register_skill(request: SkillRegisterRequest):
    """Register a new skill dynamically at runtime.

    Accepts a skill descriptor with the route information needed
    to dispatch calls via HTTP.  For handler-based skills, use
    the ``create_skill_from_handler()`` Python API directly.

    Returns the registered skill's summary.
    """
    registry = get_skill_registry()

    from .skill_registry import Skill, SkillParameter

    params = [
        SkillParameter(
            name=p.get("name", ""),
            type=p.get("type", "string"),
            required=p.get("required", False),
            description=p.get("description", ""),
        )
        for p in request.parameters
    ]

    skill = Skill(
        name=request.name,
        description=request.description,
        parameters=params,
        handler=None,
        critical=request.critical,
        category=request.category,
        metadata={
            "route_method": request.route_method,
            "route_path": request.route_path,
            "route_payload": request.route_payload,
        },
    )

    try:
        registry.register(skill)
        return {"status": "registered", "skill": skill.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/skills/{skill_name}", summary="Unregister a skill")
async def unregister_skill(skill_name: str):
    """Remove a skill from the registry."""
    registry = get_skill_registry()
    try:
        registry.unregister(skill_name)
        return {"status": "unregistered", "skill": skill_name}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")


@router.post("/skills/discover", summary="Discover skills from filesystem")
async def discover_skills(query: dict = {}):
    """Scan a directory for ``.skill.json`` files and register them.

    Request body (optional)::

        {"directory": "/path/to/skills"}

    Defaults to ``./skills`` if not specified.
    """
    directory = query.get("directory", "./skills")
    registry = get_skill_registry()
    count = registry.discover(directory)
    return {"status": "discovered", "skills_registered": count, "total": registry.count()}


@router.post("/memory/extract", summary="Extract facts from conversation")
async def extract_facts(request: MemoryExtractRequest):
    """Analyze a conversation turn and extract memorable facts.

    Returns the extracted facts (if any) and whether memory was updated.
    """
    try:
        should_extract = await should_extract_memory_async(
            request.user_text, request.ai_text
        )
        if not should_extract:
            return {"extracted": False, "facts": {}, "message": "No memorable facts found"}

        facts = await extract_memory_async(request.user_text, request.ai_text)
        if facts:
            update_memory(facts)
            return {"extracted": True, "facts": facts, "message": f"Saved: {list(facts.keys())}"}

        return {"extracted": False, "facts": {}, "message": "No facts to save"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
