"""
Stealth Playwright configuration.

Injects evasion scripts at navigation time to remove automation fingerprints
that headful browser scripts are commonly detected by.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("barq.auto_applier.stealth")


STEALTH_JS = """
// ── Remove webdriver property ──────────────────────────────────────────
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// ── Mask chrome runtime ───────────────────────────────────────────────
window.chrome = { runtime: {} };

// ── Plugins length ─────────────────────────────────────────────────────
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// ── Languages ──────────────────────────────────────────────────────────
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// ── Platform override ──────────────────────────────────────────────────
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
});

// ── Hardware concurrency ───────────────────────────────────────────────
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
});

// ── Device memory ──────────────────────────────────────────────────────
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
});

// ── WebGL vendor (realistic GPU fingerprint) ───────────────────────────
const getExt = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(...args) {
    const ctx = getExt.apply(this, args);
    if (ctx && args[0] === 'webgl') {
        const getParam = ctx.getParameter;
        ctx.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';
            if (p === 37446) return 'Intel Iris OpenGL Engine';
            return getParam.apply(ctx, [p]);
        };
    }
    return ctx;
};

// ── Permissions: hide automation indicators ────────────────────────────
const origQuery = navigator.permissions.query;
navigator.permissions.query = (params) => (
    params.name === 'notifications'
        ? Promise.resolve({ state: 'prompt' })
        : origQuery(params)
);
"""


class StealthConfig:
    """Holds all stealth configuration for Playwright browser contexts."""

    @staticmethod
    def get_launch_args(browser_type: str = "chromium") -> list[str]:
        """Return browser launch arguments that reduce automation fingerprints."""
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-notifications",
            "--disable-popup-blocking",
            f"--window-size={1366},{768}",
        ]

        if browser_type == "chromium":
            args.extend([
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-sync",
            ])

        return args

    @staticmethod
    async def apply_to_page(page: Any) -> None:
        """Inject stealth evasion scripts into a Playwright page.

        Call this after every page.goto() / page navigation.
        """
        try:
            await page.add_init_script(STEALTH_JS)
            logger.debug("Stealth init script injected on %s", page.url)
        except Exception as exc:
            logger.warning("Stealth injection failed: %s", exc)

    @staticmethod
    async def human_delay(page: Any, min_ms: int = 300, max_ms: int = 1200) -> None:
        """Wait a random human-like delay between interactions."""
        import random
        ms = random.randint(min_ms, max_ms)
        await page.wait_for_timeout(ms)

    @staticmethod
    async def human_type(page: Any, selector: str, text: str, base_delay: int = 80) -> None:
        """Type text with human-like variable speed."""
        import asyncio
        import random

        locator = page.locator(selector)
        await locator.click()
        await locator.fill("")

        for char in text:
            delay = random.randint(base_delay - 30, base_delay + 60)
            await locator.press(char)
            await asyncio.sleep(delay / 1000)

        logger.debug("Human-typed %d characters into %s", len(text), selector)
