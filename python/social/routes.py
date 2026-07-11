"""
FastAPI routes for social media automation.
Uses database DAOs for storing trends, scripts, videos, and posts.
"""

import json
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from database import analytics_dao, social_dao

from . import (
    ContentCalendar,
    ContentPoster,
    ScriptGenerator,
    TrendResearch,
    VideoAssembler,
)

router = APIRouter()


async def _auto_reset_progress(delay: int = 5):
    """Reset generation progress to idle after a delay."""
    import asyncio
    await asyncio.sleep(delay)
    if _generation_progress["status"] == "complete":
        reset_generation_progress()

# ─── Content generation progress tracker ──────────────────────────────

GENERATION_PHASES = [
    "Researching trends",
    "Drafting script",
    "Rendering video",
    "Posting content",
]

_generation_progress: dict[str, Any] = {
    "status": "idle",           # idle | scripting | rendering | posting | complete | error
    "phase": "",
    "phase_index": 0,
    "total_phases": 4,
    "progress_pct": 0,
    "message": "",
    "started_at": None,
    "elapsed_seconds": 0,
}


def get_generation_progress() -> dict[str, Any]:
    """Return a snapshot of content generation progress."""
    p = _generation_progress
    if p["started_at"]:
        p["elapsed_seconds"] = round(time.time() - p["started_at"], 1)
    return dict(p)


def set_generation_progress(status: str, phase: str, pct: float, message: str = ""):
    """Update generation progress state."""
    p = _generation_progress
    p["status"] = status
    p["phase"] = phase
    p["progress_pct"] = round(pct, 1)
    p["message"] = message or phase
    if not p["started_at"]:
        p["started_at"] = time.time()


def reset_generation_progress():
    """Reset progress to idle."""
    p = _generation_progress
    p["status"] = "idle"
    p["phase"] = ""
    p["phase_index"] = 0
    p["progress_pct"] = 0
    p["message"] = ""
    p["started_at"] = None
    p["elapsed_seconds"] = 0


trend_research = TrendResearch()
script_generator = ScriptGenerator()
video_assembler = VideoAssembler()
content_poster = ContentPoster()
content_calendar = ContentCalendar()


class ScriptRequest(BaseModel):
    topic: str
    format: str = "youtube_shorts"
    tone: str = "professional"


class RenderRequest(BaseModel):
    script_id: str


class PostRequest(BaseModel):
    video_id: str
    platforms: list[str]


class ScheduleRequest(BaseModel):
    video_id: int
    platforms: list[str]
    scheduled_date: str  # ISO datetime or date
    title: str = ""
    description: str = ""


class CalendarMonthRequest(BaseModel):
    year: int
    month: int


