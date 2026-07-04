"""
Notification Manager — orchestrates multi-channel notifications.

Routes notification events to the appropriate channels based on
priority, category, and user preferences. Supports Telegram for
urgent/high alerts, email for digests, and desktop for all alerts.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from database import settings_dao, analytics_dao
from .base import (
    NotificationEvent,
    NotificationResult,
    Channel,
    Priority,
    Category,
)
from .telegram import TelegramChannel
from .email_smtp import EmailChannel
from .desktop import DesktopChannel


class NotificationManager:
    """
    Central notification orchestrator.

    Dispatches events to the right channels based on priority and
    category. Handles channel lifecycle, channel enable/disable,
    digest generation, and activity logging.
    """

    def __init__(self):
        self.telegram = TelegramChannel()
        self.email = EmailChannel()
        self.desktop = DesktopChannel()

    async def send(self, event: NotificationEvent) -> dict[str, NotificationResult]:
        """
        Dispatch a notification event to all applicable channels.

        Routing rules:
        - URGENT: Telegram + Desktop + Email (immediate)
        - HIGH:   Telegram + Desktop
        - NORMAL: Desktop (and Telegram if enabled)
        - LOW:    Desktop only

        Args:
            event: The notification event to dispatch

        Returns:
            Dict mapping channel names to send results
        """
        results: dict[str, NotificationResult] = {}
        tasks = []

        # Always send to desktop (primary sink)
        tasks.append(("desktop", self.desktop.send(event)))

        # Route based on priority
        if event.priority == Priority.URGENT:
            tasks.append(("telegram", self.telegram.send(event)))
            if await self._is_email_enabled():
                tasks.append(("email", self.email.send(event)))
        elif event.priority == Priority.HIGH:
            if await self.telegram.is_enabled():
                tasks.append(("telegram", self.telegram.send(event)))
        elif event.priority == Priority.NORMAL:
            if await self.telegram.is_enabled():
                tasks.append(("telegram", self.telegram.send(event)))

        # Also send telegram for job_match and content categories if enabled
        if event.category in (Category.JOB_MATCH, Category.CONTENT):
            if await self.telegram.is_enabled() and event.priority not in (Priority.LOW,):
                if not any(t[0] == "telegram" for t in tasks):
                    tasks.append(("telegram", self.telegram.send(event)))

        # Execute all channel sends concurrently
        for channel_name, coro in tasks:
            try:
                result = await coro
                results[channel_name] = result
            except Exception as e:
                results[channel_name] = NotificationResult(
                    success=False,
                    channel=Channel.DESKTOP,
                    error=str(e),
                )

        # Log the activity
        await self._log_activity(event, results)

        return results

    async def send_notification(
        self,
        title: str,
        body: str,
        priority: str = "normal",
        category: str = "general",
        channel: str = "all",
        **metadata,
    ) -> dict[str, NotificationResult]:
        """Convenience method to create and send a notification."""
        event = NotificationEvent(
            title=title,
            body=body,
            priority=Priority(priority),
            category=Category(category),
            channel=Channel(channel),
            metadata=metadata,
        )
        return await self.send(event)

    async def send_job_match_alert(
        self, job_title: str, company: str, match_score: float, job_id: int
    ) -> dict[str, NotificationResult]:
        """Send a high-priority job match alert."""
        return await self.send_notification(
            title=f"🎯 Great Job Match: {job_title}",
            body=f"{company} — {match_score:.0f}% match score. Ready for review.",
            priority="high",
            category="job_match",
            related_entity_type="job_listing",
            related_entity_id=job_id,
            company=company,
            match_score=f"{match_score:.0f}%",
        )

    async def send_content_published_alert(
        self, video_title: str, platforms: list[str]
    ) -> dict[str, NotificationResult]:
        """Send an alert when content is published."""
        return await self.send_notification(
            title=f"🎬 Published: {video_title}",
            body=f"Posted successfully to {', '.join(platforms)}.",
            priority="high",
            category="content",
            platforms=", ".join(platforms),
        )

    async def send_application_update(
        self, company: str, position: str, status: str
    ) -> dict[str, NotificationResult]:
        """Send an application status update."""
        emoji = {"submitted": "📄", "interview": "🤝", "offer": "🎉", "rejected": "💔"}
        return await self.send_notification(
            title=f"{emoji.get(status, '📋')} Application {status.title()}: {position}",
            body=f"{company} — Status changed to {status}.",
            priority="high" if status in ("interview", "offer") else "normal",
            category="application",
            company=company,
            status=status,
        )

    async def send_system_alert(self, message: str) -> dict[str, NotificationResult]:
        """Send a system-level alert (errors, warnings)."""
        return await self.send_notification(
            title="🔧 System Alert",
            body=message,
            priority="urgent",
            category="system",
        )

    async def send_daily_digest(self) -> dict[str, NotificationResult]:
        """Generate and send a daily digest email."""
        digest_enabled = await settings_dao.get_setting("daily_digest_enabled")
        if digest_enabled != "true":
            return {}

        # Collect recent activity for digest
        activities = await analytics_dao.get_recent_activity(limit=20)
        recent_events = []

        for activity in activities:
            event = NotificationEvent(
                title=activity.get("action", "Activity"),
                body=activity.get("description", ""),
                priority=Priority.NORMAL,
                category=Category(activity.get("type", "general")),
            )
            recent_events.append(event)

        # Also add unread notifications
        unread = await self.desktop.get_unread(limit=10)
        for notif in unread:
            event = NotificationEvent(
                title=notif.get("title", "Notification"),
                body=notif.get("body", ""),
                priority=Priority(notif.get("priority", "normal")),
                category=Category(notif.get("category", "general")),
            )
            recent_events.append(event)

        # Deduplicate
        seen_titles = set()
        unique_events = []
        for evt in recent_events:
            if evt.title not in seen_titles:
                seen_titles.add(evt.title)
                unique_events.append(evt)

        if not unique_events:
            return {}

        # Send digest via email
        result = await self.email.send_digest(unique_events, "daily")

        # Also send a summary via desktop
        await self.send_notification(
            title="📬 Daily Digest Sent",
            body=f"Summary of {len(unique_events)} events sent to your email.",
            priority="low",
            category="analytics",
        )

        return {"email": result}

    async def _is_email_enabled(self) -> bool:
        """Check if email channel is both configured AND enabled by user."""
        if not await self.email.is_enabled():
            return False
        setting = await settings_dao.get_setting("email_enabled")
        return setting != "false"

    async def _log_activity(
        self,
        event: NotificationEvent,
        results: dict[str, NotificationResult],
    ):
        """Log notification activity."""
        success_count = sum(1 for r in results.values() if r.success)
        total_count = len(results)

        await analytics_dao.log_activity(
            activity_type="notification",
            action=f"Sent notification: {event.title}",
            description=f"{success_count}/{total_count} channels delivered ({event.priority.value})",
            metadata={
                "title": event.title,
                "priority": event.priority.value,
                "category": event.category.value,
                "channel_results": {
                    k: {"success": v.success} for k, v in results.items()
                },
            },
        )

    async def get_channel_status(self) -> dict[str, bool]:
        """Get the enabled/ready status of all channels."""
        return {
            "telegram": await self.telegram.is_enabled(),
            "email": await self.email.is_enabled(),
            "desktop": await self.desktop.is_enabled(),
        }

    async def get_pending_count(self) -> dict[str, int]:
        """Get count of unread notifications."""
        return await self.desktop.get_counts()

    async def close(self):
        """Cleanup channel resources."""
        await self.telegram.close()


# Singleton instance
notification_manager = NotificationManager()
