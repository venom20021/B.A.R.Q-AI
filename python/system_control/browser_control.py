"""
BARQ Browser Control — Playwright-based web browser automation.

Provides full browser session management:
- Launch real browser profiles (Chrome, Edge, Brave, Firefox)
- Navigate, search, click, type, scroll, screenshot
- Multi-tab management (new_tab, close_tab, tab switching)
- Session registry for multiple simultaneous browser sessions

Inspired by Mark-L's browser_control.py but adapted for BARQ's async architecture.

Usage via REST API:
    POST /system/browser/action  {"action": "go_to", "url": "https://..."}
    POST /system/browser/action  {"action": "search", "query": "python jobs"}
    POST /system/browser/action  {"action": "click", "text": "Sign in"}
    POST /system/browser/action  {"action": "screenshot"}

Usage via voice agent:
    "navigate to github.com"
    "search for python jobs"
    "click the login button"
    "scroll down"
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Optional

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


# ─── URL Helpers ───────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """Bare words like 'instagram' → 'https://instagram.com'."""
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    if "." not in url:
        url = url + ".com"
    return "https://" + url


# ─── Browser Profile Discovery ────────────────────────────────────────────────

def _real_profile_dir(browser: str) -> str:
    """Find the user's real browser profile directory."""
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam = os.environ.get("APPDATA", "")

    candidates: list[Path] = []

    if _OS == "Windows":
        profile_map = {
            "chrome": [Path(local) / "Google" / "Chrome" / "User Data"],
            "edge": [Path(local) / "Microsoft" / "Edge" / "User Data"],
            "brave": [Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data"],
            "vivaldi": [Path(local) / "Vivaldi" / "User Data"],
            "opera": [Path(roam) / "Opera Software" / "Opera Stable",
                      Path(local) / "Opera Software" / "Opera Stable"],
        }
        candidates = profile_map.get(browser, [])
    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        profile_map = {
            "chrome": [lib / "Google" / "Chrome"],
            "edge": [lib / "Microsoft Edge"],
            "brave": [lib / "BraveSoftware" / "Brave-Browser"],
            "vivaldi": [lib / "Vivaldi"],
            "opera": [lib / "com.operasoftware.Opera"],
        }
        candidates = profile_map.get(browser, [])
    elif _OS == "Linux":
        cfg = home / ".config"
        profile_map = {
            "chrome": [cfg / "google-chrome", cfg / "chromium"],
            "edge": [cfg / "microsoft-edge"],
            "brave": [cfg / "BraveSoftware" / "Brave-Browser"],
            "vivaldi": [cfg / "vivaldi"],
            "opera": [cfg / "opera"],
        }
        candidates = profile_map.get(browser, [])

    for p in candidates:
        if p.exists():
            print(f"[BrowserControl] Found real profile for {browser}: {p}")
            return str(p)

    # Fallback: create a dedicated profile for automation
    fallback = home / ".barq_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"[BrowserControl] No real profile found for {browser}, using: {fallback}")
    return str(fallback)


# ─── Browser Binary Detection ────────────────────────────────────────────────

def _find_browser_binary(browser: str) -> Optional[str]:
    """Find the browser's executable path."""
    # Common binary names per browser per platform
    binary_map = {
        "chrome":  ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
        "edge":    ["microsoft-edge", "microsoft-edge-stable"],
        "brave":   ["brave-browser", "brave"],
        "firefox": ["firefox"],
        "vivaldi": ["vivaldi", "vivaldi-stable"],
        "opera":   ["opera", "opera-stable"],
    }

    bins = binary_map.get(browser, [browser])
    for b in bins:
        found = shutil.which(b)
        if found:
            return found

    # Windows-specific: check common install paths
    if _OS == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        prog = os.environ.get("PROGRAMFILES", "")
        prog86 = os.environ.get("PROGRAMFILES(X86)", "")
        win_paths = {
            "chrome":  [f"{local}\\Google\\Chrome\\Application\\chrome.exe",
                        f"{prog86}\\Google\\Chrome\\Application\\chrome.exe"],
            "edge":    [f"{prog86}\\Microsoft\\Edge\\Application\\msedge.exe"],
            "brave":   [f"{local}\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"],
            "firefox": [f"{prog86}\\Mozilla Firefox\\firefox.exe"],
        }
        for p in win_paths.get(browser, []):
            if os.path.isfile(p):
                return p

    return None


# ─── Search Engines ──────────────────────────────────────────────────────────

_SEARCH_ENGINES: dict[str, str] = {
    "google":     "https://www.google.com/search?q=",
    "bing":       "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "yandex":     "https://yandex.com/search/?text=",
}

_BROWSER_ALIASES: dict[str, str] = {
    "google chrome":   "chrome",
    "google-chrome":   "chrome",
    "microsoft edge":  "edge",
    "ms edge":         "edge",
    "msedge":          "edge",
    "mozilla firefox": "firefox",
    "opera gx":        "operagx",
    "opera_gx":        "operagx",
}


# ─── Browser Session ─────────────────────────────────────────────────────────

class BrowserSession:
    """Controls a single browser instance via Playwright.

    Uses the user's real browser profile for a seamless experience
    (logged-in accounts, extensions, bookmarks all available).
    """

    def __init__(self, browser_name: str):
        self.browser_name = _BROWSER_ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def start(self):
        """Start the Playwright event loop in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=30)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._launch())
        self._ready.set()
        self._loop.run_forever()

    async def _launch(self):
        """Launch Playwright and open the browser with real user profile."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright is not installed. Install with: pip install playwright && playwright install chromium"
            )

        self._pw = await async_playwright().start()

        profile = _real_profile_dir(self.browser_name)
        binary = _find_browser_binary(self.browser_name)

        kwargs = {
            "headless": False,
            "slow_mo": 0,
            "viewport": None,
            "no_viewport": True,
            "timeout": 30000,
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-default-browser-check",
            ],
        }

        if binary:
            kwargs["executable_path"] = binary

        try:
            self._context = await self._pw.chromium.launch_persistent_context(profile, **kwargs)
            # Wait for the initial tab to be ready
            await asyncio.sleep(0.5)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            print(f"[BrowserControl] Launched {self.browser_name} with profile: {profile}")
        except Exception as e:
            print(f"[BrowserControl] Launch failed for {self.browser_name}: {e}")
            # Fallback: use a fresh profile
            fresh_profile = str(Path.home() / ".barq_profiles" / f"fresh_{self.browser_name}")
            Path(fresh_profile).mkdir(parents=True, exist_ok=True)
            kwargs.pop("executable_path", None)
            self._context = await self._pw.chromium.launch_persistent_context(fresh_profile, **kwargs)
            await asyncio.sleep(0.5)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            print(f"[BrowserControl] Launched {self.browser_name} with fresh profile: {fresh_profile}")

    async def _get_page(self):
        """Get the active page, creating a new one if closed."""
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
            await asyncio.sleep(0.2)
        return self._page

    async def _apply_stealth(self, page) -> None:
        """Inject anti-automation-detection scripts (shared with auto_applier).

        Reuses ``StealthConfig`` from the auto_applier module when available
        so one stealth implementation serves both the agent browser and the
        job auto-applier. Falls back silently if the module is unavailable.
        """
        try:
            from jobs.auto_applier.browser.stealth import StealthConfig
            await StealthConfig.apply_to_page(page)
        except Exception:
            # Minimal inline stealth so automation flags are still masked
            try:
                await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            except Exception:
                pass

    def run(self, coro, timeout: int = 60):
        """Run an async coroutine on the browser's event loop (thread-safe)."""
        if not self._loop:
            raise RuntimeError(f"Browser '{self.browser_name}' not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def go_to(self, url: str) -> str:
        """Navigate to a URL."""
        url = _normalize_url(url)
        page = await self._get_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._apply_stealth(page)
            await asyncio.sleep(0.3)
            return f"Opened: {page.url}"
        except Exception as e:
            return f"Navigation error: {e}"

    async def search(self, query: str, engine: str = "google") -> str:
        """Search the web using the specified search engine."""
        base = _SEARCH_ENGINES.get(engine.lower(), _SEARCH_ENGINES["google"])
        return await self.go_to(base + query.replace(" ", "+"))

    async def click(self, selector: str | None = None, text: str | None = None) -> str:
        """Click an element by CSS selector or visible text."""
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8000)
                return f"Clicked: '{text}'"
            if selector:
                await page.click(selector, timeout=8000)
                return f"Clicked: {selector}"
            return "No selector or text provided."
        except Exception as e:
            return f"Click error: {e}"

    async def type_text(self, text: str, selector: str | None = None, clear_first: bool = True) -> str:
        """Type text into an input field."""
        page = await self._get_page()
        try:
            el = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await el.clear()
            await el.type(text, delay=30)
            return f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"
        except Exception as e:
            return f"Type error: {e}"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        """Scroll the page."""
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return f"Scrolled {direction}."
        except Exception as e:
            return f"Scroll error: {e}"

    async def press_key(self, key: str) -> str:
        """Press a keyboard key (e.g. 'Enter', 'Escape', 'Tab')."""
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"Pressed: {key}"
        except Exception as e:
            return f"Key press error: {e}"

    async def get_text(self) -> str:
        """Get the visible text content of the current page."""
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4000]
        except Exception as e:
            return f"Could not get page text: {e}"

    # ── Anti-bot hardening (Phase 2a) ──────────────────────────────────

    async def detect_captcha(self) -> str:
        """Detect whether the current page is presenting a CAPTCHA challenge.

        Checks for common CAPTCHA iframes (hCaptcha / reCAPTCHA) and
        visible challenge markers. Used by the agent loop to pause and ask
        the user for a manual solve instead of hammering the site.

        Returns:
            'none' | 'hcaptcha' | 'recaptcha' | 'unknown-challenge'
        """
        try:
            page = await self._get_page()
            # hCaptcha challenge iframe
            hcap = await page.locator(
                "iframe[src*='hcaptcha.com'], iframe[title*='hCaptcha'], [id*='hcaptcha']"
            ).count()
            # reCAPTCHA challenge iframe
            recap = await page.locator(
                "iframe[src*='recaptcha'], iframe[src*='google.com/recaptcha'], [class*='g-recaptcha']"
            ).count()
            if hcap:
                return "hcaptcha"
            if recap:
                return "recaptcha"
            # Generic challenge markers
            body = " "
            try:
                body = (await page.inner_text("body")).lower()[:4000]
            except Exception:
                pass
            for marker in ("verify you are human", "complete the captcha", "captcha verification", "press and hold"):
                if marker in body:
                    return "unknown-challenge"
            return "none"
        except Exception as e:
            return f"error: {e}"

    async def check_rate_limited(self) -> str:
        """Detect whether the site is rate-limiting or blocking the session.

        Checks for HTTP 429 markers, LinkedIn/Glassdoor-style blocks, and
        "too many requests" text. The agent loop should back off (exponential
        sleep + jitter) before retrying.

        Returns:
            'ok' | 'rate_limited' | 'blocked' | 'error: ...'
        """
        try:
            page = await self._get_page()
            body = " "
            try:
                body = (await page.inner_text("body")).lower()[:4000]
            except Exception:
                pass
            for marker in ("too many requests", "rate limit", "request throttled", "slow down and try again"):
                if marker in body:
                    return "rate_limited"
            # LinkedIn/Indeed block pages
            for marker in ("unusual traffic", "please verify you are a human", "access denied", "our systems have detected"):
                if marker in body:
                    return "blocked"
            return "ok"
        except Exception as e:
            return f"error: {e}"

    async def observe(self) -> str:
        """Take a self-verification snapshot of the current page.

        Returns a compact summary (URL, title, visible text excerpt) that a
        planning agent can use to verify a step actually worked — e.g. after
        clicking "Sign in" it can check that the login form appeared.

        Returns:
            A human-readable observation string (or an error message).
        """
        try:
            page = await self._get_page()
            # Playwright's page.url is a SYNC property — never await it
            url = page.url
            title = await page.title()
            text = await page.inner_text("body")
            # Collapse whitespace and trim to a readable excerpt
            compact = " ".join(text.split())[:1500]
            return f"URL: {url}\nTitle: {title}\nPage text: {compact}"
        except Exception as e:
            return f"Observe error: {e}"

    async def get_url(self) -> str:
        """Get the current page URL."""
        page = await self._get_page()
        return page.url

    async def get_title(self) -> str:
        """Get the current page title."""
        page = await self._get_page()
        return await page.title()

    async def screenshot(self, path: str | None = None) -> str:
        """Take a screenshot of the current page."""
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "barq_screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            return f"Screenshot saved: {save_path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def back(self) -> str:
        """Navigate back."""
        page = await self._get_page()
        try:
            await page.go_back(timeout=10000)
            return f"Back: {page.url}"
        except Exception as e:
            return f"Back error: {e}"

    async def forward(self) -> str:
        """Navigate forward."""
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10000)
            return f"Forward: {page.url}"
        except Exception as e:
            return f"Forward error: {e}"

    async def reload(self) -> str:
        """Reload the current page."""
        page = await self._get_page()
        try:
            await page.reload(timeout=15000)
            return f"Reloaded: {page.url}"
        except Exception as e:
            return f"Reload error: {e}"

    async def new_tab(self, url: str = "") -> str:
        """Open a new tab, optionally navigating to a URL."""
        ctx = self._context
        new_page = await ctx.new_page()
        self._page = new_page
        if url:
            return await self.go_to(url)
        return "New tab opened."

    async def close_tab(self) -> str:
        """Close the current tab and switch to the last remaining one."""
        page = self._page
        if page and not page.is_closed():
            ctx = page.context
            await page.close()
            pages = ctx.pages
            self._page = pages[-1] if pages else None
            return "Tab closed."
        return "No active tab to close."

    async def close_browser(self) -> str:
        """Close the browser session."""
        try:
            if self._context:
                await self._context.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._context = None
        self._page = None
        self._pw = None
        return f"{self.browser_name} closed."

    async def fill_form(self, fields: dict[str, str]) -> str:
        """Fill multiple form fields at once. Keys are CSS selectors, values are text."""
        page = await self._get_page()
        results = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=30)
                results.append(f"✓ {selector}")
            except Exception as e:
                results.append(f"✗ {selector}: {e}")
        return "Form: " + ", ".join(results)


