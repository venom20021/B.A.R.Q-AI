"""
FastAPI routes for the Deep Research Agent.

Endpoints:
  POST /research/deep - Start a deep research session
  GET  /research/deep/progress - Get current progress of active session
  GET  /research/deep/history - Get past research results
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import analytics_dao

from .deep_research_agent import DeepResearchAgent, ResearchDepth

router = APIRouter()

# Singleton agent instance
_research_agent = DeepResearchAgent()


class DeepResearchRequest(BaseModel):
    topic: str
    depth: str = "standard"  # basic, standard, deep
    save_as_note: bool = False


@router.post("/deep", summary="Start a deep research session")
async def start_deep_research(request: DeepResearchRequest):
    """Start a multi-agent deep research session on a topic.

    The research runs synchronously and returns the complete result
    with all progress cards and the final report.
    """
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")

    if request.depth not in ("basic", "standard", "deep"):
        raise HTTPException(status_code=400, detail="Depth must be 'basic', 'standard', or 'deep'")

    try:
        result = await _research_agent.research(
            topic=request.topic,
            depth=request.depth,
        )

        # Log the research activity (type must match activity_log CHECK constraint)
        await analytics_dao.log_activity(
            "analytics",
            "deep_research",
            f"Deep research: {request.topic[:100]} ({request.depth})",
        )

        # Optionally save as a note
        note_id = None
        if request.save_as_note and result.report:
            try:
                from memory_knowledge.routes import NoteItem, create_note

                note = NoteItem(
                    title=f"Research: {request.topic[:80]}",
                    content=result.report,
                    tags=[request.depth, "deep-research", "auto-generated"],
                )
                note_result = await create_note(note)
                note_id = note_result.get("note", {}).get("id")
            except Exception:
                pass

        response = result.to_dict()
        response["note_id"] = note_id
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deep/progress", summary="Get current research progress")
async def get_research_progress():
    """Get the progress of the currently running research session, if any."""
    progress = _research_agent.get_progress()
    if not progress:
        return {"active": False, "progress": None}
    return {"active": True, "progress": progress}


@router.get("/deep/history", summary="Get past research results")
async def get_research_history(limit: int = 5):
    """Get recent deep research activities from the activity log."""
    try:
        activities = await analytics_dao.get_recent_activity(limit=20)
        research_activities = [
            a for a in activities
            if a.get("type") == "analytics" and a.get("action") == "deep_research"
        ]
        return {
            "history": [
                {
                    "topic": a.get("description", "").replace("Deep research: ", ""),
                    "timestamp": a.get("created_at"),
                    "id": a.get("id"),
                }
                for a in research_activities[:limit]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
