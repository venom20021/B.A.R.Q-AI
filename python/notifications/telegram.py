"""
Telegram notification channel.

Sends messages via the Telegram Bot API using HTTP requests.
Designed for high-priority alerts like great job matches and
successful video posts.
"""

import html
from typing import Optional

import httpx

from config import get_settings

from .base import (
    Channel,
    NotificationChannel,
    NotificationEvent,
    NotificationResult,
    Priority,
)


class TelegramChannel(NotificationChannel):
    """Sends notifications via Telegram Bot API."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    @property
    def channel_type(self) -> Channel:
        return Channel.TELEGRAM

    async def is_enabled(self) -> bool:
        """Check if Telegram bot token and chat ID are configured."""
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    async def send(self, event: NotificationEvent) -> NotificationResult:
        """Send a notification via Telegram."""
        if not await self.is_enabled():
            return NotificationResult(
                success=False,
                channel=Channel.TELEGRAM,
                error="Telegram not configured",
            )

        message = self._format_message(event)

        try:
            url = self.BASE_URL.format(
                token=self.settings.telegram_bot_token,
                method="sendMessage",
            )

            response = await self.client.post(
                url,
                json={
                    "chat_id": self.settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_notification": event.priority in (Priority.LOW, Priority.NORMAL),
                },
            )

            result = response.json()
            if result.get("ok"):
                return NotificationResult(
                    success=True,
                    channel=Channel.TELEGRAM,
                    message=f"Message sent (id: {result['result']['message_id']})",
                )
            else:
                return NotificationResult(
                    success=False,
                    channel=Channel.TELEGRAM,
                    error=result.get("description", "Unknown Telegram error"),
                )

        except httpx.HTTPError as e:
            return NotificationResult(
                success=False,
                channel=Channel.TELEGRAM,
                error=f"HTTP error: {e}",
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                channel=Channel.TELEGRAM,
                error=str(e),
            )

    def _format_message(self, event: NotificationEvent) -> str:
        """Format a notification as an HTML Telegram message."""
        priority_icons = {
            Priority.LOW: "ℹ️",
            Priority.NORMAL: "📢",
            Priority.HIGH: "⚡",
            Priority.URGENT: "🚨",
        }
        category_icons = {
            "general": "📋",
            "job_match": "🎯",
            "application": "📄",
            "content": "🎬",
            "analytics": "📊",
            "error": "❌",
            "system": "🔧",
        }

        icon = category_icons.get(event.category.value, "📋")
        priority_icon = priority_icons.get(event.priority, "📢")
        safe_title = html.escape(event.title)
        safe_body = html.escape(event.body)
        safe_category = html.escape(event.category.value.replace("_", " ").title())

        lines = [
            f"{priority_icon} <b>{safe_title}</b>",
            "",
            safe_body,
            "",
            f"<i>Category: {icon} {safe_category}</i>",
        ]

        if event.metadata:
            lines.append("")
            for key, value in event.metadata.items():
                safe_key = html.escape(key.replace("_", " ").title())
                safe_val = html.escape(str(value))
                lines.append(f"• {safe_key}: {safe_val}")

        return "\n".join(lines)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
