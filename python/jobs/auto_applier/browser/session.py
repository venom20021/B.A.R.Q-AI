"""
Session persistence for LinkedIn and job board logins.

Manages Playwright storage state (cookies + localStorage) so the
user only logs in manually once and sessions are reused automatically.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG

logger = logging.getLogger("barq.auto_applier.session")


class SessionManager:
    """Handles saving/loading Playwright storage state for job boards."""

    def __init__(self):
        self._storage_path = Path(CONFIG.storage_state_path)

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def has_session(self) -> bool:
        """Check if a saved session exists and is non-empty."""
        if not self._storage_path.exists():
            return False
        try:
            data = json.loads(self._storage_path.read_text())
            cookies = data.get("cookies", [])
            return len(cookies) > 0
        except (json.JSONDecodeError, Exception):
            return False

    def get_storage_state(self) -> Optional[dict[str, Any]]:
        """Load and return the saved storage state dict."""
        if not self.has_session:
            return None
        try:
            return json.loads(self._storage_path.read_text())
        except Exception as exc:
            logger.warning("Failed to load storage state: %s", exc)
            return None

    def save(self, storage_state: dict[str, Any]) -> None:
        """Persist storage state to disk."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps(storage_state, indent=2))
        cookies = len(storage_state.get("cookies", []))
        origins = len(storage_state.get("origins", []))
        logger.info("Session saved: %d cookies, %d origins → %s",
                     cookies, origins, self._storage_path)

    def clear(self) -> None:
        """Delete the saved session file."""
        if self._storage_path.exists():
            self._storage_path.unlink()
            logger.info("Session cleared: %s", self._storage_path)

    def is_linkedin_logged_in(self, storage_state: dict[str, Any]) -> bool:
        """Heuristic: check if LinkedIn session cookies exist."""
        for cookie in storage_state.get("cookies", []):
            domain = cookie.get("domain", "")
            name = cookie.get("name", "")
            if "linkedin" in domain and name in ("li_at", "JSESSIONID"):
                return True
        return False

    @property
    def storage_path(self) -> Path:
        return self._storage_path
