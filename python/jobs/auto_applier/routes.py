"""
FastAPI routes for the Auto Applier module.

Integrates with the existing BARQ FastAPI server at /api/jobs/auto-apply/...
"""

from typing import Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from database import jobs_dao
from .config import CONFIG, PROFILE
from .pipeline.orchestrator import AutoApplyPipeline

router = APIRouter(prefix="/auto-apply", tags=["auto-apply"])

# Singleton pipeline instance
_pipeline: Optional[AutoApplyPipeline] = None
_pipeline_progress: dict[str, Any] = {
    "status": "idle",
    "message": "",
    "jobs_found": 0,
    "jobs_processed": 0,
    "jobs_submitted": 0,
    "current_job": "",
}


def get_pipeline() -> AutoApplyPipeline:
    """Get or create the pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = AutoApplyPipeline()
    return _pipeline


# ─── Schemas ──────────────────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    job_url: str
    company: str = ""
    title: str = ""
    job_context: str = ""


class BatchApplyRequest(BaseModel):
    jobs: list[ApplyRequest]


class PipelineSettingsRequest(BaseModel):
    max_applications_per_run: int = 10
    match_threshold: int = 60
    pause_before_submit: bool = False
    interactive_mode: bool = False


# ─── Status ───────────────────────────────────────────────────────────────

@router.get("/status")
async def auto_apply_status():
    """Get auto applier status and configuration."""
    return {
        "pipeline": _pipeline_progress,
        "config": {
            "ollama_model": CONFIG.ollama_model,
            "ollama_host": CONFIG.ollama_host,
            "max_applications_per_run": CONFIG.max_applications_per_run,
            "match_threshold": CONFIG.match_threshold,
            "pause_before_submit": CONFIG.pause_before_submit,
            "headless": CONFIG.headless,
            "telegram_configured": bool(CONFIG.telegram_bot_token),
            "linkedin_configured": bool(CONFIG.linkedin_email),
            "tinyfish_configured": bool(CONFIG.tinyfish_api_key),
        },
        "profile": {
            "name": PROFILE.full_name,
            "education": PROFILE.education,
            "seeking": PROFILE.seeking,
            "skills_count": len(PROFILE.skills),
        },
    }


@router.get("/profile")
async def get_profile():
    """Get the candidate profile for form filling."""
    return {
        "full_name": PROFILE.full_name,
        "email": PROFILE.email,
        "education": PROFILE.education,
        "skills": PROFILE.skills,
        "seeking": PROFILE.seeking,
        "experience_count": len(PROFILE.experiences),
    }


# ─── Apply ────────────────────────────────────────────────────────────────

@router.post("/apply")
async def apply_to_job(request: ApplyRequest):
    """Apply to a single job URL."""
    if _pipeline_progress["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    pipeline = get_pipeline()
    _pipeline_progress["status"] = "running"
    _pipeline_progress["current_job"] = request.title or request.job_url[:60]

    try:
        result = await pipeline.engine.apply_to_job(
            job_url=request.job_url,
            company=request.company,
            title=request.title,
            job_context=request.job_context,
        )
        _pipeline_progress["status"] = "complete"
        _pipeline_progress["jobs_processed"] = 1
        _pipeline_progress["jobs_submitted"] = 1 if result.get("submitted") else 0
        return result
    except Exception as exc:
        _pipeline_progress["status"] = "error"
        _pipeline_progress["message"] = str(exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/apply/batch")
async def apply_batch(request: BatchApplyRequest, background_tasks: BackgroundTasks):
    """Apply to multiple jobs in the background."""
    if _pipeline_progress["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    pipeline = get_pipeline()
    jobs = [j.model_dump() for j in request.jobs]

    async def _run():
        _pipeline_progress["status"] = "running"
        _pipeline_progress["jobs_found"] = len(jobs)
        try:
            results = await pipeline.engine.apply_batch(jobs)
            _pipeline_progress["jobs_processed"] = len(results)
            _pipeline_progress["jobs_submitted"] = sum(1 for r in results if r.get("submitted"))
            _pipeline_progress["status"] = "complete"
        except Exception as exc:
            _pipeline_progress["status"] = "error"
            _pipeline_progress["message"] = str(exc)

    import asyncio
    asyncio.create_task(_run())

    return {
        "status": "started",
        "jobs_queued": len(jobs),
        "message": f"Processing {len(jobs)} jobs in background",
    }


@router.get("/progress")
async def auto_apply_progress():
    """Get real-time progress of the current auto-apply run."""
    return dict(_pipeline_progress)


# ─── Pipeline ─────────────────────────────────────────────────────────────

@router.post("/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    """Run the full auto-apply pipeline (discovery → digest → apply)."""
    if _pipeline_progress["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    pipeline = get_pipeline()

    async def _run_pipeline():
        _pipeline_progress["status"] = "running"
        try:
            result = await pipeline.run(send_digest=True)
            _pipeline_progress.update({
                "status": "complete",
                "jobs_found": result.get("jobs_found", 0),
                "jobs_processed": result.get("jobs_processed", 0),
                "jobs_submitted": result.get("jobs_submitted", 0),
            })
        except Exception as exc:
            _pipeline_progress["status"] = "error"
            _pipeline_progress["message"] = str(exc)

    import asyncio
    asyncio.create_task(_run_pipeline())

    return {"status": "started", "message": "Auto-apply pipeline started in background"}


@router.post("/pipeline/settings")
async def update_pipeline_settings(settings: PipelineSettingsRequest):
    """Update pipeline settings."""
    CONFIG.max_applications_per_run = settings.max_applications_per_run
    CONFIG.match_threshold = settings.match_threshold
    CONFIG.pause_before_submit = settings.pause_before_submit
    CONFIG.interactive_mode = settings.interactive_mode
    return {"status": "updated", "settings": settings.model_dump()}


# ─── Telegram ─────────────────────────────────────────────────────────────

@router.post("/telegram/start")
async def start_telegram_bot(background_tasks: BackgroundTasks):
    """Start the Telegram bot in polling mode."""
    pipeline = get_pipeline()

    async def _start():
        await pipeline.start_telegram()

    import asyncio
    asyncio.create_task(_start())

    return {"status": "started", "message": "Telegram bot starting..."}


@router.post("/telegram/send-test")
async def send_telegram_test():
    """Send a test job card to Telegram."""
    pipeline = get_pipeline()
    sent = await pipeline.telegram.send_job_card(
        job_id="test-001",
        company="Example Corp",
        title="Senior Software Engineer",
        score=85,
        url="https://example.com/jobs/test",
        reason="Test card — no actual job here",
    )
    return {"sent": sent}


# ─── EvoMap ──────────────────────────────────────────────────────────────

@router.get("/failures")
async def get_recent_failures():
    """Get recent failure entries from the EvoMap log."""
    from .failure.evo_logger import EvoLogger
    evo = EvoLogger()
    return {"failures": evo.get_recent_failures(20)}
