"""
BackgroundMonitor — user-configured topic watching with daily news checks.

Inspired by Mark-L's background_monitor.py. Allows users to configure topics
to monitor via BARQ's long-term memory. Checks DuckDuckGo news once per day
per topic and logs alerts when new headlines appear.

Blocked categories: crypto, finance, NFT — no uninvited tracking.

Usage:
    # Add a topic to monitor
    add_monitor("Python 3.13")
    add_monitor("WebGPU")

    # Check all topics for new news (called by scheduler)
    alerts = check_all()  # Returns list of alert strings

    # List / remove
    list_monitors()
    remove_monitor("Python 3.13")
"""

import hashlib
import json
import re
from datetime import datetime

# ── Blocked categories (never monitor regardless of what user says) ────────────

_BLOCKED = {
    "bitcoin", "ethereum", "dogecoin", "solana", "binance",
    "nft", "blockchain", "defi", "altcoin", "memecoin", "coin", "token",
    "crypto", "kripto", "cripto", "krypto",
    "cryptocurrency",
}

# ── Storage ────────────────────────────────────────────────────────────────────
# Monitors are stored in long_term.json under the "monitors" key,
# same as Mark-L's approach.

from memory.agent_memory_manager import load_memory, MEMORY_PATH, _lock  # noqa: E402


def _load_monitors() -> dict:
    """Load the monitors dict from long-term memory."""
    data = load_memory().get("monitors", {})
    return data if isinstance(data, dict) else {}


def _save_monitors(monitors: dict) -> None:
    """Save the monitors dict to long-term memory."""
    memory = load_memory()
    memory["monitors"] = monitors
    with _lock:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_blocked(topic: str) -> bool:
    t = topic.lower()
    return any(word in t for word in _BLOCKED)


def _slug(topic: str) -> str:
    """Create a filesystem-safe slug from a topic string."""
    return re.sub(r"[^a-z0-9]+", "_", topic.lower().strip())[:40].strip("_")


def _title_hash(title: str) -> str:
    return hashlib.md5(title.encode("utf-8", errors="ignore")).hexdigest()[:12]


# ── Public API ─────────────────────────────────────────────────────────────────

def add_monitor(topic: str) -> str:
    """Add a topic to monitor for news updates.

    Args:
        topic: The topic to watch (e.g. "Python", "WebGPU", "AI regulation").

    Returns:
        Human-readable confirmation message.
    """
    topic = topic.strip()
    if not topic:
        return "Please specify a topic to monitor."
    if _is_blocked(topic):
        return "I don't monitor crypto or financial topics."
    monitors = _load_monitors()
    slug = _slug(topic)
    if slug in monitors:
        return f"Already monitoring: {monitors[slug]['topic']}"
    monitors[slug] = {
        "topic": topic,
        "added": datetime.now().strftime("%Y-%m-%d"),
        "last_check": "",
        "last_hash": "",
    }
    _save_monitors(monitors)
    print(f"[BackgroundMonitor] ➕ Added: {topic}")
    return f"Now monitoring: {topic}"


def remove_monitor(topic: str) -> str:
    """Remove a topic from monitoring.

    Args:
        topic: The topic or slug to stop monitoring.

    Returns:
        Human-readable confirmation message.
    """
    topic = topic.strip().lower()
    monitors = _load_monitors()
    # Exact slug match first
    slug = _slug(topic)
    if slug in monitors:
        label = monitors.pop(slug)["topic"]
        _save_monitors(monitors)
        return f"Stopped monitoring: {label}"
    # Partial match fallback
    for key, val in list(monitors.items()):
        if topic in val.get("topic", "").lower():
            label = monitors.pop(key)["topic"]
            _save_monitors(monitors)
            return f"Stopped monitoring: {label}"
    return f"Not found in monitored topics: {topic}"


def list_monitors() -> list[str]:
    """List all currently monitored topics.

    Returns:
        List of topic strings (human-readable names).
    """
    return [v.get("topic", k) for k, v in _load_monitors().items()]