# ─── Session Registry ───────────────────────────────────────────────────────

class SessionRegistry:
    """Manages all active browser sessions."""

    def __init__(self):
        self._sessions: dict[str, BrowserSession] = {}
        self._active_browser: str = ""
        self._lock = threading.Lock()

    def _resolve(self, name: str | None) -> str:
        """Resolve a browser name (handle aliases, default)."""
        if not name:
            return self._active_browser or "chrome"
        return _BROWSER_ALIASES.get(name.lower().strip(), name.lower().strip())

    def get(self, browser_name: str | None = None) -> BrowserSession:
        """Get or create a browser session."""
        name = self._resolve(browser_name)
        with self._lock:
            if name not in self._sessions:
                sess = BrowserSession(name)
                sess.start()
                self._sessions[name] = sess
                print(f"[BrowserRegistry] New session: {name}")
            self._active_browser = name
            return self._sessions[name]

    def switch(self, browser_name: str) -> str:
        """Switch active browser session."""
        name = self._resolve(browser_name)
        self.get(name)  # ensures session exists
        self._active_browser = name
        return f"Active browser → {name}"

    def close(self, browser_name: str | None = None) -> str:
        """Close a specific browser session."""
        name = self._resolve(browser_name) if browser_name else self._active_browser
        with self._lock:
            sess = self._sessions.pop(name, None)
        if sess:
            sess.run(sess.close_browser())
            if self._active_browser == name:
                self._active_browser = ""
            return f"{name} closed."
        return f"No active session: {name}"

    def close_all(self) -> str:
        """Close all browser sessions."""
        with self._lock:
            names = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            try:
                s.run(s.close_browser())
            except Exception:
                pass
        return "All browsers closed: " + (", ".join(names) if names else "none")

    def list_sessions(self) -> str:
        """List all active browser sessions."""
        with self._lock:
            if not self._sessions:
                return "No active browser sessions."
            lines = [f"  • {name} {'◀ active' if name == self._active_browser else ''}"
                     for name in self._sessions]
            return "Open browsers:\n" + "\n".join(lines)

    def run_on(self, action: str, params: dict, browser_name: str | None = None) -> str:
        """Execute a browser action on the specified (or active) browser session."""
        sess = self.get(browser_name)
        action_map = {
            "go_to": lambda: sess.run(sess.go_to(params.get("url", ""))),
            "detect_captcha": lambda: sess.run(sess.detect_captcha()),
            "check_rate_limited": lambda: sess.run(sess.check_rate_limited()),
            "search": lambda: sess.run(sess.search(params.get("query", ""), params.get("engine", "google"))),
            "click": lambda: sess.run(sess.click(params.get("selector"), params.get("text"))),
            "type": lambda: sess.run(sess.type_text(params.get("text", ""), params.get("selector"), params.get("clear_first", True))),
            "scroll": lambda: sess.run(sess.scroll(params.get("direction", "down"), int(params.get("amount", 500)))),
            "screenshot": lambda: sess.run(sess.screenshot(params.get("path"))),
            "get_text": lambda: sess.run(sess.get_text()),
            "get_url": lambda: sess.run(sess.get_url()),
            "get_title": lambda: sess.run(sess.get_title()),
            "observe": lambda: sess.run(sess.observe()),
            "back": lambda: sess.run(sess.back()),
            "forward": lambda: sess.run(sess.forward()),
            "reload": lambda: sess.run(sess.reload()),
            "new_tab": lambda: sess.run(sess.new_tab(params.get("url", ""))),
            "close_tab": lambda: sess.run(sess.close_tab()),
            "press_key": lambda: sess.run(sess.press_key(params.get("key", "Enter"))),
            "fill_form": lambda: sess.run(sess.fill_form(params.get("fields", {}))),
            # switch/close/close_all/list_sessions are SessionRegistry-level
            # operations — route them to the registry, not the session object.
            "switch": lambda: _registry.switch(params.get("browser", browser_name or "chrome")),
            "close": lambda: _registry.close(params.get("browser")),
            "close_all": lambda: _registry.close_all(),
            "list_sessions": lambda: _registry.list_sessions(),
        }
        handler = action_map.get(action)
        if not handler:
            return f"Unknown browser action: '{action}'"
        try:
            return handler()
        except ImportError as e:
            return f"Browser control unavailable: {e}"
        except Exception as e:
            return f"Browser error ({action}): {e}"


