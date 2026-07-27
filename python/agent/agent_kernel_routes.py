"""
BARQ Agent Kernel & Analytics API Routes — expose status and metrics endpoints.

Provides FastAPI routers for:
- /agent/kernel/* → AgentKernel health, agent stats, context windows
- /agent/skills/stats → SkillRegistry performance analytics
- /memory/bus/* → MemoryBus status, search, stats
"""

import time

from fastapi import APIRouter

from .agent_kernel import get_agent_kernel
from .skill_registry import get_skill_registry
from memory.memory_bus import get_memory_bus

kernel_router = APIRouter(prefix="/agent/kernel", tags=["Agent Kernel"])
skill_router = APIRouter(prefix="/agent/skills", tags=["Skill Analytics"])
memory_bus_router = APIRouter(prefix="/memory/bus", tags=["Memory Bus"])


# ─── AgentKernel Routes ───────────────────────────────────────────────────


@kernel_router.get("/status")
async def kernel_status():
    """Get AgentKernel health and load status."""
    kernel = get_agent_kernel()
    return await kernel.get_status()


@kernel_router.get("/agents")
async def kernel_agents():
    """Get per-agent LLM usage statistics."""
    kernel = get_agent_kernel()
    return {"agents": await kernel.get_all_stats()}


@kernel_router.get("/agents/{agent_name}")
async def kernel_agent(agent_name: str):
    """Get LLM usage for a specific agent."""
    kernel = get_agent_kernel()
    stats = await kernel.get_agent_stats(agent_name)
    if stats is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return stats


@kernel_router.get("/contexts")
async def kernel_contexts():
    """Get all active context windows."""
    kernel = get_agent_kernel()
    contexts = []
    async with kernel._context_lock:
        for conv_id, cw in kernel._context_windows.items():
            contexts.append({
                "conversation_id": conv_id,
                "agent": cw.agent_name,
                "tokens_used": cw.tokens_used,
                "max_tokens": cw.max_tokens,
                "message_count": cw.message_count,
                "age_seconds": round(time.time() - cw.started_at, 1),
            })
    return {"contexts": contexts}


# ─── Skill Analytics Routes ────────────────────────────────────────────────


@skill_router.get("/stats")
async def skill_stats():
    """Get execution analytics for all skills."""
    registry = get_skill_registry()
    return {
        "summary": registry.get_stats_summary(),
        "skills": registry.get_all_stats(),
    }


@skill_router.get("/stats/{skill_name}")
async def skill_stat(skill_name: str):
    """Get execution analytics for a specific skill."""
    registry = get_skill_registry()
    stats = registry.get_skill_stats(skill_name)
    if stats is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No stats for skill '{skill_name}'")
    return stats


@skill_router.get("/list")
async def skill_list():
    """List all registered skills with their metadata."""
    registry = get_skill_registry()
    return {"skills": registry.summary()}


# ─── Memory Bus Routes ────────────────────────────────────────────────────


@memory_bus_router.get("/stats")
async def memory_stats():
    """Get MemoryBus statistics."""
    bus = get_memory_bus()
    return await bus.get_stats()


@memory_bus_router.post("/search")
async def memory_search(data: dict):
    """Full-text search across all memories."""
    bus = get_memory_bus()
    results = await bus.search(
        query=data.get("query", ""),
        category=data.get("category"),
        tags=data.get("tags"),
        limit=data.get("limit", 20),
    )
    return {"results": results, "count": len(results)}


@memory_bus_router.post("/store")
async def memory_store(data: dict):
    """Store a new memory entry."""
    key = data.get("key", "")
    value = data.get("value", "")
    if not key or not value:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="'key' and 'value' are required")
    bus = get_memory_bus()
    memory_id = await bus.store(
        key=key,
        value=value,
        category=data.get("category", "notes"),
        source=data.get("source", "user"),
        tags=data.get("tags"),
        ttl_seconds=data.get("ttl_seconds"),
    )
    return {"status": "stored", "id": memory_id}


@memory_bus_router.get("/recall/{key}")
async def memory_recall(key: str, category: str = ""):
    """Quick recall of a memory value by key."""
    bus = get_memory_bus()
    cat = category if category else None
    value = await bus.recall(key, category=cat)
    if value is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Memory key '{key}' not found")
    return {"key": key, "value": value}


@memory_bus_router.delete("/forget/{key}")
async def memory_forget(key: str, category: str = ""):
    """Delete a memory by key."""
    bus = get_memory_bus()
    cat = category if category else None
    found = await bus.forget(key, category=cat)
    if not found:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Memory key '{key}' not found")
    return {"status": "forgotten", "key": key}


@memory_bus_router.get("/category/{category}")
async def memory_category(category: str, limit: int = 50):
    """List all memories in a category."""
    bus = get_memory_bus()
    results = await bus.list_by_category(category, limit=limit)
    return {"category": category, "count": len(results), "entries": results}


@memory_bus_router.post("/migrate-legacy")
async def memory_migrate_legacy():
    """Migrate data from legacy long_term.json into MemoryBus."""
    bus = get_memory_bus()
    result = bus.load_legacy_memory()
    return result