@router.get("/trends")
async def get_trends():
    """Get current trending topics, stored in DB."""
    try:
        # Fetch fresh trends
        fresh_trends = await trend_research.get_trends()

        # Store in database
        inserted = 0
        for trend in fresh_trends:
            await social_dao.insert_trend(trend)
            inserted += 1

        # Return recent trends from DB
        recent = await social_dao.get_recent_trends(limit=20)

        await analytics_dao.log_activity(
            "content", "trends_fetched", f"Stored {inserted} new trends"
        )
        return {"trends": recent, "new_trends": inserted}
    except Exception as e:
        await analytics_dao.log_activity(
            "content", "trends_error", str(e), severity="error"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generation/progress")
async def generation_progress():
    """Get real-time progress of any active content generation operation."""
    return get_generation_progress()


@router.post("/generate-script")
async def generate_script(request: ScriptRequest, background_tasks: BackgroundTasks):
    """Generate a content script and store in DB."""
    set_generation_progress("scripting", GENERATION_PHASES[1], 10, f"Scripting: {request.topic[:50]}...")
    try:
        script = await script_generator.generate(
            topic=request.topic,
            format=request.format,
            tone=request.tone,
        )

        set_generation_progress("scripting", GENERATION_PHASES[1], 70, "Storing script to database...")

        # Store in database
        script_id = await social_dao.insert_script({
            "title": request.topic,
            "topic": request.topic,
            "format": request.format,
            "tone": request.tone,
            "script_content": script.get("script", ""),
            "sections": script.get("sections", "[]"),
            "visual_cues": script.get("visual_cues", "[]"),
            "score": script.get("score", 0),
            "status": "draft",
        })

        set_generation_progress("complete", "Script drafted", 100, f"Script #{script_id} ready")
        # Auto-reset after 5s
        background_tasks.add_task(_auto_reset_progress, 5)

        await analytics_dao.log_activity(
            "content", "script_generated",
            f"Script for '{request.topic[:50]}' ({request.format})"
        )
        return {"script_id": script_id, "script": script}
    except Exception as e:
        _generation_progress["status"] = "error"
        _generation_progress["message"] = str(e)
        await analytics_dao.log_activity(
            "content", "script_error", str(e), severity="error"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scripts")
async def get_scripts(status: str = "", limit: int = 50):
    """Get content scripts by status."""
    try:
        if status:
            scripts = await social_dao.get_scripts_by_status(status, limit)
        else:
            scripts = await social_dao.get_scripts_by_status("draft", limit)
        return {"scripts": scripts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/render-video")
async def render_video(request: RenderRequest, background_tasks: BackgroundTasks):
    """Render a video from a stored script."""
    set_generation_progress("rendering", GENERATION_PHASES[2], 10, f"Preparing render for script #{request.script_id}...")
    try:
        script_id = int(request.script_id)
        script = await social_dao.get_script(script_id)
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        set_generation_progress("rendering", GENERATION_PHASES[2], 25, "Loading script sections...")

        # Update script to rendering
        await social_dao.update_script_status(script_id, "rendering")

        # Parse JSON fields from the database
        sections = json.loads(script.get("sections", "[]")) if isinstance(script.get("sections"), str) else script.get("sections", [])
        script_text = script.get("script_content", "")

        set_generation_progress("rendering", GENERATION_PHASES[2], 40, "Assembling video assets...")

        output_path = f"/tmp/barq_video_{script_id}.mp4"
        video_path = await video_assembler.render(
            script={
                "sections": sections,
                "script": script_text,
            },
            output_path=output_path,
        )

        set_generation_progress("rendering", GENERATION_PHASES[2], 80, "Finalizing video...")

        # Store video in DB
        video_id = await social_dao.insert_video({
            "script_id": script_id,
            "title": script.get("title", "Untitled"),
            "file_path": str(video_path),
            "status": "completed",
        })

        await social_dao.update_script_status(script_id, "rendered")

        set_generation_progress("complete", "Video rendered", 100, f"Video #{video_id} ready")
        background_tasks.add_task(_auto_reset_progress, 5)

        await analytics_dao.log_activity(
            "content", "video_rendered", f"Video rendered for script #{script_id}"
        )

        return {"video_id": video_id, "status": "rendered", "video_path": str(video_path)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid script_id: must be an integer")
    except HTTPException:
        raise
    except Exception as e:
        _generation_progress["status"] = "error"
        _generation_progress["message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/videos")
async def get_videos(status: str = "", limit: int = 50):
    """Get videos by status."""
    try:
        if status:
            videos = await social_dao.get_videos_by_status(status, limit)
        else:
            videos = await social_dao.get_videos_by_status("completed", limit)
        return {"videos": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/post")
async def post_content(request: PostRequest, background_tasks: BackgroundTasks):
    """Post content to specified platforms."""
    platforms_str = ", ".join(request.platforms)
    set_generation_progress("posting", GENERATION_PHASES[3], 15, f"Preparing post to {platforms_str}...")
    try:
        video_id = int(request.video_id)
        video = await social_dao.get_video(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        set_generation_progress("posting", GENERATION_PHASES[3], 30, f"Connecting to {platforms_str}...")

        result = await content_poster.post(
            video_path=video.get("file_path", ""),
            title=video.get("title", "Generated Content"),
            description="Automatically generated by BARQ",
            platforms=request.platforms,
        )

        set_generation_progress("posting", GENERATION_PHASES[3], 80, "Recording to database...")

        # Record posts in DB for each platform
        for platform in request.platforms:
            platform_result = result.get("results", {}).get(platform, {})
            await social_dao.insert_post({
                "video_id": video_id,
                "platform": platform,
                "title": video.get("title", "Untitled"),
                "description": "",
                "status": "posted" if platform_result.get("status") != "error" else "failed",
                "platform_post_id": platform_result.get("id", ""),
            })

        set_generation_progress("complete", "Content posted", 100, f"Posted to {platforms_str}")
        background_tasks.add_task(_auto_reset_progress, 5)

        await analytics_dao.log_activity(
            "content", "content_posted",
            f"Posted video #{video_id} to {platforms_str}"
        )
        return {"video_id": video_id, "results": result.get("results", {})}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid video_id: must be an integer")
    except HTTPException:
        raise
    except Exception as e:
        _generation_progress["status"] = "error"
        _generation_progress["message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline")
async def pipeline_stats():
    """Get content pipeline stage counts from the database."""
    try:
        counts = await social_dao.get_pipeline_counts()
        return {"pipeline": counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Content Calendar ────────────────────────────────────────────────────


@router.get("/calendar/month")
async def calendar_month(year: int = 0, month: int = 0):
    """
    Get calendar overview for a month.
    Defaults to current month if year/month not provided.
    """
    try:
        from datetime import date
        today = date.today()
        y = year or today.year
        m = month or today.month
        calendar = await content_calendar.get_calendar_month(y, m)
        return calendar
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/week")
async def calendar_week(start: str = ""):
    """
    Get calendar overview for a week.
    Defaults to current week if start not provided.
    """
    try:
        from datetime import date
        if not start:
            today = date.today()
            start = today.isoformat()
        calendar = await content_calendar.get_calendar_week(start)
        return calendar
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calendar/schedule")
async def schedule_post(request: ScheduleRequest):
    """Schedule a video for posting at a future date."""
    try:
        result = await content_calendar.schedule_post(
            video_id=request.video_id,
            platforms=request.platforms,
            scheduled_date=request.scheduled_date,
            title=request.title,
            description=request.description,
        )
        await analytics_dao.log_activity(
            "content", "post_scheduled",
            f"Scheduled video #{request.video_id} for {request.scheduled_date[:10]} on {', '.join(request.platforms)}"
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/calendar/schedule/{post_id}")
async def cancel_scheduled_post(post_id: int):
    """Cancel a scheduled post."""
    try:
        await content_calendar.cancel_scheduled_post(post_id)
        return {"status": "cancelled", "post_id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/upcoming")
async def upcoming_schedule(days: int = 14):
    """Get upcoming scheduled posts for the next N days."""
    try:
        schedule = await content_calendar.get_upcoming_schedule(days=days)
        return {"upcoming": schedule, "total": len(schedule)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/stats")
async def calendar_stats():
    """Get calendar statistics."""
    try:
        stats = await content_calendar.get_calendar_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def social_status():
    """Get social media module status."""
    try:
        platform_status = await content_poster.get_platform_status()
        pipeline = await social_dao.get_pipeline_counts()
        return {
            "platforms": platform_status,
            "pipeline": pipeline,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
