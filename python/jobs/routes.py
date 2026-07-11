"""
FastAPI routes for job search automation.
Uses database DAOs for all CRUD operations.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from database import analytics_dao, db_connection, jobs_dao

from . import FollowUpAutomation, JobApplier, JobEvaluator, JobScanner, ResponseTracker
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
            await jobs_dao.insert_job_listing(job)
            count += 1

        await analytics_dao.log_activity(
            "job", "scan",
            f"Scanned {count} new job listings from {len(set(j.get('source_board', '') or j.get('source', '') for j in jobs))} boards"
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
