"""
FastAPI routes for multi-channel notification system.

Provides endpoints for:
- Sending notifications through all channels
- Managing notification preferences
- Polling for desktop notifications
- Triggering digests
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import settings_dao

from .manager import (
    Category,
    Channel,
    NotificationEvent,
    Priority,
    notification_manager,
)

router = APIRouter()


# ─── Request Models ──────────────────────────────────────────────────────────

class SendNotificationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=2000)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    category: str = Field(default="general", pattern="^(general|job_match|application|content|analytics|error|system)$")
    channel: str = Field(default="all", pattern="^(telegram|email|desktop|all)$")
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None


class UpdateSettingsRequest(BaseModel):
    key: str
    value: str


class TelegramCredentialsRequest(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class NotificationSettingsRequest(BaseModel):
    telegram_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    desktop_enabled: Optional[bool] = None
    daily_digest_enabled: Optional[bool] = None
    job_match_alerts: Optional[bool] = None
    content_alerts: Optional[bool] = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/send", summary="Send a notification through all configured channels")
async def send_notification(request: SendNotificationRequest):
    """Send a notification event through the appropriate channels."""
    try:
        event = NotificationEvent(
            title=request.title,
            body=request.body,
            priority=Priority(request.priority),
            category=Category(request.category),
            channel=Channel(request.channel),
            related_entity_type=request.related_entity_type,
            related_entity_id=request.related_entity_id,
        )
        results = await notification_manager.send(event)
        return {
            "success": any(r.success for r in results.values()),
            "results": {
                channel: {
                    "success": result.success,
                    "message": result.message or result.error,
                }
                for channel, result in results.items()
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending", summary="Get unread desktop notifications")
async def get_pending(limit: int = 50):
    """Get unread desktop notifications (polled by Electron)."""
    try:
        unread = await notification_manager.desktop.get_unread(limit)
        counts = await notification_manager.desktop.get_counts()
        return {
            "notifications": unread,
            "counts": counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{notification_id}/read", summary="Mark a notification as read")
async def mark_read(notification_id: int):
    """Mark a desktop notification as read."""
    success = await notification_manager.desktop.mark_read(notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read", "id": notification_id}


@router.post("/digest", summary="Trigger a daily digest email")
async def trigger_digest():
    """Manually trigger a daily digest email."""
    try:
        results = await notification_manager.send_daily_digest()
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", summary="Get notification channel status")
async def get_status():
    """Get the enabled/ready status of all notification channels."""
    try:
        channel_status = await notification_manager.get_channel_status()
        counts = await notification_manager.get_pending_count()
        return {
            "channels": channel_status,
            "pending": counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings", summary="Get notification settings")
async def get_settings():
    """Get current notification preferences."""
    try:
        settings = await settings_dao.get_settings_by_category("notifications")
        return {s["key"]: s["value"] for s in settings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings", summary="Update notification preferences")
async def update_settings(request: NotificationSettingsRequest):
    """Update notification preferences."""
    try:
        if request.telegram_enabled is not None:
            await settings_dao.set_setting("telegram_enabled", str(request.telegram_enabled).lower(), "notifications")
        if request.email_enabled is not None:
            await settings_dao.set_setting("email_enabled", str(request.email_enabled).lower(), "notifications")
        if request.desktop_enabled is not None:
            await settings_dao.set_setting("desktop_notifications", str(request.desktop_enabled).lower(), "notifications")
        if request.daily_digest_enabled is not None:
            await settings_dao.set_setting("daily_digest_enabled", str(request.daily_digest_enabled).lower(), "notifications")
        if request.job_match_alerts is not None:
            await settings_dao.set_setting("job_match_alerts", str(request.job_match_alerts).lower(), "notifications")
        if request.content_alerts is not None:
            await settings_dao.set_setting("content_alerts", str(request.content_alerts).lower(), "notifications")

        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Telegram Credentials ─────────────────────────────────────────────


@router.get("/telegram/status", summary="Get Telegram connection status (token configured, last test)")
async def get_telegram_status():
    """Get Telegram configuration status (without exposing the full token)."""
    from config import get_settings
    cfg = get_settings()
    token = cfg.telegram_bot_token or await settings_dao.get_setting("telegram_bot_token") or ""
    chat_id = cfg.telegram_chat_id or await settings_dao.get_setting("telegram_chat_id") or ""
    return {
        "configured": bool(token and chat_id),
        "bot_token_preview": (token[:8] + "..." + token[-4:]) if token and len(token) > 12 else "",
        "chat_id_preview": (chat_id[:4] + "...") if chat_id else "",
        "has_token": bool(token),
        "has_chat_id": bool(chat_id),
    }


class TelegramCredentialsRequest(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


@router.post("/telegram/credentials", summary="Save Telegram bot token and chat ID")
async def set_telegram_credentials(request: TelegramCredentialsRequest):
    """Save Telegram bot token and chat ID to user settings (persisted across restarts)."""
    try:
        if request.bot_token:
            await settings_dao.set_setting("telegram_bot_token", request.bot_token, "notifications")
        if request.chat_id:
            await settings_dao.set_setting("telegram_chat_id", request.chat_id, "notifications")
        return {"status": "saved", "has_token": bool(request.bot_token), "has_chat_id": bool(request.chat_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telegram/credentials", summary="Get saved Telegram bot token and chat ID (masked)")
async def get_telegram_credentials():
    """Get saved Telegram credentials (token is masked for security)."""
    try:
        token = await settings_dao.get_setting("telegram_bot_token") or ""
        chat_id = await settings_dao.get_setting("telegram_chat_id") or ""
        return {
            "bot_token": token,
            "chat_id": chat_id,
            "bot_token_masked": (token[:8] + "..." + token[-4:]) if len(token) > 12 else ("*" * min(len(token), 8)) if token else "",
            "has_token": bool(token),
            "has_chat_id": bool(chat_id),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/{channel}", summary="Send a test notification to verify channel setup")
async def test_channel(channel: str):
    """Send a test notification to verify a channel is working."""
    if channel not in ("telegram", "email", "desktop"):
        raise HTTPException(status_code=400, detail=f"Unknown channel: {channel}")

    event = NotificationEvent(
        title="🔔 BARQ Test Notification",
        body="This is a test message to verify your notification channel is working correctly.",
        priority=Priority.NORMAL,
        category=Category.SYSTEM,
    )

    if channel == "telegram":
        result = await notification_manager.telegram.send(event)
    elif channel == "email":
        result = await notification_manager.email.send(event)
    else:
        result = await notification_manager.desktop.send(event)

    return {
        "success": result.success,
        "channel": channel,
        "message": result.message or result.error,
    }
