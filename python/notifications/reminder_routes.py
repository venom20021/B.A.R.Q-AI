"""
FastAPI routes for Smart Reminders.

Provides endpoints for creating, listing, and dismissing reminders.
Also includes native OS toast triggering.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("barq.reminders")

router = APIRouter()


# ─── Request Models ──────────────────────────────────────────────────────────


class CreateReminderRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(default="", max_length=2000)
    delay_minutes: int = Field(default=5, ge=1, le=43200)  # 1 min to 30 days
    due_at: Optional[str] = None  # ISO format datetime


class ReminderResponse(BaseModel):
    status: str
    reminder: Optional[dict] = None
    detail: str = ""


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/reminders", summary="Create a new reminder")
async def create_reminder(request: CreateReminderRequest):
    """Create a timed reminder with native OS toast notification."""
    try:
        from .reminders import reminder_manager

        due_at = None
        if request.due_at:
            try:
                due_at = datetime.fromisoformat(request.due_at)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid due_at format: {request.due_at}. Use ISO format (e.g. 2026-01-15T14:30:00+00:00)",
                )

        result = await reminder_manager.create_reminder(
            title=request.title,
            message=request.message,
            due_at=due_at,
            delay_minutes=request.delay_minutes if not request.due_at else None,
        )

        if result.get("status") == "ok":
            return result
        raise HTTPException(status_code=500, detail=result.get("detail", "Failed to create reminder"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reminders", summary="List all reminders")
async def list_reminders(
    include_dismissed: bool = Query(False, description="Include dismissed reminders"),
):
    """List all reminders, optionally including dismissed ones."""
    try:
        from .reminders import reminder_manager

        reminders = await reminder_manager.list_reminders(include_dismissed=include_dismissed)
        return {"status": "ok", "count": len(reminders), "reminders": reminders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reminders/{reminder_id}/dismiss", summary="Dismiss a reminder")
async def dismiss_reminder(reminder_id: int):
    """Mark a reminder as dismissed by its ID."""
    try:
        from .reminders import reminder_manager

        result = await reminder_manager.dismiss_reminder(reminder_id)
        if result.get("status") == "ok":
            return result
        raise HTTPException(status_code=404, detail="Reminder not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reminders/check", summary="Check for due reminders now")
async def check_reminders():
    """Manually trigger a check for due reminders. Fires native OS toasts."""
    try:
        from .reminders import reminder_manager

        fired = await reminder_manager.check_due_reminders()
        return {"status": "ok", "fired": len(fired), "reminders": fired}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toast/test", summary="Test native OS toast notification")
async def test_toast():
    """Send a test native OS toast to verify the notification system works."""
    try:
        from .reminders import _show_native_toast

        success = _show_native_toast(
            title="🔔 BARQ Reminder Test",
            message="This is a test toast from BARQ's Smart Reminder system!",
            duration=5,
        )
        return {
            "status": "ok" if success else "unavailable",
            "detail": "Native toast shown" if success else "No notification library available",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
