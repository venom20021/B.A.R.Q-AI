"""
Telegram notification channel.

Sends messages via the Telegram Bot API using HTTP requests.
Designed for high-priority alerts like great job matches and
successful video posts.
"""

import html
import os
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
                # Render job_url and URL-like keys as clickable links
                if key in ("job_url", "url", "apply_url", "link") and str(value).startswith(("http://", "https://")):
                    safe_val = html.escape(str(value))
                    lines.append(f"🔗 <a href=\"{safe_val}\"><b>Open Application Link</b></a>")
                else:
                    safe_key = html.escape(key.replace("_", " ").title())
                    safe_val = html.escape(str(value))
                    lines.append(f"• {safe_key}: {safe_val}")

        return "\n".join(lines)

    async def send_document(
        self,
        document_path: str,
        caption: str = "",
        parse_mode: str = "HTML",
    ) -> NotificationResult:
        """Send a document (PDF, image, etc.) via Telegram.

        Uses the sendDocument Bot API endpoint to send files.
        The file is uploaded via multipart/form-data.

        Args:
            document_path: Absolute path to the file to send
            caption: Optional caption text for the document
            parse_mode: HTML or Markdown for caption formatting

        Returns:
            NotificationResult indicating success/failure
        """
        if not await self.is_enabled():
            return NotificationResult(
                success=False,
                channel=Channel.TELEGRAM,
                error="Telegram not configured",
            )

        if not os.path.isfile(document_path):
            return NotificationResult(
                success=False,
                channel=Channel.TELEGRAM,
                error=f"File not found: {document_path}",
            )

        try:
            import aiofiles as aio

            url = self.BASE_URL.format(
                token=self.settings.telegram_bot_token,
                method="sendDocument",
            )

            async with aio.open(document_path, "rb") as f:
                file_bytes = await f.read()

            # Send as multipart upload
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {"document": (os.path.basename(document_path), file_bytes, "application/pdf")}
                data = {
                    "chat_id": self.settings.telegram_chat_id,
                    "caption": caption[:1000] if caption else "",
                }
                if parse_mode:
                    data["parse_mode"] = parse_mode

                response = await client.post(url, data=data, files=files)

            result = response.json()
            if result.get("ok"):
                return NotificationResult(
                    success=True,
                    channel=Channel.TELEGRAM,
                    message=f"Document sent (id: {result['result']['message_id']})",
                )
            else:
                return NotificationResult(
                    success=False,
                    channel=Channel.TELEGRAM,
                    error=result.get("description", "Unknown Telegram error"),
                )

        except ImportError:
            # Fallback: try without aiofiles using synchronous read
            try:
                import httpx
                url = self.BASE_URL.format(
                    token=self.settings.telegram_bot_token,
                    method="sendDocument",
                )
                with open(document_path, "rb") as f:
                    file_bytes = f.read()

                async with httpx.AsyncClient(timeout=60.0) as client:
                    files = {"document": (os.path.basename(document_path), file_bytes, "application/pdf")}
                    data = {
                        "chat_id": self.settings.telegram_chat_id,
                        "caption": caption[:1000] if caption else "",
                    }
                    if parse_mode:
                        data["parse_mode"] = parse_mode
                    response = await client.post(url, data=data, files=files)

                result = response.json()
                if result.get("ok"):
                    return NotificationResult(
                        success=True,
                        channel=Channel.TELEGRAM,
                        message=f"Document sent (id: {result['result']['message_id']})",
                    )
                else:
                    return NotificationResult(
                        success=False,
                        channel=Channel.TELEGRAM,
                        error=result.get("description", "Unknown Telegram error"),
                    )
            except Exception as e:
                return NotificationResult(
                    success=False,
                    channel=Channel.TELEGRAM,
                    error=f"Document send failed: {e}",
                )
        except Exception as e:
            return NotificationResult(
                success=False,
                channel=Channel.TELEGRAM,
                error=f"Document send failed: {e}",
            )

    async def send_html_message(
        self,
        text: str,
        title: str = "",
        disable_notification: bool = False,
    ) -> NotificationResult:
        """
        Send a pre-formatted HTML message directly, bypassing _format_message() escaping.

        Unlike send(), this method does NOT html.escape() the body — it sends the
        raw HTML text as-is. Use this for messages that already contain HTML tags
        like formatted resumes or rich content.

        Args:
            text: Raw HTML message body (already contains HTML tags like <b>, <a>)
            title: Optional title prefix (will be auto-escaped and prepended)
            disable_notification: Whether to send silently

        Returns:
            NotificationResult indicating success/failure
        """
        if not await self.is_enabled():
            return NotificationResult(
                success=False,
                channel=Channel.TELEGRAM,
                error="Telegram not configured",
            )

        try:
            message = text
            if title:
                safe_title = html.escape(title)
                message = f"<b>{safe_title}</b>\n\n{text}"

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
                    "disable_notification": disable_notification,
                },
            )

            result = response.json()
            if result.get("ok"):
                return NotificationResult(
                    success=True,
                    channel=Channel.TELEGRAM,
                    message=f"HTML message sent (id: {result['result']['message_id']})",
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

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
