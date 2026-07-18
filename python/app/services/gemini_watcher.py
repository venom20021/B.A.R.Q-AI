"""
Gemini Local Ingestion File Watcher — hands-free ingestion of Google Gemini
chat history (Google Takeout JSON or HTML) into the ``ai_chats`` knowledge graph.

Flow
----
1. A Gemini chat history file (Google Takeout .json or .html) lands in
   ``./data/ingest/ai_chats/``
2. The background watcher (asyncio-based with optional ``watchdog``) detects
   the new file, waits for the write to stabilise, then parses it:
   - **JSON**: Google Takeout format — looks for items whose title starts
     with ``"Said "``, strips that prefix, and extracts clean user prompts
   - **HTML**: Uses ``BeautifulSoup`` to strip HTML and extract the raw
     conversational text / user prompts
3. Cleaned prompt text is sent to the local Ollama instance
   (``llama3.1:8b`` at ``http://localhost:11434/api/generate``) for
   knowledge triplet extraction
4. Extracted ``[Subject, RELATIONSHIP, Object]`` triplets are injected into
   the ``barq_brains["ai_chats"]`` NetworkX graph via ``MultiBrainManager``
5. The source file is **deleted** from the watch directory to prevent
   re-processing
6. All parsing / Ollama / filesystem failures are logged as telemetry
   ``EvolutionEvent`` payloads into ``./memory/evolution/`` following the
   GEP (Genome Evolution Protocol) pattern
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

import httpx

# ─── Conditional watchdog import ─────────────────────────────────────────────

_HAS_WATCHDOG = False
_WatchdogObserver: Any = None
_WatchdogEventHandler: Any = None
try:
    from watchdog.events import FileSystemEventHandler as _WatchdogEventHandler
    from watchdog.observers import Observer as _WatchdogObserver

    _HAS_WATCHDOG = True
except ImportError:
    pass

# ─── Conditional watchdog handler class ─────────────────────────────────────
# Defined here so the base class is resolved before any runtime usage;
# the class itself is a no-op body that gets replaced below when watchdog
# is actually available.

if _HAS_WATCHDOG and _WatchdogEventHandler is not None:

    class _GeminiWatchdogHandler(_WatchdogEventHandler):  # type: ignore[valid-type,misc]
        """Watchdog event handler that delegates to ``GeminiFileWatcher``."""

        def __init__(self, watcher: GeminiFileWatcher) -> None:
            super().__init__()
            self.watcher = watcher

        def on_created(self, event: Any) -> None:
            if event.is_directory:
                return
            self._handle(event.src_path)

        def on_moved(self, event: Any) -> None:
            dest = getattr(event, "dest_path", None)
            if dest:
                self._handle(dest)

        def _handle(self, path: str) -> None:
            if Path(path).suffix.lower() in _SKIP_SUFFIXES:
                return
            self.watcher._process_file(path)
else:
    # Placeholder when watchdog is not installed — never instantiated
    _GeminiWatchdogHandler = object  # type: ignore[misc]

# ─── Conditional BeautifulSoup import ────────────────────────────────────────

_HAS_BS4 = False
try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment]

# ─── Project imports ────────────────────────────────────────────────────────

from config import get_settings
from graph_brain import EXTRACTION_SYSTEM_PROMPT
from memory_knowledge.multi_brain import multi_brain_manager
from voice.evolution_logger import get_evolution_logger

logger = logging.getLogger("barq.gemini_watcher")

# ─── Constants ───────────────────────────────────────────────────────────────

WATCH_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "ingest",
    "ai_chats",
)

BRAIN_TYPE = "ai_chats"

# File extensions to skip while still being downloaded
_SKIP_SUFFIXES = {".tmp", ".part", ".download", ".crdownload", ".crdownload~"}

# Maximum seconds to wait for a file's size to stabilise
_FILE_STABILITY_RETRIES = 6
_FILE_STABILITY_DELAY = 1.0

# How often (seconds) the background poller scans the watch directory
_POLL_INTERVAL = 5.0

# Telegram-style Gemini chat title prefix to strip
_SAID_PREFIX = "said "


# ═════════════════════════════════════════════════════════════════════════════
#  GeminiParser — Dual-Format (JSON / HTML) Gemini Chat Parser
# ═════════════════════════════════════════════════════════════════════════════


class GeminiParser:
    """Parse Google Gemini chat history files into clean prompt text.

    Supports two input formats:

    - **Google Takeout JSON** (``.json``):
      The expected format is a JSON array of conversation items. Each item
      has a ``title`` field — items where ``title`` starts with ``"Said "``
      are user-initiated prompts. The prefix is stripped and the remainder
      is the clean user prompt text.

    - **HTML** (``.html``):
      Uses ``BeautifulSoup`` to strip all HTML structure, then extracts
      meaningful text content, focusing on user-query portions (words
      following ``<user>`` markers, question marks, or imperative verbs).
    """

    # ── Public API ──────────────────────────────────────────────────────

    def parse(self, file_path: str) -> str:
        """Parse a Gemini chat history file and return clean prompt text.

        Args:
            file_path: Absolute or relative path to a ``.json`` or ``.html`` file.

        Returns:
            Cleaned, concatenated user prompt text ready for triplet extraction.
            Returns empty string on failure or empty content.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("[GeminiWatcher] File not found: %s", file_path)
            return ""

        suffix = path.suffix.lower()
        raw = path.read_text(encoding="utf-8", errors="replace")

        if suffix == ".json":
            return self._parse_json(raw)
        elif suffix == ".html":
            return self._parse_html(raw)
        else:
            logger.debug(
                "[GeminiWatcher] Unknown suffix %s — treating as text", suffix
            )
            return self._clean_text(raw)

    # ── JSON / Google Takeout Parser ────────────────────────────────────

    def _parse_json(self, raw: str) -> str:
        """Parse Google Takeout JSON and extract ``"Said …"`` prompt texts.

        The Google Takeout format is typically a JSON array of objects::

            [
              {
                "title": "Said tell me about neural networks",
                "text": "...",
                ...
              },
              ...
            ]

        Items whose ``title`` starts with ``"Said "`` (case-insensitive)
        are user prompts. The prefix is stripped and the remainder is the
        clean query text.

        If the JSON is a dict with a ``"conversations"`` key (wrapped
        Takeout export), it recurses into that array.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("[GeminiWatcher] Invalid JSON: %s", exc)
            return ""

        items: list[dict[str, Any]] = []

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Wrapped Takeout export: { "conversations": [...] }
            items = data.get("conversations", data.get("items", data.get("data", [])))
            if not isinstance(items, list):
                items = []
        else:
            return self._clean_text(raw)

        if not items:
            return ""

        prompts: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            text = (item.get("text") or item.get("content") or item.get("body") or "").strip()

            # Primary: items whose title starts with "Said "
            title_lower = title.lower()
            if title_lower.startswith(_SAID_PREFIX):
                prompt = title[len(_SAID_PREFIX):].strip()
                if prompt:
                    prompts.append(prompt)
                    continue

            # Secondary: if the title itself looks like a question, use it
            if title and self._is_likely_question(title):
                prompts.append(title)
                continue

            # Tertiary: if text is non-empty and looks like a user query
            if text and (text.endswith("?") or len(text) > 20):
                prompts.append(text)

        if not prompts:
            logger.debug("[GeminiWatcher] No 'Said …' prompts found in JSON")
            return self._clean_text(raw)

        return "\n\n".join(prompts)

    # ── HTML Parser ─────────────────────────────────────────────────────

    def _parse_html(self, raw: str) -> str:
        """Parse an HTML export of Gemini chats using BeautifulSoup.

        Strips all HTML tags, extracts conversational text, and isolates
        user-query-like segments (text following ``<user>`` markers or
        containing question indicators).

        Falls back to regex-based extraction if BeautifulSoup is not installed.
        """
        if _HAS_BS4 and BeautifulSoup is not None:
            return self._parse_html_bs4(raw)
        else:
            logger.info(
                "[GeminiWatcher] BeautifulSoup not available — using regex fallback for HTML"
            )
            return self._parse_html_regex(raw)

    def _parse_html_bs4(self, raw: str) -> str:
        """Parse HTML with BeautifulSoup — the primary path."""
        soup = BeautifulSoup(raw, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style", "meta", "link", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n")

        return self._extract_user_prompts_from_text(text)

    def _parse_html_regex(self, raw: str) -> str:
        """Parse HTML with regex fallback when BeautifulSoup is unavailable."""
        # Remove style / script blocks
        cleaned = re.sub(
            r"<style[^>]*>.*?</style>", "", raw, flags=re.IGNORECASE | re.DOTALL
        )
        cleaned = re.sub(
            r"<script[^>]*>.*?</script>", "", cleaned, flags=re.IGNORECASE | re.DOTALL
        )

        # Convert block tags to newlines
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</p>", "\n\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</(div|section|article|blockquote)>", "\n\n", cleaned, flags=re.IGNORECASE)

        # Strip remaining tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)

        # Decode common HTML entities
        cleaned = cleaned.replace("&amp;", "&")
        cleaned = cleaned.replace("&lt;", "<")
        cleaned = cleaned.replace("&gt;", ">")
        cleaned = cleaned.replace("&nbsp;", " ")
        cleaned = cleaned.replace("&quot;", '"')
        cleaned = cleaned.replace("&#39;", "'")

        # Collapse whitespace
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r" {2,}", " ", cleaned)

        return self._extract_user_prompts_from_text(cleaned)

    # ── Shared Text Processing ─────────────────────────────────────────

    @staticmethod
    def _extract_user_prompts_from_text(text: str) -> str:
        """Extract user-query-like segments from raw extracted text.

        Heuristics:
        - Lines following ``<user>`` markers
        - Lines ending with ``?``
        - Lines starting with question/imperative words
        - Lines with significant length (likely substantive queries)
        """
        lines = text.split("\n")
        prompts: list[str] = []
        is_user_context = False

        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                is_user_context = False
                continue

            line_lower = line.lower()

            # Detect user markers
            if line_lower.startswith("<user>") or line_lower.startswith("user:"):
                is_user_context = True
                line = re.sub(r"^<\/?user>\s*:?\s*", "", line, flags=re.IGNORECASE).strip()
                if line:
                    prompts.append(line)
                continue

            if line_lower.startswith("<model>") or line_lower.startswith("model:"):
                is_user_context = False
                continue

            # Within user context, capture the line
            if is_user_context and len(line) > 10:
                prompts.append(line)
                continue

            # Question detection (even without user markers)
            if line.endswith("?") and len(line) > 10:
                prompts.append(line)
                continue

            # Imperative / query start words
            first_word = line.split()[0].lower() if line.split() else ""
            if first_word in {
                "what", "how", "why", "when", "where", "which", "who",
                "can", "could", "would", "should", "explain", "define",
                "describe", "tell", "show", "write", "create", "generate",
                "is", "are", "do", "does", "did", "give", "make", "find",
            }:
                if len(line) > 15:
                    prompts.append(line)

        if not prompts:
            return ""

        return "\n\n".join(prompts[:50])  # cap at 50 prompts

    @staticmethod
    def _is_likely_question(text: str) -> bool:
        """Check whether *text* reads like a user question."""
        t = text.strip()
        if not t:
            return False
        if t.endswith("?"):
            return True
        first_word = t.split()[0].lower() if t.split() else ""
        return first_word in {
            "what", "how", "why", "when", "where", "which", "who",
            "can", "could", "would", "should", "explain", "define",
            "describe", "tell", "show", "write", "create", "generate",
        }

    # ── Text Cleaner ───────────────────────────────────────────────────

    @staticmethod
    def _clean_text(raw: str) -> str:
        """Basic text cleaning: strip BOM, normalise newlines, trim."""
        text = raw.lstrip("\ufeff")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()


# ═════════════════════════════════════════════════════════════════════════════
#  GeminiTripletExtractor — Ollama-powered Triplet Extraction
# ═════════════════════════════════════════════════════════════════════════════


class GeminiTripletExtractor:
    """Send cleaned Gemini prompt text to local Ollama and parse triplets.

    Uses the same ``EXTRACTION_SYSTEM_PROMPT`` and httpx call pattern from
    ``graph_brain.py``, targeting ``llama3.1:8b`` at
    ``http://localhost:11434/api/generate``.

    Extracted triplets are injected directly into the ``barq_brains["ai_chats"]``
    NetworkX graph via ``MultiBrainManager``.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.ollama_host: str = settings.ollama_host
        self.ollama_model: str = settings.ollama_model
        self._http_client = httpx.Client(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
        )
        self._lock = Lock()
        self._stats_lock = Lock()
        self._total_triplets_extracted: int = 0
        self._total_prompts_processed: int = 0
        self._last_error: Optional[str] = None

    # ── Public API ──────────────────────────────────────────────────────

    def process_prompt(self, prompt_text: str) -> int:
        """Extract triplets from *prompt_text* and add them to the ``ai_chats`` brain.

        Args:
            prompt_text: Cleaned user prompt text (from ``GeminiParser``).

        Returns:
            Number of triplets successfully added to the graph.
        """
        if not prompt_text.strip():
            return 0

        triplets = self._call_ollama(prompt_text)
        if not triplets:
            return 0

        count = 0
        for subj, rel, obj in triplets:
            multi_brain_manager.add_triplet(BRAIN_TYPE, subj, rel, obj)
            count += 1

        with self._stats_lock:
            self._total_triplets_extracted += count
            self._total_prompts_processed += 1

        logger.info(
            "[GeminiWatcher] Added %d triplets to brain '%s'",
            count,
            BRAIN_TYPE,
        )
        return count

    # ── Ollama Call ─────────────────────────────────────────────────────

    def _call_ollama(self, text_content: str) -> list[tuple[str, str, str]]:
        """Send *text_content* to Ollama and parse the JSON triplet response.

        Returns:
            List of ``(subject, relation, object)`` tuples. Empty on failure.
        """
        if not text_content.strip():
            return []

        payload = {
            "model": self.ollama_model,
            "system": EXTRACTION_SYSTEM_PROMPT,
            "prompt": text_content.strip()[:4000],  # cap input length
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "top_p": 0.9},
        }

        try:
            resp = self._http_client.post(
                f"{self.ollama_host}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "").strip()
        except httpx.HTTPStatusError as exc:
            msg = f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.warning("[GeminiWatcher] %s", msg)
            with self._stats_lock:
                self._last_error = msg
            return []
        except httpx.RequestError as exc:
            msg = f"Ollama connection error: {exc}"
            logger.warning("[GeminiWatcher] %s", msg)
            with self._stats_lock:
                self._last_error = msg
            return []
        except (json.JSONDecodeError, KeyError) as exc:
            msg = f"Ollama response parse error: {exc}"
            logger.warning("[GeminiWatcher] %s", msg)
            with self._stats_lock:
                self._last_error = msg
            return []

        # Parse the JSON array
        triplets: list[tuple[str, str, str]] = []
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                logger.warning(
                    "[GeminiWatcher] Ollama response not a JSON array: %s …", raw[:200]
                )
                return []

            for item in parsed:
                if not isinstance(item, list) or len(item) != 3:
                    continue
                subj, rel, obj = item
                # Normalise (matching BARQGraphBrain._normalize_entity logic)
                subj = str(subj).strip().lower()[:80]
                obj = str(obj).strip().lower()[:80]
                rel = str(rel).strip().upper().replace(" ", "_") or "RELATED_TO"
                if subj and obj:
                    triplets.append((subj, rel, obj))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            msg = f"Triplet decode error: {exc}"
            logger.warning("[GeminiWatcher] %s", msg)
            with self._stats_lock:
                self._last_error = msg

        logger.debug(
            "[GeminiWatcher] Extracted %d triplets from %d chars",
            len(triplets),
            len(text_content),
        )
        return triplets

    # ── Statistics ──────────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Return extractor statistics."""
        with self._stats_lock:
            return {
                "total_prompts_processed": self._total_prompts_processed,
                "total_triplets_extracted": self._total_triplets_extracted,
                "last_error": self._last_error,
                "ollama_host": self.ollama_host,
                "ollama_model": self.ollama_model,
            }

    def reset_stats(self) -> None:
        """Reset all statistics counters."""
        with self._stats_lock:
            self._total_triplets_extracted = 0
            self._total_prompts_processed = 0
            self._last_error = None

    def close(self) -> None:
        """Close the underlying HTTP client."""
        try:
            self._http_client.close()
        except Exception:
            pass


# ─── Module-level singleton ─────────────────────────────────────────────────

_extractor: GeminiTripletExtractor = GeminiTripletExtractor()


def get_extractor() -> GeminiTripletExtractor:
    """Return the singleton ``GeminiTripletExtractor`` instance."""
    return _extractor


# ═════════════════════════════════════════════════════════════════════════════
#  GeminiFileWatcher — Directory Watcher with EvoMap Resilience Logging
# ═════════════════════════════════════════════════════════════════════════════


class GeminiFileWatcher:
    """Background service that watches ``data/ingest/ai_chats/`` for new files.

    Supports two modes:

    1. **``watchdog`` mode** (default if ``watchdog`` is installed):
       Uses ``watchdog.Observer`` for instant file-system event notifications.

    2. **Polling mode** (fallback):
       Periodically scans the directory every ``POLL_INTERVAL`` seconds.

    On each new file, the watcher:
    1. Waits for the file write to stabilise (size check)
    2. Parses the file (JSON Google Takeout or HTML) into clean prompt text
    3. Sends prompts to Ollama for triplet extraction
    4. Injects triplets into the ``ai_chats`` brain via ``MultiBrainManager``
    5. **Deletes** the source file to prevent re-processing loops
    6. Persists the brain to disk

    All errors are logged as ``EvolutionEvent`` entries in
    ``./memory/evolution/`` for the EvoMap/Evolver daemon.
    """

    def __init__(
        self,
        watch_dir: str | None = None,
        extractor: GeminiTripletExtractor | None = None,
        parser: GeminiParser | None = None,
    ) -> None:
        self.watch_dir = watch_dir or WATCH_DIR
        self.extractor = extractor or _extractor
        self.parser = parser or GeminiParser()
        self._evolution_logger = get_evolution_logger()

        # Watchdog mode state
        self._observer: Any = None
        self._handler: Any = None

        # Polling mode state
        self._poll_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

        # Thread-unsafe: processed set (used by watchdog handler only)
        self._processed_files: set[str] = set()
        self._processed_lock = Lock()

        self._running = False

        # Ensure the watch directory exists
        Path(self.watch_dir).mkdir(parents=True, exist_ok=True)

        if not _HAS_WATCHDOG:
            logger.info(
                "[GeminiWatcher] watchdog not installed — using async polling "
                "mode (interval=%ds). Install with: pip install watchdog",
                _POLL_INTERVAL,
            )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def mode(self) -> str:
        return "watchdog" if _HAS_WATCHDOG else "polling"

    # ── Start / Stop ───────────────────────────────────────────────────

    def start(self) -> None:
        """Start watching the directory."""
        if self._running:
            logger.info("[GeminiWatcher] Already running")
            return

        if _HAS_WATCHDOG:
            self._start_watchdog()
        else:
            self._start_polling()

        self._running = True
        logger.info(
            "[GeminiWatcher] Started — watching %s (mode=%s)",
            self.watch_dir,
            self.mode,
        )

    def stop(self) -> None:
        """Stop watching the directory."""
        if not self._running:
            return

        if _HAS_WATCHDOG:
            self._stop_watchdog()
        else:
            self._stop_polling()

        self._running = False
        logger.info("[GeminiWatcher] Stopped")

    def close(self) -> None:
        """Clean up all resources."""
        self.stop()
        self.extractor.close()

    # ── Watchdog Mode ──────────────────────────────────────────────────

    def _start_watchdog(self) -> None:
        """Start the watchdog observer."""
        handler = _GeminiWatchdogHandler(self)
        observer = _WatchdogObserver()
        observer.schedule(handler, self.watch_dir, recursive=False)
        observer.start()
        self._observer = observer
        self._handler = handler
        logger.info(
            "[GeminiWatcher] Watchdog observer started (recursive=False, dir=%s)",
            self.watch_dir,
        )

    def _stop_watchdog(self) -> None:
        """Stop the watchdog observer."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            self._handler = None

    # ── Polling Mode (Async) ───────────────────────────────────────────

    def _start_polling(self) -> None:
        """Start the asyncio-based polling loop."""
        self._stop_event.clear()
        self._poll_task = asyncio.create_task(self._poll_loop())

    def _stop_polling(self) -> None:
        """Stop the asyncio-based polling loop."""
        self._stop_event.set()
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()

    async def _poll_loop(self) -> None:
        """Main polling loop — periodically scans the watch directory.

        File stability checks (``_wait_for_stable_file``) involve blocking
        ``time.sleep`` calls, so each file scan is dispatched to a thread
        via ``asyncio.to_thread`` to avoid blocking the event loop.
        """
        while not self._stop_event.is_set():
            try:
                await asyncio.to_thread(self._scan_directory)
            except Exception as exc:
                logger.error("[GeminiWatcher] Poll error: %s", exc)
                self._record_evolution_event(
                    event_type="watcher_poll_error",
                    metadata={"error": str(exc)},
                )
            await asyncio.sleep(_POLL_INTERVAL)

    # ─── Directory Scanning ────────────────────────────────────────────

    def _scan_directory(self) -> None:
        """Scan the watch directory for new files and process them."""
        path = Path(self.watch_dir)
        if not path.exists():
            return

        for file_path in sorted(path.iterdir()):
            if not file_path.is_file():
                continue

            resolved = str(file_path.resolve())
            with self._processed_lock:
                if resolved in self._processed_files:
                    continue

            if file_path.suffix.lower() in _SKIP_SUFFIXES:
                continue
            if file_path.suffix.lower().endswith(".failed"):
                continue

            self._process_file(resolved)

    # ─── Core Processing Pipeline ──────────────────────────────────────

    def _process_file(self, file_path: str) -> int:
        """Process a single file through the full ingestion pipeline.

        Pipeline: stabilise → parse → extract triplets → inject → delete.
        All errors are recorded as EvolutionEvents.

        Returns:
            Number of triplets added (0 on failure or empty content).
        """
        path = Path(file_path)

        # ── 1. Wait for file to finish writing ──────────────────────────
        if not self._wait_for_stable_file(path):
            logger.warning(
                "[GeminiWatcher] File %s never stabilised — skipping",
                path.name,
            )
            self._record_evolution_event(
                event_type="file_stability_timeout",
                metadata={"file": path.name, "path": file_path},
            )
            return 0

        # Mark as processed early to avoid re-entry
        with self._processed_lock:
            self._processed_files.add(file_path)

        logger.info("[GeminiWatcher] Processing: %s", path.name)

        # ── 2. Parse the file ──────────────────────────────────────────
        try:
            prompt_text = self.parser.parse(file_path)
        except Exception as exc:
            logger.error("[GeminiWatcher] Parse error for %s: %s", path.name, exc)
            self._record_evolution_event(
                event_type="parse_error",
                duration_ms=0.0,
                metadata={
                    "file": path.name,
                    "format": path.suffix.lower(),
                    "error": str(exc),
                },
            )
            # Rename to .failed so the file can be inspected later
            self._safe_rename_to_failed(file_path)
            return 0

        if not prompt_text:
            logger.info(
                "[GeminiWatcher] No prompt content in %s — deleting",
                path.name,
            )
            self._safe_delete(file_path)
            return 0

        # ── 3. Extract triplets via Ollama ─────────────────────────────
        try:
            count = self.extractor.process_prompt(prompt_text)
        except Exception as exc:
            logger.error(
                "[GeminiWatcher] Triplet extraction error for %s: %s",
                path.name,
                exc,
            )
            self._record_evolution_event(
                event_type="extraction_error",
                duration_ms=0.0,
                metadata={
                    "file": path.name,
                    "prompt_length": len(prompt_text),
                    "error": str(exc),
                },
            )
            # Rename to .failed on extraction failure so the file can be
            # inspected later (transient Ollama errors should not destroy data)
            self._safe_rename_to_failed(file_path)
            return 0

        # ── 4. Persist the brain ───────────────────────────────────────
        if count > 0:
            try:
                multi_brain_manager.save_brain(BRAIN_TYPE)
                logger.info(
                    "[GeminiWatcher] %s → %d triplets → brain '%s' persisted",
                    path.name,
                    count,
                    BRAIN_TYPE,
                )
            except Exception as exc:
                logger.warning(
                    "[GeminiWatcher] Failed to persist brain after %s: %s",
                    path.name,
                    exc,
                )
                self._record_evolution_event(
                    event_type="brain_persist_error",
                    metadata={
                        "file": path.name,
                        "triplets": count,
                        "error": str(exc),
                    },
                )
        else:
            logger.info(
                "[GeminiWatcher] %s → 0 triplets extracted (no relationships found)",
                path.name,
            )

        # ── 5. Delete the source file on success ───────────────────────
        self._safe_delete(file_path)
        return count

    # ─── File Utilities ────────────────────────────────────────────────

    @staticmethod
    def _wait_for_stable_file(
        path: Path,
        max_retries: int = _FILE_STABILITY_RETRIES,
        delay: float = _FILE_STABILITY_DELAY,
    ) -> bool:
        """Wait until the file size stabilises (finished copying/downloading).

        Checks that the file size is unchanged across consecutive polls
        and that the file is > 0 bytes.

        This is a **blocking** call (``time.sleep``). When called from
        the async polling loop, it is wrapped via ``asyncio.to_thread``
        to avoid blocking the event loop.
        """
        prev_size = -1
        for _ in range(max_retries):
            if not path.exists():
                return False
            try:
                curr_size = path.stat().st_size
                if curr_size == prev_size and curr_size > 0:
                    return True
                prev_size = curr_size
            except OSError:
                return False
            time.sleep(delay)
        return False

    async def _wait_for_stable_file_async(
        self, path: Path,
    ) -> bool:
        """Async-safe wrapper that runs the blocking stability check in a thread."""
        return await asyncio.to_thread(
            self._wait_for_stable_file,
            path,
            _FILE_STABILITY_RETRIES,
            _FILE_STABILITY_DELAY,
        )

    @staticmethod
    def _safe_delete(file_path: str) -> bool:
        """Safely delete a file, logging but not raising on failure."""
        try:
            os.remove(file_path)
            logger.debug("[GeminiWatcher] Deleted: %s", file_path)
            return True
        except OSError as exc:
            logger.warning("[GeminiWatcher] Failed to delete %s: %s", file_path, exc)
            return False

    @staticmethod
    def _safe_rename_to_failed(file_path: str) -> str | None:
        """Rename a failed file to ``.failed`` so it can be inspected but not
        re-processed. Returns the new path or ``None`` on failure."""
        path = Path(file_path)
        failed_path = path.with_suffix(path.suffix + ".failed")
        try:
            path.rename(failed_path)
            logger.debug("[GeminiWatcher] Renamed failed file: %s → %s", file_path, failed_path)
            return str(failed_path)
        except OSError as exc:
            logger.warning("[GeminiWatcher] Failed to rename %s: %s", file_path, exc)
            return None

    # ─── EvoMap/Evolver Resilience Logging ─────────────────────────────

    def _record_evolution_event(
        self,
        event_type: str,
        duration_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a telemetry event to ``./memory/evolution/``.

        Follows the GEP (Genome Evolution Protocol) pattern established by
        ``EvolutionLogger`` for the EvoMap/Evolver daemon.
        """
        try:
            self._evolution_logger.record(
                event_type=f"gemini_watcher_{event_type}",
                duration_ms=duration_ms,
                metadata={
                    "service": "gemini_watcher",
                    "brain_type": BRAIN_TYPE,
                    "watch_dir": self.watch_dir,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **(metadata or {}),
                },
            )
            # Flush critical events immediately so the evolver daemon
            # can react promptly to failures
            if event_type in (
                "parse_error",
                "extraction_error",
                "ollama_timeout",
                "brain_persist_error",
            ):
                self._evolution_logger.flush()
        except Exception as exc:
            logger.warning("[GeminiWatcher] Failed to record evolution event: %s", exc)

    # ─── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return current watcher and extractor statistics."""
        return {
            "running": self._running,
            "mode": self.mode,
            "watch_dir": self.watch_dir,
            "brain_type": BRAIN_TYPE,
            "has_watchdog": _HAS_WATCHDOG,
            "has_beautifulsoup": _HAS_BS4,
            "extractor": self.extractor.stats,
        }

    def process_all_existing(self) -> int:
        """Process any files already present in the watch directory.

        Returns:
            Total number of triplets added across all files.
        """
        path = Path(self.watch_dir)
        if not path.exists():
            return 0

        total = 0
        for file_path in sorted(path.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() in _SKIP_SUFFIXES:
                continue
            if file_path.suffix.lower().endswith(".failed"):
                continue
            count = self._process_file(str(file_path.resolve()))
            total += count

        logger.info("[GeminiWatcher] Processed %d total triplets from existing files", total)
        return total


# ═════════════════════════════════════════════════════════════════════════════
#  Module-level singleton (matching project convention)
# ═════════════════════════════════════════════════════════════════════════════

_gemini_watcher: GeminiFileWatcher = GeminiFileWatcher()


def get_gemini_watcher() -> GeminiFileWatcher:
    """Return the singleton ``GeminiFileWatcher`` instance."""
    return _gemini_watcher


# ═════════════════════════════════════════════════════════════════════════════
#  FastAPI Startup Registration Snippet
#
#  Paste this block into ``python/main.py`` inside the ``lifespan``
#  async context manager (after the existing ingestion watcher block):
#
#  .. code-block:: python
#
#      # ── Start Gemini File Watcher ───────────────────────────────────
#      _gemini_watcher = None
#      try:
#          from app.services.gemini_watcher import GeminiFileWatcher
#
#          _gemini_watcher = GeminiFileWatcher()
#          _gemini_watcher.process_all_existing()
#          _gemini_watcher.start()
#          print("[BARQ Sidecar] Gemini file watcher started")
#      except Exception as e:
#          print(f"[BARQ Sidecar] Gemini file watcher start error: {e}")
#
#  And in the shutdown section:
#
#  .. code-block:: python
#
#      if _gemini_watcher is not None:
#          try:
#              _gemini_watcher.close()
#              print("[BARQ Sidecar] Gemini file watcher stopped")
#          except Exception:
#              pass
#
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # CLI entrypoint for testing
    import argparse

    parser = argparse.ArgumentParser(
        description="BARQ Gemini File Watcher — ingest Gemini chat history into the ai_chats brain",
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Start watching the directory (blocking)",
    )
    parser.add_argument(
        "--once", "-1",
        action="store_true",
        help="Process all existing files and exit",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Process a single file and exit",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=WATCH_DIR,
        help=f"Watch directory (default: {WATCH_DIR})",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.file:
        # Process a single file
        watcher = GeminiFileWatcher(watch_dir=args.dir)
        watcher._process_file(args.file)
        print(f"Stats: {watcher.get_stats()}")
    elif args.once:
        watcher = GeminiFileWatcher(watch_dir=args.dir)
        total = watcher.process_all_existing()
        print(f"Total triplets added: {total}")
    elif args.watch:
        watcher = GeminiFileWatcher(watch_dir=args.dir)
        watcher.process_all_existing()
        watcher.start()
        print(f"[GeminiWatcher] Watching {args.dir} (mode={watcher.mode})")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down ...")
            watcher.close()
    else:
        parser.print_help()
