"""
Email notification channel.

Sends notifications via SMTP with support for both immediate
alerts and scheduled daily/weekly digests.
"""

import asyncio
import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from config import get_settings

from .base import (
    Channel,
    NotificationChannel,
    NotificationEvent,
    NotificationResult,
)


class EmailChannel(NotificationChannel):
    """Sends notifications via SMTP email."""

    def __init__(self):
        self.settings = get_settings()

    @property
    def channel_type(self) -> Channel:
        return Channel.EMAIL

    async def is_enabled(self) -> bool:
        """Check if SMTP settings are configured."""
        return bool(
            self.settings.smtp_host
            and self.settings.smtp_user
            and self.settings.smtp_pass
            and self.settings.notification_email
        )

    async def send(self, event: NotificationEvent) -> NotificationResult:
        """Send an immediate email notification."""
        if not await self.is_enabled():
            return NotificationResult(
                success=False,
                channel=Channel.EMAIL,
                error="SMTP not configured",
            )

        try:
            msg = self._build_message(event)
            # Run SMTP in thread to avoid blocking the event loop
            await asyncio.to_thread(self._send_smtp, msg)

            return NotificationResult(
                success=True,
                channel=Channel.EMAIL,
                message=f"Email sent to {self.settings.notification_email}",
            )

        except smtplib.SMTPException as e:
            return NotificationResult(
                success=False,
                channel=Channel.EMAIL,
                error=f"SMTP error: {e}",
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                channel=Channel.EMAIL,
                error=str(e),
            )

    def _build_message(self, event: NotificationEvent) -> MIMEMultipart:
        """Build an HTML email from a notification event."""
        msg = MIMEMultipart("alternative")
        # Sanitize subject: strip newlines and truncate to prevent header injection
        safe_subject = event.title.replace("\n", " ").replace("\r", "")[:200]
        msg["Subject"] = f"[BARQ] {safe_subject}"
        msg["From"] = formataddr(("BARQ Notifications", self.settings.smtp_user))
        msg["To"] = self.settings.notification_email

        # Plain text version
        text_content = f"{event.title}\n\n{event.body}"
        msg.attach(MIMEText(text_content, "plain"))

        # HTML version
        html_content = self._build_html(event)
        msg.attach(MIMEText(html_content, "html"))

        return msg

    def _build_html(self, event: NotificationEvent) -> str:
        """Build an HTML email body."""
        priority_colors = {
            "low": "#6b7280",
            "normal": "#3b82f6",
            "high": "#f59e0b",
            "urgent": "#ef4444",
        }
        color = priority_colors.get(event.priority.value, "#3b82f6")
        safe_title = html.escape(event.title)
        safe_body = html.escape(event.body)
        safe_category = html.escape(event.category.value.replace("_", " ").title())
        safe_priority = html.escape(event.priority.value.upper())

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f3f4f6;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding: 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
<tr><td style="background-color: {color}; padding: 24px; text-align: center;">
<h1 style="color: white; margin: 0; font-size: 20px;">{safe_title}</h1>
</td></tr>
<tr><td style="padding: 24px;">
<p style="color: #374151; font-size: 15px; line-height: 1.6;">{safe_body}</p>
<table width="100%" cellpadding="8" style="margin-top: 16px; background-color: #f9fafb; border-radius: 8px;">
<tr><td style="color: #6b7280; font-size: 13px;">
<strong>Priority:</strong> {safe_priority}<br>
<strong>Category:</strong> {safe_category}
</td></tr>
</table>
<hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
<p style="color: #9ca3af; font-size: 12px; text-align: center;">
Sent by BARQ — Your Voice-Controlled Desktop Assistant
</p>
</td></tr></table>
</td></tr></table>
</body>
</html>"""

    def _send_smtp(self, msg: MIMEMultipart):
        """Synchronous SMTP send (runs in thread pool)."""
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            server.starttls()
            server.login(self.settings.smtp_user, self.settings.smtp_pass)
            server.send_message(msg)

    async def send_digest(
        self, events: list[NotificationEvent], digest_type: str = "daily"
    ) -> NotificationResult:
        """Send a digest email containing multiple notifications."""
        if not await self.is_enabled():
            return NotificationResult(
                success=False,
                channel=Channel.EMAIL,
                error="SMTP not configured",
            )

        try:
            safe_digest_type = digest_type[:20].replace("\n", " ")
            subject = f"[BARQ] {safe_digest_type.title()} Digest — {len(events)} notifications"
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = formataddr(("BARQ Notifications", self.settings.smtp_user))
            msg["To"] = self.settings.notification_email

            # Build digest content
            events_html = ""
            for i, evt in enumerate(events):
                safe_title = html.escape(evt.title)
                safe_body = html.escape(evt.body)
                events_html += f"""
                <div style="padding: 16px; margin-bottom: 12px; background-color: #f9fafb; border-radius: 8px; border-left: 4px solid #3b82f6;">
                    <h3 style="margin: 0 0 8px 0; color: #111827; font-size: 15px;">{safe_title}</h3>
                    <p style="margin: 0; color: #6b7280; font-size: 14px;">{safe_body}</p>
                </div>"""

            html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f3f4f6;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding: 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
<tr><td style="background-color: #059669; padding: 24px; text-align: center;">
<h1 style="color: white; margin: 0; font-size: 20px;">{digest_type.title()} Digest</h1>
<p style="color: #a7f3d0; margin: 8px 0 0 0; font-size: 14px;">{len(events)} notification{"s" if len(events) != 1 else ""}</p>
</td></tr>
<tr><td style="padding: 24px;">
{events_html}
<hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
<p style="color: #9ca3af; font-size: 12px; text-align: center;">
Sent by BARQ — Your Voice-Controlled Desktop Assistant
</p>
</td></tr></table>
</td></tr></table>
</body>
</html>"""

            text = f"{digest_type.title()} Digest\n{'=' * 30}\n\n"
            for evt in events:
                text += f"• {evt.title}: {evt.body}\n"

            msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            await asyncio.to_thread(self._send_smtp, msg)

            return NotificationResult(
                success=True,
                channel=Channel.EMAIL,
                message=f"Digest sent ({len(events)} events)",
            )

        except Exception as e:
            return NotificationResult(
                success=False,
                channel=Channel.EMAIL,
                error=str(e),
            )
