"""
FastAPI routes for job search automation.
Uses database DAOs for all CRUD operations.
"""

import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from database import analytics_dao, db_connection, jobs_dao

from . import (
    FollowUpAutomation, JobApplier, JobEvaluator, JobScanner,
    ResponseTracker, get_pipeline_progress, get_pipeline_settings, run_pipeline,
)
from .scanner import get_scan_progress, set_scan_error

router = APIRouter()

scanner = JobScanner()
evaluator = JobEvaluator()
applier = JobApplier()
response_tracker = ResponseTracker()
followup_automation = FollowUpAutomation()


class ApproveRequest(BaseModel):
    job_id: str


async def _run_scan():
    """Background scan that runs in a separate asyncio task."""
    try:
        jobs = await scanner.scan_all(
            keywords=["software engineer", "developer", "full stack"],
            location="remote",
        )
        count = 0
        for job in jobs[:50]:
            # Insert job listing
            listing_id = await jobs_dao.insert_job_listing(job)
            # Insert evaluation data if the scanner already evaluated it
            if "overall_score" in job:
                try:
                    await jobs_dao.insert_evaluation({
                        "job_listing_id": listing_id,
                        "overall_score": float(job.get("overall_score", 3.0)),
                        "match_percentage": float(job.get("match_percentage", 0)),
                        "reasoning": job.get("reasoning", ""),
                        "pros": json.dumps(job.get("pros", [])),
                        "cons": json.dumps(job.get("cons", [])),
                        "evaluated_by": "scanner",
                    })
                except Exception as eval_err:
                    print(f"[Scan] Failed to insert evaluation for job #{listing_id}: {eval_err}")
            count += 1

        source_boards = len(set(
            j.get("source_board", "") or j.get("source", "")
            for j in jobs if j.get("source_board") or j.get("source")
        ))
        await analytics_dao.log_activity(
            "job", "scan",
            f"Scanned {count} new job listings from {source_boards} boards"
        )
    except Exception as e:
        set_scan_error(f"Scan failed: {e}")
        await analytics_dao.log_activity("job", "scan_error", str(e), severity="error")


@router.post("/scan")
async def scan_jobs(background_tasks: BackgroundTasks):
    """Trigger a scan of all job boards in the background with real-time progress tracking."""
    # Don't start a new scan if one is already running
    progress = get_scan_progress()
    if progress["status"] in ("scanning", "evaluating"):
        return {"status": "already_running", "message": "A scan is already in progress", "progress": progress}

    # Reset and start scan as a background task
    background_tasks.add_task(_run_scan)

    return {
        "status": "started",
        "message": "Scan started in background",
    }


@router.get("/scan/progress")
async def scan_progress():
    """Get real-time progress of the current scan operation."""
    progress = get_scan_progress()
    return progress


