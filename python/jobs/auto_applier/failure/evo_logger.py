"""
EvoMap Failure Protocol.

Wraps all automation failures in structured telemetry payloads logged to
./memory/evolution/error_log.json for the EvoMap evolver daemon to audit.

Each failure entry includes:
  - URL and job context
  - Error type and message
  - DOM snapshot (first 3000 chars)
  - Screenshot path (if captured)
  - Timestamp
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG

logger = logging.getLogger("barq.auto_applier.evo")


class EvoLogger:
    """Structured failure logger for the EvoMap protocol."""

    def __init__(self):
        self._log_path = Path(CONFIG.evolution_log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    async def log_failure(
        self,
        url: str,
        error_type: str,
        error_message: str,
        dom_snapshot: str = "",
        screenshot_path: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Log a failure payload to the EvoMap evolution log.

        Args:
            url: The job URL where the failure occurred.
            error_type: Exception class name or error category.
            error_message: Human-readable error description.
            dom_snapshot: Truncated DOM HTML for debugging.
            screenshot_path: Path to a saved screenshot (if captured).
            context: Additional context (company, title, etc.).

        Returns:
            The failure payload dict that was logged.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "error_type": error_type,
            "error_message": error_message[:500],
            "dom_snapshot": dom_snapshot[:3000],
            "screenshot_path": screenshot_path,
            "context": context or {},
        }

        try:
            # Load existing log
            existing: list[dict] = []
            if self._log_path.exists():
                try:
                    raw = self._log_path.read_text(encoding="utf-8")
                    if raw.strip():
                        existing = json.loads(raw)
                        if not isinstance(existing, list):
                            existing = [existing]
                except (json.JSONDecodeError, Exception):
                    existing = []

            # Append and save
            existing.append(payload)
            self._log_path.write_text(
                json.dumps(existing, indent=2, default=str),
                encoding="utf-8",
            )

            logger.info(
                "EvoMap failure logged: %s @ %s — %s",
                error_type, url[:60], error_message[:80],
            )
            return payload

        except Exception as exc:
            logger.error("Failed to write EvoMap log: %s", exc)
            return payload

    async def log_success(
        self,
        url: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a successful application to the evolution log."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "event": "application_submitted",
            "context": context or {},
        }
        try:
            existing: list[dict] = []
            if self._log_path.exists():
                raw = self._log_path.read_text(encoding="utf-8")
                if raw.strip():
                    existing = json.loads(raw)
            existing.append(payload)
            self._log_path.write_text(
                json.dumps(existing, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to log success: %s", exc)

    def get_recent_failures(self, count: int = 10) -> list[dict[str, Any]]:
        """Return the most recent failure entries."""
        if not self._log_path.exists():
            return []
        try:
            data = json.loads(self._log_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # Filter to failures only
                failures = [e for e in data if "error_type" in e]
                return failures[-count:]
            return []
        except Exception:
            return []
