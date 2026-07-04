"""
BARQ Python Sidecar - FastAPI Application

This service runs alongside the Electron app and provides:
- Voice control (Vosk wake word + Whisper STT)
- Job search automation (scraping, evaluation, application)
- Social media content pipeline (trends, scripts, video, posting)
- Analytics aggregation
"""

import os
import sys
from contextlib import asynccontextmanager
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

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    print(f"[BARQ Sidecar] Starting on {settings.host}:{settings.port}")
    await init_db()
    print("[BARQ Sidecar] Ready for requests")
    yield
    # Shutdown
    await close_db()
    print("[BARQ Sidecar] Shutting down")


app = FastAPI(
    title="BARQ Sidecar API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

# CORS - allow only local Electron app
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{settings.port}"],
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


@app.get("/health")
async def health():
    """Health check endpoint for the Electron main process."""
    return {
        "status": "ok",
        "service": "barq-sidecar",
        "version": "1.0.0",
    }


@app.post("/shutdown")
async def shutdown():
    """Graceful shutdown endpoint."""
    print("[BARQ Sidecar] Shutdown requested via API")
    await close_db()
    os._exit(0)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning",
    )
