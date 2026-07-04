"""
FastAPI routes for job search automation.
Uses database DAOs for all CRUD operations.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from . import JobScanner, JobEvaluator, JobApplier
from database import jobs_dao, analytics_dao, db_connection, db_connection

router = APIRouter()

scanner = JobScanner()
evaluator = JobEvaluator()
applier = JobApplier()


class ApproveRequest(BaseModel):
    job_id: str


@router.post("/scan")
async def scan_jobs():
    """Trigger a scan of all job boards and store results in DB."""
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
            "job", "scan", f"Scanned {count} new job listings from {len(set(j.get('source_board', '') for j in jobs))} boards"
        )
        return {"jobs_found": count, "message": f"Stored {count} jobs in database"}
    except Exception as e:
        await analytics_dao.log_activity("job", "scan_error", str(e), severity="error")
        raise HTTPException(status_code=500, detail=str(e))


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
