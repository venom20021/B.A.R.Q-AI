"""
Tests for the Phase 1a browser observe action (system_control/browser_control.py).

The observe action lets a planning agent take a self-verification snapshot
(URL + title + visible text) after a browser_action, so it can confirm a step
actually worked. These tests exercise the logic with a fake page — no real
browser is ever launched.
"""

import pytest


def _awaitable(value):
    """Return a coroutine resolving to value (so `await page.url` works)."""

    async def _inner():
        return value

    return _inner()


class FakePage:
    """Minimal stand-in for a Playwright page."""

    def __init__(self, url="https://example.com/jobs/123", title="Example Jobs",
                 body="Software Engineer   Remote   Apply now"):
        # Playwright's page.url is a SYNC property — observe() must NOT await
        # it (awaiting a plain str raises TypeError). Expose a plain str so the
        # test catches any regression here.
        self.url = url
        self._title = title
        self._body = body

    def is_closed(self):
        return False

    async def title(self):
        return self._title

    async def inner_text(self, selector):
        return self._body


class StubSession:
    """Replacement for BrowserSession.run() that never touches Playwright."""

    def __init__(self, result="stubbed-result"):
        self.result = result
        self.called_actions = []

    def observe(self):
        # run_on's action map builds `sess.run(sess.observe())`, so the stub
        # must expose observe() (returning a coroutine like the real method).
        return _awaitable("observe-called")

    def run(self, coro, timeout=60):
        # coro is an awaitable built by run_on — we can't await it here, so
        # just record that run() was invoked and return the canned result.
        self.called_actions.append(coro)
        return self.result


def _make_session(page):
    from system_control.browser_control import BrowserSession
    sess = BrowserSession("chrome")
    sess._page = page
    return sess


# ─── observe() ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_observe_returns_url_title_and_text():
    """observe() should return a compact self-verification snapshot."""
    sess = _make_session(FakePage())
    result = await sess.observe()

    assert "URL: https://example.com/jobs/123" in result
    assert "Title: Example Jobs" in result
    # Whitespace is collapsed so the excerpt is a single readable line
    assert "Software Engineer Remote Apply now" in result


@pytest.mark.asyncio
async def test_observe_truncates_long_text():
    """The page-text excerpt should be truncated (not dumped in full)."""
    long_body = "word " * 5000
    sess = _make_session(FakePage(body=long_body))
    result = await sess.observe()
    # 1500 chars max excerpt, plus URL/title lines
    assert len(result) < 2000


@pytest.mark.asyncio
async def test_observe_graceful_when_no_page():
    """observe() must return an error string instead of raising when the
    browser has no active page/context."""
    sess = _make_session(None)
    sess._context = None
    result = await sess.observe()
    assert result.startswith("Observe error:")


# ─── Action map wiring ─────────────────────────────────────────────────────

def test_observe_is_registered_action(monkeypatch):
    """browser_action('observe') must route through the action map without
    launching a real browser (the session get() is stubbed)."""
    from system_control import browser_control

    stub = StubSession(result="URL: https://x.com\nTitle: X\nPage text: hi")
    monkeypatch.setattr(browser_control._registry, "get", lambda name=None: stub)

    result = browser_control.browser_action("observe", {"browser": "chrome"})
    assert result == "URL: https://x.com\nTitle: X\nPage text: hi"
    assert len(stub.called_actions) == 1


def test_registry_level_actions_route_to_registry(monkeypatch):
    """switch/close/close_all/list_sessions are SessionRegistry methods — the
    action map must call the registry, not the individual session object."""
    from system_control import browser_control

    stub = StubSession()
    monkeypatch.setattr(browser_control._registry, "get", lambda name=None: stub)

    calls = []

    def _rec(name):
        def f(*a, **k):
            calls.append(name)
            return name
        return f

    monkeypatch.setattr(browser_control._registry, "switch", _rec("switch"))
    monkeypatch.setattr(browser_control._registry, "close", _rec("close"))
    monkeypatch.setattr(browser_control._registry, "close_all", _rec("close_all"))
    monkeypatch.setattr(browser_control._registry, "list_sessions", _rec("list_sessions"))

    browser_control.browser_action("switch", {"browser": "edge"})
    browser_control.browser_action("close", {})
    browser_control.browser_action("close_all", {})
    browser_control.browser_action("list_sessions", {})
    assert calls == ["switch", "close", "close_all", "list_sessions"]
    # The session object must never be asked to do registry-level work
    assert stub.called_actions == []


def test_unknown_action_reports_error(monkeypatch):
    """Unknown actions should return a clear message, not raise."""
    from system_control import browser_control

    stub = StubSession()
    monkeypatch.setattr(browser_control._registry, "get", lambda name=None: stub)

    result = browser_control.browser_action("fly_to_the_moon", {})
    assert result == "Unknown browser action: 'fly_to_the_moon'"
    # get() is called before the action lookup, but no run() for unknown actions
    assert stub.called_actions == []


# ─── URL helper ─────────────────────────────────────────────────────────────

def test_normalize_url():
    from system_control.browser_control import _normalize_url

    assert _normalize_url("https://example.com") == "https://example.com"
    assert _normalize_url("github.com/barq") == "https://github.com/barq"
    assert _normalize_url("instagram") == "https://instagram.com"
    assert _normalize_url("") == "about:blank"
