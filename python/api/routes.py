"""
API v1 Routes — all job automation endpoints under /api/v1.

Supports resume management, job search, AI matching, optimization,
cover letters, cold emails, auto-apply, dashboard stats, and funnel data.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from database import analytics_dao, jobs_dao
from jobs import JobApplier, JobEvaluator, JobScanner
from jobs.cold_mail import ColdEmailWriter
from jobs.cover_letter import CoverLetterGenerator
from jobs.matcher import JobMatcher
from jobs.optimizer import ResumeOptimizer
from jobs.resume_parser import clear_parse_cache, parse_resume

router = APIRouter(prefix="/api/v1", tags=["Jobs v1"])

# Instantiate all modules
scanner = JobScanner()
evaluator = JobEvaluator()
applier = JobApplier()
matcher = JobMatcher()
optimizer = ResumeOptimizer()
cover_letter_gen = CoverLetterGenerator()
cold_mail_writer = ColdEmailWriter()

logger = logging.getLogger("barq.api.v1")


# ─── Models ──────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    keywords: str = Field(default="software engineer", description="Search keywords")
    location: str = Field(default="remote", description="Location filter")
    sources: list[str] = Field(default=["all"], description="Job boards to search")


class MatchRequest(BaseModel):
    job_id: int
    resume_path: str | None = None


class OptimizeRequest(BaseModel):
    job_id: int
    resume_path: str | None = None


class CoverLetterRequest(BaseModel):
    job_id: int
    resume_path: str | None = None


class ColdMailRequest(BaseModel):
    job_id: int
    recipient_name: str | None = None
    recipient_email: str | None = None
    reason: str = Field(default="I found this role and my background aligns well")
    tone: str = Field(default="professional", pattern="^(professional|casual|enthusiastic)$")


class ApplyRequest(BaseModel):
    job_id: int
    auto_fill: bool = Field(default=True, description="Auto-fill the application form")


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    """System health check."""
    return {
        "status": "ok",
        "service": "barq-jobs",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Resume ──────────────────────────────────────────────────────────────────

@router.post("/resume/upload")
async def upload_resume(resume_path: str | None = None):
    """Upload/parse the resume markdown file."""
    try:
        result = parse_resume(resume_path)
        return {"status": "parsed", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resume")
async def get_resume():
    """Get the parsed resume data."""
    try:
        result = parse_resume()
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/refresh")
async def refresh_resume():
    """Clear cache and re-parse the resume."""
    clear_parse_cache()
    try:
        result = parse_resume()
        return {"status": "refreshed", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Jobs ────────────────────────────────────────────────────────────────────

@router.post("/jobs/search")
async def search_jobs(request: SearchRequest, background_tasks: BackgroundTasks):
    """Trigger a job search with specified keywords."""
    try:
        results = await scanner.scan_all(
            keywords=[kw.strip() for kw in request.keywords.split(",")],
            location=request.location,
        )
        # Store in database
        count = 0
        for job in results[:50]:
            await jobs_dao.insert_job_listing(job)
            count += 1

        await analytics_dao.log_activity(
            "job", "search", f"Searched '{request.keywords}' — found {count} jobs"
        )
        return {"status": "completed", "jobs_found": count, "jobs": results[:20]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
async def list_jobs(
    status: str | None = None,
    min_score: float | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List all jobs with optional filters."""
    try:
        if min_score is not None:
            matches = await jobs_dao.get_top_matches(min_score=min_score, limit=limit)
            return {"jobs": matches, "count": len(matches)}
        elif source:
            jobs = await jobs_dao.get_jobs_by_source(source, limit=limit)
            return {"jobs": jobs, "count": len(jobs)}
        else:
            jobs = await jobs_dao.get_active_jobs(limit=limit, offset=offset)
            return {"jobs": jobs, "count": len(jobs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}")
async def get_job(job_id: int):
    """Get a single job with its match data."""
    try:
        job = await jobs_dao.get_job_listing(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        evaluation = await jobs_dao.get_evaluation(job_id)
        return {"job": job, "evaluation": evaluation}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Matching ────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/match")
async def match_job(job_id: int, request: MatchRequest | None = None):
    """Run AI matching for a specific job."""
    try:
        job = await jobs_dao.get_job_listing(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        resume = parse_resume(request.resume_path if request else None)
        if resume.get("_error"):
            raise HTTPException(status_code=400, detail=resume["_error"])

        result = await matcher.match(job, resume)

        # Store evaluation in database
        eval_id = await jobs_dao.insert_evaluation({
            "job_listing_id": job_id,
            "overall_score": result["overall_score"] / 20,  # Convert 0-100 to 0-5
            "role_fit_score": result["breakdown"]["skills_match"] / 20,
            "culture_score": result["breakdown"]["experience_match"] / 20,
            "compensation_score": result["breakdown"]["salary_match"] / 20,
            "growth_score": result["breakdown"]["location_match"] / 20,
            "red_flag_score": 0,
            "match_percentage": result["overall_score"],
            "reasoning": result["fit_summary"],
            "pros": json.dumps(result["matching_skills"]),
            "cons": json.dumps(result["missing_skills"]),
            "evaluated_by": "llm",
        })

        return {"status": "matched", "match": result, "evaluation_id": eval_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/batch-match")
async def batch_match_jobs(background_tasks: BackgroundTasks):
    """Match all new/unmatched jobs against the resume."""
    try:
        resume = parse_resume()
        if resume.get("_error"):
            raise HTTPException(status_code=400, detail=resume["_error"])

        jobs = await jobs_dao.get_active_jobs(limit=100)
        results = []

        for job in jobs:
            # Skip already-matched jobs
            existing = await jobs_dao.get_evaluation(job["id"])
            if existing:
                continue

            result = await matcher.match(job, resume)
            results.append(result)

            await jobs_dao.insert_evaluation({
                "job_listing_id": job["id"],
                "overall_score": result["overall_score"] / 20,
                "role_fit_score": result["breakdown"]["skills_match"] / 20,
                "culture_score": result["breakdown"]["experience_match"] / 20,
                "compensation_score": result["breakdown"]["salary_match"] / 20,
                "growth_score": result["breakdown"]["location_match"] / 20,
                "red_flag_score": 0,
                "match_percentage": result["overall_score"],
                "reasoning": result["fit_summary"],
                "pros": json.dumps(result["matching_skills"]),
                "cons": json.dumps(result["missing_skills"]),
                "evaluated_by": "llm",
            })

        return {
            "status": "completed",
            "jobs_matched": len(results),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/matched")
async def get_matched_jobs(min_score: float = 70, limit: int = 20):
    """List jobs with match scores above threshold."""
    try:
        # Convert 0-100 to 0-5 for database
        db_min = min_score / 20
        matches = await jobs_dao.get_top_matches(min_score=db_min, limit=limit)
        return {"jobs": matches, "count": len(matches), "threshold": min_score}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Optimization ────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/optimize")
async def optimize_resume(job_id: int, request: OptimizeRequest | None = None):
    """Generate an optimized resume for a specific job."""
    try:
        job = await jobs_dao.get_job_listing(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        resume = parse_resume(request.resume_path if request else None)
        if resume.get("_error"):
            raise HTTPException(status_code=400, detail=resume["_error"])

        # Get match analysis if available
        evaluation = await jobs_dao.get_evaluation(job_id)
        match_analysis = {
            "overall_score": (evaluation["overall_score"] * 20) if evaluation else 0,
            "missing_skills": json.loads(evaluation.get("cons", "[]")) if evaluation else [],
            "matching_skills": json.loads(evaluation.get("pros", "[]")) if evaluation else [],
            "fit_summary": evaluation.get("reasoning", "") if evaluation else "",
        } if evaluation else None

        result = await optimizer.optimize(resume["raw_md"], job, match_analysis)

        # Store the optimized resume
        from database import jobs_dao as dao
        await dao.insert_document({
            "application_id": 0,  # Will be linked when application is created
            "document_type": "resume",
            "content": result["optimized_md"],
            "format": "markdown",
            "generated_by": "llm",
        })

        return {
            "status": "optimized",
            "optimized_resume": result["optimized_md"],
            "keywords_injected": result["keywords_injected"],
            "changes_made": result["changes_made"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/optimized-resume")
async def get_optimized_resume(job_id: int):
    """Get the optimized resume for a job."""
    # For now, re-optimize on demand
    return await optimize_resume(job_id)


# ─── Cover Letter ────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/cover-letter")
async def generate_cover_letter(job_id: int, request: CoverLetterRequest | None = None):
    """Generate a tailored cover letter for a job."""
    try:
        job = await jobs_dao.get_job_listing(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        resume = parse_resume(request.resume_path if request else None)
        if resume.get("_error"):
            raise HTTPException(status_code=400, detail=resume["_error"])

        cover_letter = await cover_letter_gen.generate(job, resume)

        return {
            "status": "generated",
            "cover_letter": cover_letter,
            "job_id": job_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Cold Email ──────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/cold-mail")
async def generate_cold_mail(job_id: int, request: ColdMailRequest):
    """Generate a cold outreach email for a job."""
    try:
        job = await jobs_dao.get_job_listing(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        resume = parse_resume()
        summary = resume.get("summary", "") or ", ".join(resume.get("skills", [])[:5])

        email = await cold_mail_writer.write(
            company=job.get("company", ""),
            job_title=job.get("title", ""),
            resume_summary=summary[:300],
            reason=request.reason,
            recipient_name=request.recipient_name,
            recipient_email=request.recipient_email,
            tone=request.tone,
        )

        return {
            "status": "generated",
            "email": email,
            "job_id": job_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Applications ────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/resume/pdf")
async def generate_job_resume_pdf(job_id: int):
    """Generate a tailored resume PDF for a job."""
    try:
        job = await jobs_dao.get_job_listing(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        resume = parse_resume()
        if resume.get("_error"):
            raise HTTPException(status_code=400, detail=resume["_error"])

        user_profile = {
            "full_name": resume.get("full_name", ""),
            "email": resume.get("email", ""),
            "phone": resume.get("phone", ""),
            "linkedin_url": resume.get("linkedin_url", ""),
            "github_url": resume.get("github_url", ""),
            "portfolio_url": resume.get("portfolio_url", ""),
            "summary": resume.get("summary", ""),
            "headline": resume.get("headline", ""),
            "skills": resume.get("skills", []),
            "experience": resume.get("experience", []),
            "education": resume.get("education", []),
            "projects": resume.get("projects", []),
        }

        result = await applier.generate_resume_pdf(job, user_profile)

        return {
            "status": result["status"],
            "pdf_path": result.get("pdf_path", ""),
            "backend": result.get("backend", ""),
            "file_size_bytes": result.get("file_size_bytes", 0),
            "resume_text": result.get("resume_text", ""),
            "message": f"Resume PDF generated using {result.get('backend', 'unknown')} backend",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/apply")
async def auto_apply(job_id: int, request: ApplyRequest | None = None):
    """Start auto-fill application (Playwright)."""
    try:
        job = await jobs_dao.get_job_listing(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        resume = parse_resume()
        user_profile = {
            "full_name": resume.get("full_name", ""),
            "email": resume.get("email", ""),
            "phone": resume.get("phone", ""),
            "linkedin_url": resume.get("linkedin_url", ""),
            "portfolio_url": resume.get("portfolio_url", ""),
            "skills": resume.get("skills", []),
            "experience": resume.get("experience", []),
            "education": resume.get("education", []),
        }

        result = await applier.fill_application_form(  # noqa: F841
            form_fields=[],  # Will be detected by Playwright
            user_profile=user_profile,
        )

        # Create application record
        app_id = await jobs_dao.insert_application({
            "job_listing_id": job_id,
            "status": "generating",
            "application_type": "auto",
        })

        return {
            "status": "started",
            "application_id": app_id,
            "message": "Application form fill started. Review before submission.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/applications")
async def list_applications(status: str | None = None, limit: int = 50):
    """List all applications with optional status filter."""
    try:
        if status:
            apps = await jobs_dao.get_applications_by_status(status, limit)
        else:
            apps = await jobs_dao.get_applications_by_status("", limit)
        return {"applications": apps, "count": len(apps)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/applications/{app_id}/status")
async def update_application_status(app_id: int, status: str):
    """Update an application's status."""
    try:
        await jobs_dao.update_application_status(app_id, status)
        return {"status": "updated", "application_id": app_id, "new_status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Dashboard ───────────────────────────────────────────────────────────────

@router.get("/dashboard/stats")
async def dashboard_stats():
    """Aggregate statistics for the dashboard."""
    try:
        counts = await jobs_dao.get_application_count_by_status()
        status_map = {row["status"]: row["count"] for row in counts}

        from database import db_connection
        total_jobs = await db_connection.fetch_one(
            "SELECT COUNT(*) as count FROM job_listings"
        )
        total_matches = await db_connection.fetch_one(
            "SELECT COUNT(*) as count FROM job_evaluations"
        )

        return {
            "total_jobs_scanned": total_jobs["count"] if total_jobs else 0,
            "total_matches": total_matches["count"] if total_matches else 0,
            "applications_draft": status_map.get("draft", 0),
            "applications_queued": status_map.get("queued", 0),
            "applications_submitted": status_map.get("submitted", 0),
            "interviews": status_map.get("interview", 0) + status_map.get("interview_scheduled", 0),
            "offers": status_map.get("offer", 0) + status_map.get("offered", 0),
            "rejections": status_map.get("rejected", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/funnel")
async def dashboard_funnel():
    """Application funnel data."""
    try:
        counts = await jobs_dao.get_application_count_by_status()
        status_map = {row["status"]: row["count"] for row in counts}

        funnel = [
            {"stage": "Scanned", "count": status_map.get("new", 0) + status_map.get("draft", 0), "pct": 0},
            {"stage": "Matched", "count": status_map.get("matched", 0), "pct": 0},
            {"stage": "Applied", "count": status_map.get("submitted", 0), "pct": 0},
            {"stage": "Interview", "count": status_map.get("interview", 0) + status_map.get("interview_scheduled", 0), "pct": 0},
            {"stage": "Offer", "count": status_map.get("offer", 0) + status_map.get("offered", 0), "pct": 0},
        ]

        # Calculate conversion percentages
        for i in range(1, len(funnel)):
            if funnel[i - 1]["count"] > 0:
                funnel[i]["pct"] = round((funnel[i]["count"] / funnel[i - 1]["count"]) * 100, 1)

        return {"funnel": funnel}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── WebSocket ───────────────────────────────────────────────────────────────

connected_clients: set[WebSocket] = set()


@router.websocket("/ws")
async def job_notifications(websocket: WebSocket):
    """WebSocket endpoint for real-time job match notifications."""
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Keep connection alive — client sends "ping" periodically
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
    except Exception:
        connected_clients.discard(websocket)


async def broadcast_notification(message: dict[str, Any]):
    """Broadcast a notification to all connected WebSocket clients."""
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.add(client)
    connected_clients.difference_update(disconnected)
