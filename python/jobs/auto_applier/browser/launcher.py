"""
Headful Playwright browser launcher.

Launches a visible Chrome instance with stealth configurations,
reuses stored sessions, and provides a clean shutdown protocol.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    BrowserType,
    Page,
    async_playwright,
)

from ..config import CONFIG
from .session import SessionManager
from .stealth import StealthConfig

logger = logging.getLogger("barq.auto_applier.browser")


class BrowserLauncher:
    """Manages a headful Playwright browser lifecycle."""

    def __init__(self):
        self._playwright: Any = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._session_mgr = SessionManager()

    # ── Public API ──────────────────────────────────────────────────────

    async def launch(self) -> Page:
        """Launch headful browser, restore session, return a new page tab.

        Returns:
            An active Playwright Page ready for navigation.
        """
        logger.info("Launching headful %s browser...", CONFIG.browser_type)

        self._playwright = await async_playwright().start()
        browser_type: BrowserType = getattr(self._playwright, CONFIG.browser_type)

        self._browser = await browser_type.launch(
            headless=False,  # Per requirement — must be VISIBLE
            args=StealthConfig.get_launch_args(CONFIG.browser_type),
            slow_mo=CONFIG.slow_mo,
        )

        # Restore or create a fresh context with stealth init script
        storage_path = self._get_storage_path()
        if storage_path.exists():
            logger.info("Restoring session from %s", storage_path)
            self._context = await self._browser.new_context(
                storage_state=str(storage_path),
                viewport={"width": CONFIG.viewport_width, "height": CONFIG.viewport_height},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                bypass_csp=True,
                ignore_https_errors=True,
            )
        else:
            logger.info("No saved session — creating fresh context")
            self._context = await self._browser.new_context(
                viewport={"width": CONFIG.viewport_width, "height": CONFIG.viewport_height},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                bypass_csp=True,
                ignore_https_errors=True,
            )

        self._page = await self._context.new_page()
        await StealthConfig.apply_to_page(self._page)

        logger.info("Browser launched: headful=%s, viewport=%dx%d",
                     False, CONFIG.viewport_width, CONFIG.viewport_height)
        return self._page

    async def close(self) -> None:
        """Cleanly close the browser and save session state."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._context:
                await self._save_session()
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Browser closed cleanly")
        except Exception as exc:
            logger.warning("Error during browser shutdown: %s", exc)

    async def save_session(self) -> None:
        """Explicitly save the current session (e.g. after manual LinkedIn login)."""
        await self._save_session()

    # ── Internals ───────────────────────────────────────────────────────

    def _get_storage_path(self) -> Path:
        path = Path(CONFIG.storage_state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def _save_session(self) -> None:
        if not self._context:
            return
        try:
            storage = await self._context.storage_state()
            path = self._get_storage_path()
            import json
            path.write_text(json.dumps(storage, indent=2))
            logger.info("Session saved to %s (%d keys)", path, len(storage.get("cookies", [])))
        except Exception as exc:
            logger.warning("Failed to save session state: %s", exc)

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context
