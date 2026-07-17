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

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure the python directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.recruitment.routes import router as recruitment_router
from agent.research.routes import router as research_router
from agent.routes import router as agent_router
from agent.vision_routes import router as vision_router
from knowledge.routes import router as knowledge_router
from analytics.routes import router as analytics_router
from api.routes import router as api_v1_router
from settings.routes import router as settings_router
from auth_routes import router as auth_router
from config import get_settings
from database import analytics_dao, close_db, init_db
from desktop_automation.routes import router as desktop_router
from documents.routes import router as documents_router
from external_apis.routes import router as external_apis_router
from graph_brain import graph_brain
from jobs.routes import router as jobs_router
from memory_knowledge.brain_api import router as brain_api_router
from memory_knowledge.graph_routes import router as graph_router
from memory_knowledge.ingestion_routes import router as ingestion_router
from memory_knowledge.migration_routes import router as migration_router
from memory_knowledge.routes import router as memory_router
from notifications.routes import router as notification_router
from social.routes import router as social_router
from system_control.routes import router as system_router
from voice.routes import router as voice_router
from web_media.routes import router as web_router

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

        # Auto-extract knowledge triplets from new content every 3 hours
        scheduler.add_job(
            _auto_extract_knowledge,
            IntervalTrigger(hours=3),
            id="auto_extract_knowledge",
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
        from database import analytics_dao, jobs_dao
        from jobs import JobScanner

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
        from database import analytics_dao, jobs_dao
        from jobs.matcher import JobMatcher
        from jobs.resume_parser import parse_resume

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

    # Check LLM availability (Ollama + cloud fallback)
    try:
        from utils.ollama_client import OllamaClient, CloudLLMClient

        _ollama_check = OllamaClient()
        _cloud = CloudLLMClient()

        if await _ollama_check.is_available():
            print(f"[BARQ Sidecar] ✅ Ollama '{settings.ollama_model}' ready at {settings.ollama_host}")
        else:
            # Socket check to give a friendly diagnostic message
            import socket as _socket
            _s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            _s.settimeout(1)
            try:
                _s.connect(("127.0.0.1", 11434))
                _s.close()
                print(f"[BARQ Sidecar] ⚠ Ollama is running but model '{settings.ollama_model}' is not pulled yet")
                print(f"[BARQ Sidecar]   ➡ Run: ollama pull {settings.ollama_model}")
            except Exception:
                print("[BARQ Sidecar] ⚠ Ollama is NOT running")
                print(f"[BARQ Sidecar]   ➡ Install from: https://ollama.com/download/windows")
            finally:
                try:
                    _s.close()
                except Exception:
                    pass

            # Check cloud fallback
            if _cloud.enabled:
                print(f"[BARQ Sidecar] ✅ Cloud LLM fallback ready ({_cloud.model} at {_cloud.base_url})")
            else:
                print("[BARQ Sidecar] ⚠ No cloud LLM fallback — set OPENAI_API_KEY in .env to enable")
                print("[BARQ Sidecar]   ➡ Get a key at: https://platform.openai.com/api-keys")
    except Exception:
        pass  # don't crash on startup diagnostics

    # Load knowledge graph from disk if it exists
    import os as _os
    _graph_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "graph.json")
    graph_brain.load_from_disk(_graph_path)

    # Load multi-brain domain-specific graphs from disk
    from memory_knowledge.multi_brain import multi_brain_manager as _mbm
    _brains_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "brains")
    _mbm.set_data_dir(_brains_dir)
    _loaded = _mbm.load_all()
    _loaded_count = sum(1 for v in _loaded.values() if v)
    print(f"[BARQ Sidecar] Loaded {_loaded_count}/{len(_loaded)} domain-specific brains from {_brains_dir}")

    try:
        await analytics_dao.log_activity(
            "system", "startup", f"BARQ Sidecar v2.0 started on {settings.host}:{settings.port}",
            severity="info"
        )
    except Exception:
        pass  # DB might not be ready yet
    await start_scheduler()
    # Start the agent task queue
    try:
        from agent.task_queue import get_task_queue
        queue = get_task_queue()
        await queue.start()
        print("[BARQ Sidecar] Agent task queue started")
    except Exception as e:
        print(f"[BARQ Sidecar] Agent task queue start error: {e}")

    # Skills auto-register on import via agent.skill_registry

    # Start the ingestion drop-folder watcher
    _ingestion_monitor = None
    try:
        from memory_knowledge.ingestion import DropFolderMonitor
        from memory_knowledge.ingestion_routes import set_monitor as _set_ingestion_monitor

        _ingestion_monitor = DropFolderMonitor()
        _ingestion_monitor.process_all_existing()
        _ingestion_monitor.start()
        _set_ingestion_monitor(_ingestion_monitor)
        print("[BARQ Sidecar] Ingestion watcher started")
    except Exception as e:
        print(f"[BARQ Sidecar] Ingestion watcher start error: {e}")

    print("[BARQ Sidecar] Ready for requests")
    yield
    # Shutdown
    # Stop the ingestion watcher
    if _ingestion_monitor is not None:
        try:
            _ingestion_monitor.stop()
            print("[BARQ Sidecar] Ingestion watcher stopped")
        except Exception:
            pass
    await stop_scheduler()
    # Stop the agent task queue
    try:
        from agent.task_queue import get_task_queue
        queue = get_task_queue()
        await queue.stop()
        print("[BARQ Sidecar] Agent task queue stopped")
    except Exception as e:
        print(f"[BARQ Sidecar] Agent task queue stop error: {e}")
    try:
        await analytics_dao.log_activity(
            "system", "shutdown", "BARQ Sidecar shutting down",
            severity="info"
        )
    except Exception:
        pass
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
app.include_router(graph_router, prefix="/graph", tags=["Graph Brain"])
app.include_router(brain_api_router, tags=["Brain Visualisation"])
app.include_router(auth_router, tags=["Auth"])
app.include_router(api_v1_router, tags=["Jobs v1"])  # Already has /api/v1 prefix
app.include_router(agent_router, prefix="/agent", tags=["Agent System"])
app.include_router(vision_router, prefix="/vision", tags=["Visual Awareness"])
app.include_router(recruitment_router, prefix="/recruitment", tags=["Recruitment Agents"])
app.include_router(research_router, prefix="/research", tags=["Deep Research Agent"])
app.include_router(knowledge_router, prefix="/knowledge", tags=["Knowledge Management"])
app.include_router(ingestion_router, tags=["Ingestion Pipeline"])
app.include_router(migration_router, tags=["Graph Migration"])
app.include_router(settings_router, tags=["Settings"])
app.include_router(external_apis_router, tags=["Free Public APIs"])


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


