"""
FastAPI routes for social media automation.
Uses database DAOs for storing trends, scripts, videos, and posts.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
from . import TrendResearch, ScriptGenerator, VideoAssembler, ContentPoster
from database import social_dao, analytics_dao

router = APIRouter()

trend_research = TrendResearch()
script_generator = ScriptGenerator()
video_assembler = VideoAssembler()
content_poster = ContentPoster()


class ScriptRequest(BaseModel):
    topic: str
    format: str = "youtube_shorts"
    tone: str = "professional"


class RenderRequest(BaseModel):
    script_id: str


class PostRequest(BaseModel):
    video_id: str
    platforms: list[str]


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


@router.post("/generate-script")
async def generate_script(request: ScriptRequest):
    """Generate a content script and store in DB."""
    try:
        script = await script_generator.generate(
            topic=request.topic,
            format=request.format,
            tone=request.tone,
        )

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

        await analytics_dao.log_activity(
            "content", "script_generated",
            f"Script for '{request.topic[:50]}' ({request.format})"
        )
        return {"script_id": script_id, "script": script}
    except Exception as e:
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
async def render_video(request: RenderRequest):
    """Render a video from a stored script."""
    try:
        script_id = int(request.script_id)
        script = await social_dao.get_script(script_id)
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        # Update script to rendering
        await social_dao.update_script_status(script_id, "rendering")

        # Parse JSON fields from the database
        sections = json.loads(script.get("sections", "[]")) if isinstance(script.get("sections"), str) else script.get("sections", [])
        script_text = script.get("script_content", "")

        output_path = f"/tmp/barq_video_{script_id}.mp4"
        video_path = await video_assembler.render(
            script={
                "sections": sections,
                "script": script_text,
            },
            output_path=output_path,
        )

        # Store video in DB
        video_id = await social_dao.insert_video({
            "script_id": script_id,
            "title": script.get("title", "Untitled"),
            "file_path": str(video_path),
            "status": "completed",
        })

        await social_dao.update_script_status(script_id, "rendered")
        await analytics_dao.log_activity(
            "content", "video_rendered", f"Video rendered for script #{script_id}"
        )

        return {"video_id": video_id, "status": "rendered", "video_path": str(video_path)}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid script_id: must be an integer")
    except HTTPException:
        raise
    except Exception as e:
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
async def post_content(request: PostRequest):
    """Post content to specified platforms."""
    try:
        video_id = int(request.video_id)
        video = await social_dao.get_video(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        result = await content_poster.post(
            video_path=video.get("file_path", ""),
            title=video.get("title", "Generated Content"),
            description="Automatically generated by BARQ",
            platforms=request.platforms,
        )

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

        await analytics_dao.log_activity(
            "content", "content_posted",
            f"Posted video #{video_id} to {', '.join(request.platforms)}"
        )
        return {"video_id": video_id, "results": result.get("results", {})}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid video_id: must be an integer")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline")
async def pipeline_stats():
    """Get content pipeline stage counts from the database."""
    try:
        counts = await social_dao.get_pipeline_counts()
        return {"pipeline": counts}
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
