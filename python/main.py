"""
BARQ Python Sidecar - FastAPI Application

This service runs alongside the Electron app and provides:
- Voice control (Vosk wake word + Whisper STT)
- Job search automation (scraping, evaluation, application)
- Social media content pipeline (trends, scripts, video, posting)
- Analytics aggregation
- AI-powered resume parsing, matching, optimization
- Cover letter & cold email generation
- Playwright-based auto-apply
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the python directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_settings
from database import init_db, close_db
from voice.routes import router as voice_router
from jobs.routes import router as jobs_router
from social.routes import router as social_router
from analytics.routes import router as analytics_router
from notifications.routes import router as notification_router
from system_control.routes import router as system_router
from memory_knowledge.routes import router as memory_router
from web_media.routes import router as web_router
from documents.routes import router as documents_router
from desktop_automation.routes import router as desktop_router
from api.routes import router as api_v1_router
from auth_routes import router as auth_router

settings = get_settings()
logger = logging.getLogger("barq")

# ─── Background Job Scheduler ────────────────────────────────────────────────

scheduler = None


async def start_scheduler():
    """Start the APScheduler for background tasks."""
    global scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()

        # Auto-scrape jobs every 6 hours
        scheduler.add_job(
            _auto_scan_jobs,
            IntervalTrigger(hours=settings.job_scan_interval_hours),
            id="auto_scan_jobs",
            replace_existing=True,
        )

        # Auto-match new jobs every hour
        scheduler.add_job(
            _auto_match_jobs,
            IntervalTrigger(hours=1),
            id="auto_match_jobs",
            replace_existing=True,
        )

        scheduler.start()
        logger.info(f"[Scheduler] Started with {len(scheduler.get_jobs())} jobs")
    except ImportError:
        logger.warning("[Scheduler] APScheduler not installed — background tasks disabled")
    except Exception as e:
        logger.error(f"[Scheduler] Failed to start: {e}")


async def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("[Scheduler] Stopped")


async def _auto_scan_jobs():
    """Auto-scan for new jobs (called by scheduler)."""
    try:
        from jobs import JobScanner
        from database import jobs_dao, analytics_dao

        scanner = JobScanner()
        jobs = await scanner.scan_all(
            keywords=["software engineer", "developer", "full stack"],
            location="remote",
        )
        count = 0
        for job in jobs[:50]:
            await jobs_dao.insert_job_listing(job)
            count += 1

        await analytics_dao.log_activity(
            "job", "auto_scan", f"Auto-scanned {count} new jobs"
        )
        logger.info(f"[AutoScan] Found {count} new jobs")
    except Exception as e:
        logger.error(f"[AutoScan] Failed: {e}")


async def _auto_match_jobs():
    """Auto-match new jobs against resume (called by scheduler)."""
    try:
        from jobs.matcher import JobMatcher
        from jobs.resume_parser import parse_resume
        from database import jobs_dao, analytics_dao

        resume = parse_resume()
        if resume.get("_error"):
            return

        matcher = JobMatcher()
        jobs = await jobs_dao.get_active_jobs(limit=50)

        matched = 0
        for job in jobs:
            existing = await jobs_dao.get_evaluation(job["id"])
            if existing:
                continue

            result = await matcher.match(job, resume)
            await jobs_dao.insert_evaluation({
                "job_listing_id": job["id"],
                "overall_score": result["overall_score"] / 20,
                "match_percentage": result["overall_score"],
                "reasoning": result["fit_summary"],
                "pros": json.dumps(result["matching_skills"]),
                "cons": json.dumps(result["missing_skills"]),
                "evaluated_by": "llm",
            })
            matched += 1

        await analytics_dao.log_activity(
            "job", "auto_match", f"Auto-matched {matched} jobs"
        )
        logger.info(f"[AutoMatch] Matched {matched} jobs")
    except Exception as e:
        logger.error(f"[AutoMatch] Failed: {e}")


# ─── Lifespan ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    print(f"[BARQ Sidecar] Starting on {settings.host}:{settings.port}")
    await init_db()
    await start_scheduler()
    print("[BARQ Sidecar] Ready for requests")
    yield
    # Shutdown
    await stop_scheduler()
    await close_db()
    print("[BARQ Sidecar] Shutting down")


# ─── App Creation ────────────────────────────────────────────────────────────

app = FastAPI(
    title="BARQ Sidecar API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

# CORS - allow local origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(voice_router, prefix="/voice", tags=["Voice"])
app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
app.include_router(social_router, prefix="/social", tags=["Social"])
app.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
app.include_router(notification_router, prefix="/notifications", tags=["Notifications"])
app.include_router(system_router, prefix="/system", tags=["System Control"])
app.include_router(memory_router, prefix="/memory", tags=["Memory & Knowledge"])
app.include_router(web_router, prefix="/web", tags=["Web & Media"])
app.include_router(documents_router, prefix="/documents", tags=["Document Generation"])
app.include_router(desktop_router, prefix="/desktop", tags=["Desktop Automation"])
app.include_router(auth_router, tags=["Auth"])
app.include_router(api_v1_router, tags=["Jobs v1"])  # Already has /api/v1 prefix


@app.get("/health")
async def health():
    """Health check endpoint for the Electron main process."""
    return {
        "status": "ok",
        "service": "barq-sidecar",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/health")
async def api_health():
    """API v1 health check."""
    return {
        "status": "ok",
        "service": "barq-jobs",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/shutdown")
async def shutdown():
    """Graceful shutdown endpoint."""
    print("[BARQ Sidecar] Shutdown requested via API")
    await stop_scheduler()
    await close_db()
    os._exit(0)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO if settings.debug else logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning",
    )