# ─── Singleton ────────────────────────────────────────────────────────────────

_registry = SessionRegistry()


def browser_action(action: str, params: dict | None = None) -> str:
    """Convenience function to execute a browser action (for voice agent integration).

    Args:
        action: Action name (go_to, search, click, type, scroll, etc.)
        params: Dict of parameters for the action.

    Returns:
        Human-readable result string.
    """
    params = params or {}
    return _registry.run_on(action, params, params.get("browser"))


def open_url_native(url: str, browser_name: str | None = None) -> str:
    """Open a URL in the user's native browser (no Playwright automation).

    Used for simple navigation when automation is not needed.
    The URL opens in the user's real browser with their real profile.
    """
    url = _normalize_url(url)

    # Specific browser via subprocess
    if browser_name:
        name = _BROWSER_ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        binary = _find_browser_binary(name)
        if binary:
            try:
                subprocess.Popen([binary, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Opened in {name}: {url}"
            except Exception:
                pass

    # Default OS browser
    try:
        if _OS == "Windows":
            os.startfile(url)
        elif _OS == "Darwin":
            subprocess.run(["open", url], check=True, timeout=10)
        else:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened in default browser: {url}"
    except Exception:
        try:
            if webbrowser.open(url):
                return f"Opened in default browser: {url}"
        except Exception:
            pass
        return f"Could not open: {url}"
