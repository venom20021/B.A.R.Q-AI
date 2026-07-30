"""
Smart Reminders — native OS toasts, reminder scheduling, background checks.

Uses win10toast (Windows) or plyer (cross-platform fallback) to show
native OS toast notifications. Reminders are stored in the DB and
checked periodically by a background task.

Usage:
    from notifications.reminders import reminder_manager

    # Create a reminder
    await reminder_manager.create_reminder(
        title="Meeting",
        message="Stand-up in 5 minutes",
        delay_minutes=5,
    )

    # Check due reminders
    due = await reminder_manager.check_due_reminders()
"""

import asyncio
import logging
import platform
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import settings_dao

logger = logging.getLogger("barq.reminders")


@dataclass
class Reminder:
    """A scheduled reminder."""

    id: int = 0
    title: str = ""
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    due_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    dismissed: bool = False
    notified: bool = False

    def is_due(self) -> bool:
        """Check if this reminder is due (past its due time)."""
        return datetime.now(timezone.utc) >= self.due_at and not self.dismissed

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "dismissed": self.dismissed,
            "notified": self.notified,
        }


# ─── Native Toast ─────────────────────────────────────────────────────────


def _show_native_toast(title: str, message: str, duration: int = 5) -> bool:
    """Show a native OS toast notification.

    Tries win10toast first (Windows), then falls back to plyer.
    Returns True on success, False if no notification library is available.
    """
    system = platform.system()

    if system == "Windows":
        try:
            from win10toast import ToastNotifier

            toaster = ToastNotifier()
            toaster.show_toast(
                title,
                message,
                duration=duration,
                threaded=True,
            )
            return True
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"win10toast failed: {e}")

    # Cross-platform fallback via plyer
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            timeout=duration,
            app_name="BARQ",
        )
        return True
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"plyer notification failed: {e}")

    # Last resort: print to stderr (always available)
    logger.info(f"[REMINDER] {title}: {message}")
    return False


# ─── Reminder Manager ──────────────────────────────────────────────────────


class ReminderManager:
    """Manages reminders with DB persistence and native toast delivery."""

    def __init__(self):
        self._background_task: Optional[asyncio.Task] = None
        self._running = False

    async def create_reminder(
        self,
        title: str,
        message: str = "",
        due_at: Optional[datetime] = None,
        delay_minutes: Optional[int] = None,
    ) -> dict[str, Any]:
        """Create a new reminder.

        Args:
            title: Short reminder title (e.g., "Meeting")
            message: Optional detail message
            due_at: Absolute due time (UTC). If None, computed from delay_minutes.
            delay_minutes: Minutes from now until due. Ignored if due_at is set.

        Returns:
            Dict with status and reminder data.
        """
        now = datetime.now(timezone.utc)

        if due_at is None:
            delay = delay_minutes or 0
            due_at = now + timedelta(minutes=delay)

        reminder_data = {
            "title": title[:200],
            "message": (message or "")[:1000],
            "created_at": now.isoformat(),
            "due_at": due_at.isoformat(),
            "dismissed": False,
            "notified": False,
        }

        try:
            # Store in DB via settings_dao (using "reminders" category)
            reminder_id = await settings_dao.set_setting(
                f"reminder_{int(now.timestamp())}",
                json_dumps(reminder_data),
                "reminders",
            )
            reminder_data["id"] = reminder_id or 0
            return {"status": "ok", "reminder": reminder_data}
        except Exception as e:
            logger.error(f"Failed to save reminder: {e}")
            return {"status": "error", "detail": str(e)}

    async def list_reminders(self, include_dismissed: bool = False) -> list[dict]:
        """List all reminders, optionally including dismissed ones."""
        try:
            settings = await settings_dao.get_settings_by_category("reminders")
            reminders = []
            for s in settings:
                try:
                    data = json_loads(s["value"])
                    if not include_dismissed and data.get("dismissed"):
                        continue
                    reminders.append(data)
                except Exception:
                    continue
            return reminders
        except Exception as e:
            logger.error(f"Failed to list reminders: {e}")
            return []

    async def dismiss_reminder(self, reminder_id: int) -> dict[str, Any]:
        """Mark a reminder as dismissed."""
        return await self._update_reminder_field(reminder_id, "dismissed", True)

    async def mark_notified(self, reminder_id: int) -> dict[str, Any]:
        """Mark a reminder as having been notified."""
        return await self._update_reminder_field(reminder_id, "notified", True)

    async def _update_reminder_field(
        self, reminder_id: int, field: str, value: bool
    ) -> dict[str, Any]:
        """Update a boolean field on a reminder by ID."""
        try:
            settings = await settings_dao.get_settings_by_category("reminders")
            for s in settings:
                try:
                    data = json_loads(s["value"])
                    if data.get("id") == reminder_id:
                        data[field] = value
                        await settings_dao.set_setting(
                            s["key"], json_dumps(data), "reminders"
                        )
                        return {"status": "ok", "reminder": data}
                except Exception:
                    continue
            return {"status": "error", "detail": "Reminder not found"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    async def check_due_reminders(self) -> list[dict]:
        """Check for due reminders, show native toasts, return fired reminders."""
        fired = []
        reminders = await self.list_reminders(include_dismissed=False)

        for r in reminders:
            if self._is_due(r) and not r.get("notified"):
                # Show native toast
                _show_native_toast(
                    title=r.get("title", "Reminder"),
                    message=r.get("message", ""),
                    duration=10,
                )

                # Mark as notified
                rid = r.get("id", 0)
                await self.mark_notified(rid)
                r["notified"] = True
                fired.append(r)

        return fired

    def _is_due(self, reminder: dict) -> bool:
        """Check if a reminder dict is past its due time."""
        try:
            due_str = reminder.get("due_at", "")
            if not due_str:
                return False
            due = datetime.fromisoformat(due_str)
            return datetime.now(timezone.utc) >= due
        except Exception:
            return False

    async def start_background_check(self, interval_seconds: int = 30):
        """Start background task that checks for due reminders every N seconds."""
        if self._running:
            return

        self._running = True
        self._background_task = asyncio.create_task(
            self._background_loop(interval_seconds)
        )
        logger.info(f"Reminder background check started (every {interval_seconds}s)")

    async def stop_background_check(self):
        """Stop the background reminder check task."""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            self._background_task = None
            logger.info("Reminder background check stopped")

    async def _background_loop(self, interval: int):
        """Background loop — check due reminders, sleep, repeat."""
        while self._running:
            try:
                fired = await self.check_due_reminders()
                if fired:
                    logger.info(f"Fired {len(fired)} reminder(s)")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reminder check error: {e}")

            await asyncio.sleep(interval)


# ─── JSON helpers (avoid full import chain) ────────────────────────────────

try:
    import orjson as json_impl

    def json_dumps(obj: Any) -> str:
        return json_impl.dumps(obj).decode("utf-8")

    def json_loads(s: str) -> Any:
        return json_impl.loads(s)
except ImportError:
    import json as json_impl

    def json_dumps(obj: Any) -> str:
        return json_impl.dumps(obj, default=str)

    def json_loads(s: str) -> Any:
        return json_impl.loads(s)


# Singleton
reminder_manager = ReminderManager()