async def check_all() -> list[str]:
    """Run all pending topic checks (once per day per topic).

    Uses DuckDuckGo's instant answer API (no API key required).
    Only checks topics that haven't been checked today.

    Returns:
        List of alert strings — empty if nothing new.
    """
    monitors = _load_monitors()
    if not monitors:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    alerts: list[str] = []
    changed = False

    for slug, data in monitors.items():
        if data.get("last_check") == today:
            continue  # already checked today

        topic = data.get("topic", slug)
        try:
            results = await _duckduckgo_news(topic, max_results=5)
            if not results:
                monitors[slug]["last_check"] = today
                changed = True
                continue

            top = results[0]
            title = top.get("title", "").strip()
            if not title:
                continue

            h = _title_hash(title)
            monitors[slug]["last_check"] = today
            changed = True

            if h == data.get("last_hash"):
                continue  # same headline as last check

            monitors[slug]["last_hash"] = h

            snippet = top.get("snippet", "")[:200]
            source = top.get("source", "")

            parts = [
                f"[Monitor Alert] {topic}",
                f"Headline: {title}",
            ]
            if snippet:
                parts.append(snippet)
            if source:
                parts.append(f"Source: {source}")
            alerts.append("\n".join(parts))
            print(f"[BackgroundMonitor] 🔔 New for '{topic}': {title[:60]}")

        except Exception as e:
            print(f"[BackgroundMonitor] ⚠️ Check failed for '{topic}': {e}")

    if changed:
        _save_monitors(monitors)

    return alerts


async def _duckduckgo_news(query: str, max_results: int = 5) -> list[dict]:
    """Fetch news results from DuckDuckGo's instant answer API.

    No API key required. Uses DuckDuckGo's public API endpoint.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of dicts with 'title', 'snippet', 'source', 'url' keys.
    """
    try:
        import httpx

        # DuckDuckGo instant answer API (no key needed)
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
            "t": "barq_assistant",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)

            if response.status_code != 200:
                print(f"[BackgroundMonitor] DDG API returned {response.status_code}")
                return []

            data = response.json()

            # Extract related topics (news-like results)
            results = []
            topics = data.get("RelatedTopics", [])
            for item in topics[:max_results]:
                if isinstance(item, dict) and "Text" in item:
                    title = item.get("Text", "").split(" - ")[0] if " - " in item.get("Text", "") else item.get("Text", "")
                    results.append({
                        "title": title or item.get("Text", ""),
                        "snippet": item.get("Text", ""),
                        "url": item.get("FirstURL", ""),
                        "source": item.get("Result", ""),
                    })

            # If not enough from RelatedTopics, try the abstract
            abstract = data.get("Abstract", "")
            if abstract and len(results) < max_results:
                results.append({
                    "title": data.get("Heading", query),
                    "snippet": abstract[:200],
                    "url": data.get("AbstractURL", ""),
                    "source": data.get("AbstractSource", "DuckDuckGo"),
                })

            return results[:max_results]

    except ImportError:
        print("[BackgroundMonitor] httpx not installed — skipping DDG check")
        return []
    except Exception as e:
        print(f"[BackgroundMonitor] DDG fetch error: {e}")
        return []


async def scheduled_check() -> list[str]:
    """Scheduler hook: check all topics and dispatch alerts.

    Returns a list of alert strings. If there are alerts, they are
    logged and dispatched via the notification system.

    Called by APScheduler on an interval (e.g. every 6 hours).
    """
    alerts = await check_all()
    if alerts:
        for alert in alerts:
            print(f"[BackgroundMonitor] 📢 {alert[:100]}...")
            # Dispatch via notification system
            try:
                from notifications.manager import notification_manager
                lines = alert.split("\n")
                topic = lines[0].replace("[Monitor Alert] ", "") if lines else "Monitor Alert"
                headline = lines[1].replace("Headline: ", "") if len(lines) > 1 else alert[:80]
                await notification_manager.send_notification(
                    title=f"📰 {topic}",
                    body=headline,
                    priority="low",
                    category="general",
                    source="background_monitor",
                    raw_alert=alert,
                )
                print("[BackgroundMonitor] ✅ Alert dispatched")
            except Exception as e:
                print(f"[BackgroundMonitor] ⚠️ Dispatch error: {e}")
    return alerts