# ─── Scheduler Configuration Endpoints ─────────────────────────────────────


@app.get("/scheduler/tasks")
async def get_scheduled_tasks():
    """Get all scheduled tasks from the database."""
    try:
        from database import db_connection
        tasks = await db_connection.fetch_all(
            "SELECT id, task_type, name, config, cron_expression, enabled, "
            "last_run, next_run, total_runs, last_status, created_at "
            "FROM scheduled_tasks ORDER BY task_type"
        )
        return {"tasks": tasks}
    except Exception as e:
        return {"tasks": [], "error": str(e)}


@app.post("/scheduler/tasks")
async def create_scheduled_task(data: dict):
    """Create a new scheduled task."""
    try:
        import json

        from database import db_connection
        task_id = await db_connection.insert(
            "INSERT INTO scheduled_tasks (task_type, name, config, cron_expression, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                data.get("task_type", "custom"),
                data.get("name", "New Task"),
                json.dumps(data.get("config", {})),
                data.get("cron_expression", "0 */6 * * *"),
                1 if data.get("enabled", True) else 0,
            ),
        )
        return {"status": "created", "id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/scheduler/tasks/{task_id}/toggle")
async def toggle_scheduled_task(task_id: int):
    """Enable or disable a scheduled task."""
    try:
        from database import db_connection
        task = await db_connection.fetch_one(
            "SELECT enabled FROM scheduled_tasks WHERE id = ?", (task_id,)
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        new_enabled = 0 if task["enabled"] else 1
        await db_connection.update(
            "UPDATE scheduled_tasks SET enabled = ? WHERE id = ?",
            (new_enabled, task_id),
        )
        return {"status": "toggled", "enabled": bool(new_enabled)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scheduler/status")
async def scheduler_status():
    """Get the current status of the APScheduler."""
    global scheduler
    if scheduler is None:
        return {"running": False, "jobs": []}
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return {"running": True, "jobs": jobs}


async def _auto_extract_knowledge():
    """Auto-extract knowledge triplets from unprocessed jobs/social (called by scheduler)."""
    try:
        from knowledge.auto_extractor import AutoExtractor

        extractor = AutoExtractor()
        result = await extractor.run_full_extraction()
        logger.info(
            "[AutoExtract] Extracted %d triplets (%d from jobs, %d from trends)",
            result["total_triplets"],
            result["job_triplets"],
            result["trend_triplets"],
        )
    except Exception as e:
        logger.error("[AutoExtract] Failed: %s", e)


@app.post("/scheduler/run/{task_type}")
async def run_task_manual(task_type: str):
    """Manually trigger a scheduled task."""
    try:
        if task_type == "job_scan":
            await _auto_scan_jobs()
            return {"status": "completed", "task": task_type}
        elif task_type == "job_match":
            await _auto_match_jobs()
            return {"status": "completed", "task": task_type}
        elif task_type == "knowledge_extract":
            await _auto_extract_knowledge()
            return {"status": "completed", "task": task_type}
        else:
            return {"status": "unknown_task", "task": task_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
