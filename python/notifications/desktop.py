"""
Desktop notification channel.

Stores notifications in the database so the Electron app can
poll for them and show native desktop toasts. This is always
enabled and acts as the primary notification sink.
"""

from database import settings_dao

from .base import (
    Channel,
    NotificationChannel,
    NotificationEvent,
    NotificationResult,
)


class DesktopChannel(NotificationChannel):
    """Desktop notifications via DB storage (polled by Electron)."""

    def __init__(self):
        self._enabled = True

    @property
    def channel_type(self) -> Channel:
        return Channel.DESKTOP

    async def is_enabled(self) -> bool:
        """Desktop notifications are always available by default."""
        setting = await settings_dao.get_setting("desktop_notifications")
        return setting != "false"

    async def send(self, event: NotificationEvent) -> NotificationResult:
        """Store notification in DB for Electron to pick up."""
        try:
            notification_id = await settings_dao.insert_notification(event.to_db_dict())
            return NotificationResult(
                success=True,
                channel=Channel.DESKTOP,
                message=f"Stored (id: {notification_id})",
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                channel=Channel.DESKTOP,
                error=str(e),
            )

    async def get_unread(self, limit: int = 50) -> list[dict]:
        """Get unread desktop notifications."""
        return await settings_dao.get_unread_notifications(limit)

    async def mark_read(self, notification_id: int) -> bool:
        """Mark a notification as read."""
        count = await settings_dao.mark_notification_read(notification_id)
        return count > 0

    async def get_counts(self) -> dict[str, int]:
        """Get notification counts."""
        return await settings_dao.get_notification_count()