@router.get("/matches")
async def get_matches(min_score: float = 3.0, limit: int = 20):
    """Get evaluated job matches from the database."""
    try:
        matches = await jobs_dao.get_top_matches(min_score=min_score, limit=limit)
        return {
            "matches": [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "company": m["company"],
                    "location": m.get("location", ""),
                    "salary_min": m.get("salary_min", 0),
                    "salary_max": m.get("salary_max", 0),
                    "match_score": m.get("overall_score", 0),
                    "match_percentage": m.get("match_percentage", 0),
                    "pros": m.get("pros", "[]"),
                    "cons": m.get("cons", "[]"),
                    "reasoning": m.get("reasoning", ""),
                    "source": m.get("source_board", ""),
                    "status": "new",
                }
                for m in matches
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve")
async def approve_application(request: ApproveRequest):
    """Approve a job for automated application."""
    try:
        job_id = int(request.job_id)
        app_id = await jobs_dao.insert_application({
            "job_listing_id": job_id,
            "status": "queued",
            "application_type": "auto",
        })
        await analytics_dao.log_activity(
            "job", "approve", f"Application queued for job listing #{job_id}"
        )
        return {
            "status": "approved",
            "application_id": app_id,
            "job_id": request.job_id,
            "message": "Application queued for processing",
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id: must be an integer")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/applications")
async def get_applications(status: str = "", limit: int = 50):
    """Get applications, optionally filtered by status."""
    try:
        if status:
            apps = await jobs_dao.get_applications_by_status(status, limit)
        else:
            apps = await jobs_dao.get_applications_by_status("queued", limit)
        return {"applications": apps, "count": len(apps)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Response Rate Analytics ────────────────────────────────────────


@router.get("/analytics/responses")
async def get_response_analytics():
    """Get comprehensive response rate analytics."""
    try:
        analytics = await response_tracker.get_response_analytics()
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/responses/record")
async def record_response(data: dict):
    """Record a response for an application (interview, rejection, offer)."""
    try:
        result = await response_tracker.record_response(
            application_id=data["application_id"],
            response_type=data["response_type"],
            response_text=data.get("response_text"),
            interview_date=data.get("interview_date"),
        )
        return result
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Follow-Up Automation ────────────────────────────────────────────


@router.get("/followups/candidates")
async def get_followup_candidates():
    """Get applications that need follow-up (submitted > 14 days, no response)."""
    try:
        candidates = await response_tracker.get_followup_candidates()
        return {"candidates": candidates, "count": len(candidates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/followups/schedule")
async def schedule_followups():
    """Check all applications and generate follow-up drafts."""
    try:
        scheduled = await followup_automation.schedule_followups()
        return {"scheduled": scheduled, "count": len(scheduled)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/followups/send")
async def send_followup(data: dict):
    """Mark a follow-up as sent for an application."""
    try:
        result = await followup_automation.send_followup(
            application_id=data["application_id"],
            followup_number=data.get("followup_number", 1),
        )
        return result
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/followups/history")
async def get_followup_history():
    """Get follow-up history."""
    try:
        history = await response_tracker.get_followup_history()
        return {"history": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Resume Upload ─────────────────────────────────────────────────


class ResumeUploadResponse(BaseModel):
    status: str
    message: str
    path: str = ""


@router.post("/resume/upload", summary="Upload a resume file to replace ~/career-ops/cv.md")
async def upload_resume(data: dict):
    """
    Upload resume content (markdown text) and save it to ~/career-ops/cv.md.
    The pipeline and resume parser will use this file for job matching.
    """
    import os
    from pathlib import Path

    try:
        content = data.get("content", "")
        if not content or len(content.strip()) < 50:
            raise HTTPException(status_code=400, detail="Resume content must be at least 50 characters")

        from .resume_parser import DEFAULT_RESUME_PATH
        path = Path(DEFAULT_RESUME_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        from .resume_parser import clear_parse_cache
        clear_parse_cache()

        await analytics_dao.log_activity("job", "resume_upload", "Resume updated via upload")

        return {"status": "saved", "message": "Resume saved successfully", "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resume", summary="Get the current resume content and parse status")
async def get_resume():
    """Get the current resume file content and parsed data."""
    try:
        from .resume_parser import DEFAULT_RESUME_PATH, parse_resume
        parsed = parse_resume()
        path_exists = bool(parsed.get("raw_md"))
        return {
            "exists": path_exists,
            "path": DEFAULT_RESUME_PATH,
            "parsed": {
                "full_name": parsed.get("full_name", ""),
                "email": parsed.get("email", ""),
                "skills_count": len(parsed.get("skills", [])),
                "experience_count": len(parsed.get("experience", [])),
                "education_count": len(parsed.get("education", [])),
            },
            "char_count": len(parsed.get("raw_md", "")),
            "error": parsed.get("_error", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Pipeline Endpoints ────────────────────────────────────────────

class PipelineSettingsRequest(BaseModel):
    mode: str = "notify"
    auto_apply: bool = False
    max_per_run: int = 10
    generate_pdf: bool = True
    send_telegram: bool = True
    min_match_score: int = 60


@router.post("/pipeline/run")
async def run_application_pipeline(settings: Optional[PipelineSettingsRequest] = None):
    """
    Execute the end-to-end job application pipeline.

    Processes queued/approved jobs by:
    1. Parsing resume from ~/career-ops/cv.md
    2. Optimizing resume for each specific job
    3. Generating tailored cover letters
    4. Generating PDF documents
    5. Sending Telegram notification with job link + docs
       OR auto-applying via Playwright

    Returns real-time progress via GET /jobs/pipeline/progress
    """
    import asyncio

    # Check if pipeline is already running
    progress = get_pipeline_progress()
    if progress["status"] == "running":
        return {"status": "already_running", "message": "Pipeline is already running", "progress": progress}

    cfg = settings.model_dump() if settings else {}

    # Run pipeline as a background task
    async def _run():
        try:
            await run_pipeline(cfg)
        except Exception as e:
            print(f"[Routes] Pipeline background task error: {e}")

    asyncio.create_task(_run())

    return {
        "status": "started",
        "message": "Job application pipeline started in background",
        "settings": cfg or get_pipeline_settings(),
    }


@router.get("/pipeline/progress")
async def pipeline_progress():
    """Get real-time progress of the running pipeline."""
    return get_pipeline_progress()


@router.get("/pipeline/settings")
async def pipeline_settings():
    """Get current pipeline settings."""
    return get_pipeline_settings()


@router.get("/status")
async def job_status():
    """Get current job search status from the database."""
    try:
        counts = await jobs_dao.get_application_count_by_status()
        status_map = {row["status"]: row["count"] for row in counts}
        row = await db_connection.fetch_one(
            "SELECT COUNT(*) as count FROM job_listings"
        )
        total_scanned = row["count"] if row else 0
        return {
            "is_scanning": False,
            "total_jobs_scanned": total_scanned,
            "pending_review": status_map.get("ready_for_review", 0),
            "applications_queued": status_map.get("queued", 0),
            "applications_submitted": status_map.get("submitted", 0),
            "interviews": status_map.get("interview", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
