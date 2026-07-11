"""
BARQ Multi-Channel Notification System

Provides alerts through Telegram, Email, and Desktop channels.
Features priority-based routing, daily/scheduled digests, and
centralized logging of all notification activity.

Usage:
    from notifications import notification_manager

    # Send a simple notification
    await notification_manager.send_notification(
        title="Hello",
        body="This is a test",
        priority="high",
    )

    # Send a job match alert
    await notification_manager.send_job_match_alert(
        job_title="Senior Engineer",
        company="Acme Corp",
        match_score=92.0,
        job_id=123,
    )
"""

from .base import (
    Category,
    Channel,
    NotificationEvent,
    NotificationResult,
    Priority,
)
from .desktop import DesktopChannel
from .email_smtp import EmailChannel
from .manager import NotificationManager, notification_manager
from .telegram import TelegramChannel

__all__ = [
    "notification_manager",
    "NotificationManager",
    "NotificationEvent",
    "NotificationResult",
    "Priority",
    "Category",
    "Channel",
    "DesktopChannel",
    "TelegramChannel",
    "EmailChannel",
]
