"""
BARQ Ingestion Pipeline — drop-folder watcher, file parser, and Ollama
triplet extraction for domain-specific knowledge graphs.

Flow
----
1. A file lands in ``data/dropbox/{apple_notes, google_docs, ai_chats, career, general}/``
2. ``IngestionParser`` converts it to clean Markdown (``.md``)
3. ``TripletExtractor`` sends the Markdown to Ollama (``llama3.1:8b``) using the
   ``EXTRACTION_SYSTEM_PROMPT`` prompt from ``graph_brain.py``
4. The resulting ``["Subject", "RELATIONSHIP", "Object"]`` triplets are routed
   into the correct isolated ``MultiBrainManager`` brain based on the source folder
5. The affected brain is auto-persisted to ``data/brains/{brain_type}.json``
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from threading import Lock
from typing import Any, Optional

import httpx

# ─── Conditional watchdog import ─────────────────────────────────────────────

_HAS_WATCHDOG = False
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    _HAS_WATCHDOG = True
except ImportError:
    FileSystemEventHandler = object  # type: ignore[misc, assignment]
    Observer = None  # type: ignore[assignment, misc]

from graph_brain import EXTRACTION_SYSTEM_PROMPT
from memory_knowledge.multi_brain import BRAIN_REGISTRY, multi_brain_manager
from config import get_settings

logger = logging.getLogger("barq.ingestion")

# ─── Folder → Brain Type Mapping ────────────────────────────────────────────

BRAIN_FOLDER_MAP: dict[str, str] = {
    "apple_notes": "apple_notes",
    "google_docs": "google_docs",
    "ai_chats": "ai_chats",
    "career": "career",
    "gemini_chats": "gemini_chats",
    "general": "general",
}

# ─── Drop-box base directory ────────────────────────────────────────────────

_DEFAULT_DROPBOX = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dropbox"
)


def get_dropbox_base() -> str:
    """Return the drop-box base directory, creating it if needed."""
    base = _DEFAULT_DROPBOX
    Path(base).mkdir(parents=True, exist_ok=True)
    for folder in BRAIN_FOLDER_MAP:
        Path(base, folder).mkdir(parents=True, exist_ok=True)
    return base


# ═════════════════════════════════════════════════════════════════════════════
#  IngestionParser — convert any supported input format to Markdown
# ═════════════════════════════════════════════════════════════════════════════


class IngestionParser:
    """Convert various input formats into clean, uniform Markdown.

    Supported input formats:
    - ``.txt`` — plain text (passthrough)
    - ``.md`` — already Markdown (passthrough)
    - ``.json`` — AI Chat exports (array of ``{role, content}`` objects)
    - ``.html`` — Apple Notes / Google Docs HTML exports
    """

    # ── Public API ──────────────────────────────────────────────────────

    def parse(self, file_path: str) -> str:
        """Read *file_path* and return clean Markdown.

        Args:
            file_path: Absolute or relative path to the source file.

        Returns:
            Markdown string ready for triplet extraction.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("IngestionParser: file not found — %s", file_path)
            return ""

        suffix = path.suffix.lower()
        raw = path.read_text(encoding="utf-8", errors="replace")

        if suffix == ".json":
            return self._parse_json_chat(raw)
        elif suffix == ".html":
            return self._parse_html(raw)
        elif suffix in (".txt", ".md"):
            return self._clean_text(raw)
        else:
            logger.debug("IngestionParser: unknown suffix %s, treating as text", suffix)
            return self._clean_text(raw)

    # ── JSON Chat Parser ────────────────────────────────────────────────

    def _parse_json_chat(self, raw: str) -> str:
        """Convert an AI chat JSON export to Markdown conversation format.

        Supports:
        - Generic: JSON array of ``{"role", "content"}`` objects
        - Dict with ``"messages"`` / ``"conversation"`` / ``"chats"`` key
        - **Google Takeout** format: ``{"conversations": [{...}]}``
        - **Google AI Studio** format: ``{"contents": [{role, parts}]}``
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("IngestionParser: invalid JSON chat — falling back to raw text")
            return self._clean_text(raw)

        messages: list[dict[str, Any]] = []

        if isinstance(data, list):
            messages = data
        elif isinstance(data, dict):
            # Google Takeout format
            if "conversations" in data:
                convs = data["conversations"]
                return self._parse_takeout_conversations(convs)
            # Google AI Studio format
            if "contents" in data:
                return self._parse_ai_studio_contents(data["contents"])
            # Generic dict formats
            messages = data.get("messages", data.get("conversation", data.get("chats", [])))
            if not messages and "title" in data and "content" in data:
                return self._clean_text(f"# {data['title']}\n\n{data['content']}")

        if not messages or not isinstance(messages, list):
            return self._clean_text(raw)

        md_parts: list[str] = []
        for msg in messages:
            role = str(msg.get("role", msg.get("author", msg.get("from", "unknown")))).capitalize()
            content = str(msg.get("content", msg.get("text", "")))
            if content:
                md_parts.append(f"**{role}:** {content.strip()}")

        result = "\n\n".join(md_parts) if md_parts else self._clean_text(raw)
        return result

    def _parse_takeout_conversations(self, conversations: list[dict]) -> str:
        """Parse Google Takeout conversations array into Markdown."""
        md_parts: list[str] = []
        for conv in conversations[:50]:  # Limit to first 50 conversations
            title = conv.get("title", "Untitled")
            md_parts.append(f"# Conversation: {title}")
            for msg in conv.get("messages", []):
                author = str(msg.get("author", "unknown")).capitalize()
                content_parts = msg.get("content", [])
                if isinstance(content_parts, list):
                    text = " ".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in content_parts
                    )
                else:
                    text = str(content_parts)
                if text.strip():
                    md_parts.append(f"**{author}:** {text.strip()}")
            md_parts.append("")
        return "\n\n".join(md_parts) if md_parts else ""

    def _parse_ai_studio_contents(self, contents: list[dict]) -> str:
        """Parse Google AI Studio contents array into Markdown."""
        md_parts: list[str] = []
        for msg in contents:
            role = str(msg.get("role", "unknown")).capitalize()
            parts = msg.get("parts", [])
            text_parts: list[str] = []
            for part in parts:
                if isinstance(part, dict):
                    text_parts.append(part.get("text", ""))
                else:
                    text_parts.append(str(part))
            text = " ".join(tp for tp in text_parts if tp.strip())
            if text.strip():
                md_parts.append(f"**{role}:** {text.strip()}")
        return "\n\n".join(md_parts) if md_parts else ""

    # ── HTML Parser ─────────────────────────────────────────────────────

    def _parse_html(self, raw: str) -> str:
        """Strip HTML tags and return clean text as Markdown.

        Preserves headers (h1-h6 → # headers), links ([text](url)),
        and line breaks. Everything else is plain text.
        """
        # Extract <title> if present
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Remove <style> and <script> blocks
        cleaned = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<script[^>]*>.*?</script>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)

        # Convert <br> and </p> to newlines
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</p>", "\n\n", cleaned, flags=re.IGNORECASE)

        # Convert headers
        for i in range(1, 7):
            cleaned = re.sub(
                rf"<h{i}[^>]*>(.*?)</h{i}>",
                f"{'#' * i} \\1",
                cleaned,
                flags=re.IGNORECASE | re.DOTALL,
            )

        # Convert links
        cleaned = re.sub(
            r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            r"[\2](\1)",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # Strip remaining tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)

        # Decode common HTML entities
        cleaned = cleaned.replace("&amp;", "&")
        cleaned = cleaned.replace("&lt;", "<")
        cleaned = cleaned.replace("&gt;", ">")
        cleaned = cleaned.replace("&nbsp;", " ")
        cleaned = cleaned.replace("&quot;", '"')
        cleaned = cleaned.replace("&#39;", "'")

        # Collapse excessive whitespace
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r" {2,}", " ", cleaned)
        result = cleaned.strip()

        if title and not result.startswith("#"):
            result = f"# {title}\n\n{result}"

        return result

    # ── Text Cleaner ────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(raw: str) -> str:
        """Basic text cleaning: strip BOM, normalise newlines, trim."""
        text = raw.lstrip("\ufeff")  # Remove UTF-8 BOM
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()


# ═════════════════════════════════════════════════════════════════════════════
#  TripletExtractor — Ollama LLM → MultiBrainManager
# ═════════════════════════════════════════════════════════════════════════════


class TripletExtractor:
    """Extract ``[Subject, RELATIONSHIP, Object]`` triplets from Markdown
    content using the local Ollama LLM, and route them into the correct
    ``MultiBrainManager`` brain.

    Reuses the same ``EXTRACTION_SYSTEM_PROMPT`` and ``httpx``-based
    Ollama call pattern from ``graph_brain.py``.
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
        self._total_documents_processed: int = 0
        self._last_error: Optional[str] = None

    # ── Public API ──────────────────────────────────────────────────────

    def process_document(self, brain_type: str, markdown_content: str) -> int:
        """Extract triplets from *markdown_content* and add them to *brain_type*.

        Args:
            brain_type: Which brain to insert into (e.g. ``"ai_chats"``).
            markdown_content: Cleaned Markdown text (from ``IngestionParser``).

        Returns:
            Number of triplets successfully added.
        """
        if not markdown_content.strip():
            return 0

        triplets = self._call_ollama(markdown_content)
        if not triplets:
            return 0

        count = 0
        for subj, rel, obj in triplets:
            multi_brain_manager.add_triplet(brain_type, subj, rel, obj)
            count += 1

        with self._stats_lock:
            self._total_triplets_extracted += count
            self._total_documents_processed += 1

        logger.info(
            "[Ingestion] Added %d triplets to brain '%s' (%s)",
            count, brain_type, BRAIN_REGISTRY.get(brain_type, {}).get("label", brain_type),
        )
        return count

    def process_file(self, brain_type: str, file_path: str) -> int:
        """Read *file_path*, parse to Markdown, extract triplets, route to brain.

        Args:
            brain_type: Target brain (e.g. ``"apple_notes"``).
            file_path: Path to the source file.

        Returns:
            Number of triplets added, or 0 on failure.
        """
        try:
            parser = IngestionParser()
            markdown = parser.parse(file_path)
            if not markdown:
                logger.debug("[Ingestion] No content extracted from %s", file_path)
                return 0
            return self.process_document(brain_type, markdown)
        except Exception as exc:
            logger.error("[Ingestion] Failed to process %s: %s", file_path, exc)
            with self._stats_lock:
                self._last_error = str(exc)
            return 0

    # ── Ollama Call ─────────────────────────────────────────────────────

    def _call_ollama(self, text_content: str) -> list[tuple[str, str, str]]:
        """Send *text_content* to Ollama and parse the triplet JSON response.

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
            logger.warning(
                "[Ingestion] Ollama HTTP %s: %s",
                exc.response.status_code, exc.response.text[:200],
            )
            with self._stats_lock:
                self._last_error = f"Ollama HTTP {exc.response.status_code}"
            return []
        except httpx.RequestError as exc:
            logger.warning("[Ingestion] Ollama request failed: %s", exc)
            with self._stats_lock:
                self._last_error = f"Ollama connection error: {exc}"
            return []
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("[Ingestion] Ollama response parse error: %s", exc)
            with self._stats_lock:
                self._last_error = f"Ollama response parse error: {exc}"
            return []

        # Parse the JSON array
        triplets: list[tuple[str, str, str]] = []
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                logger.warning("[Ingestion] Ollama response not a JSON array: %s …", raw[:200])
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
            logger.warning("[Ingestion] Triplet decode error: %s\nRaw: %s …", exc, raw[:200])
            with self._stats_lock:
                self._last_error = f"Triplet decode error: {exc}"

        logger.debug("[Ingestion] Extracted %d triplets from %d chars", len(triplets), len(text_content))
        return triplets

    # ── Statistics ──────────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Return extractor statistics."""
        with self._stats_lock:
            return {
                "total_documents_processed": self._total_documents_processed,
                "total_triplets_extracted": self._total_triplets_extracted,
                "last_error": self._last_error,
                "ollama_host": self.ollama_host,
                "ollama_model": self.ollama_model,
            }

    def reset_stats(self) -> None:
        """Reset all statistics counters."""
        with self._stats_lock:
            self._total_triplets_extracted = 0
            self._total_documents_processed = 0
            self._last_error = None


# ─── Module-level singleton (matching project convention) ───────────────────

_triplet_extractor: TripletExtractor = TripletExtractor()


def get_extractor() -> TripletExtractor:
    """Return the singleton ``TripletExtractor`` instance."""
    return _triplet_extractor


# ═════════════════════════════════════════════════════════════════════════════
#  DropFolderMonitor — watchdog-based file watcher
# ═════════════════════════════════════════════════════════════════════════════


class DropFolderHandler(FileSystemEventHandler):
    """Watchdog event handler that processes new files dropped into any
    brain-specific subfolder.
    """

    def __init__(self, extractor: TripletExtractor, parser: IngestionParser) -> None:
        super().__init__()
        self.extractor = extractor
        self.parser = parser
        self._processed = _ProcessedFiles()

    def on_created(self, event: Any) -> None:
        """Called when a new file is created in a watched directory."""
        self._handle_event(event)

    def on_moved(self, event: Any) -> None:
        """Called when a file is moved (e.g. copy-then-rename into dropbox)."""
        if hasattr(event, "dest_path"):
            self._handle_path(event.dest_path)

    def _handle_event(self, event: Any) -> None:
        if event.is_directory:
            return
        self._handle_path(event.src_path)

    def _handle_path(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.is_file():
            return
        if path.suffix.lower() in (".tmp", ".part", ".download", ".crdownload"):
            return  # skip in-progress downloads
        if self._processed.was_processed(file_path):
            return

        # Determine brain type from parent folder name
        brain_type = self._resolve_brain_type(file_path)
        if not brain_type:
            # Check grandparent folder too (in case there's a subfolder level)
            brain_type = self._resolve_brain_type(str(path.parent.parent))
        if not brain_type:
            logger.debug("[Ingestion] File outside known brain folder: %s", file_path)
            return

        logger.info("[Ingestion] New file detected: %s → brain '%s'", file_path, brain_type)

        # Wait briefly for the file to finish writing
        self._wait_for_file(path)
        time.sleep(0.5)

        # Process
        try:
            count = self.extractor.process_file(brain_type, str(path))
            self._processed.mark_processed(file_path)
            if count > 0:
                # Auto-persist the affected brain
                multi_brain_manager.save_brain(brain_type)
                logger.info(
                    "[Ingestion] Processed %s → %d triplets added to '%s'",
                    path.name, count, brain_type,
                )
        except Exception as exc:
            logger.error("[Ingestion] Error processing %s: %s", file_path, exc)

    @staticmethod
    def _resolve_brain_type(file_path: str) -> Optional[str]:
        """Map the parent folder name to a brain type.

        Walks up to 2 parent levels to handle nested drop structures.
        """
        path = Path(file_path)
        parent = path.parent.name.lower()
        if parent in BRAIN_FOLDER_MAP:
            return BRAIN_FOLDER_MAP[parent]
        grandparent = path.parent.parent.name.lower()
        if grandparent in BRAIN_FOLDER_MAP:
            return BRAIN_FOLDER_MAP[grandparent]
        return None

    @staticmethod
    def _wait_for_file(path: Path, max_retries: int = 5, delay: float = 0.5) -> None:
        """Wait until the file size stabilises (finished copying)."""
        prev_size = -1
        for _ in range(max_retries):
            if not path.exists():
                return
            try:
                curr_size = path.stat().st_size
                if curr_size == prev_size and curr_size > 0:
                    return  # size stable, copy complete
                prev_size = curr_size
            except OSError:
                return
            time.sleep(delay)


class _ProcessedFiles:
    """Thread-safe set of processed file paths (with expiry)."""

    def __init__(self, max_size: int = 1000) -> None:
        self._set: set[str] = set()
        self._max_size = max_size
        self._lock = Lock()

    def was_processed(self, path: str) -> bool:
        resolved = os.path.abspath(path)
        with self._lock:
            return resolved in self._set

    def mark_processed(self, path: str) -> None:
        resolved = os.path.abspath(path)
        with self._lock:
            self._set.add(resolved)
            if len(self._set) > self._max_size:
                # Trim oldest entries
                self._set = set(list(self._set)[-self._max_size // 2 :])


class DropFolderMonitor:
    """Manages watchdog ``Observer`` instances for each brain drop-folder.

    Usage::

        monitor = DropFolderMonitor()
        monitor.start()
        # ...
        monitor.stop()
    """

    def __init__(
        self,
        extractor: Optional[TripletExtractor] = None,
        parser: Optional[IngestionParser] = None,
        dropbox_dir: Optional[str] = None,
    ) -> None:
        self.extractor = extractor or _triplet_extractor
        self.parser = parser or IngestionParser()
        self.dropbox = dropbox_dir or get_dropbox_base()
        self._observer: Any = None
        self._handler: Optional[DropFolderHandler] = None
        self._running = False

        if not _HAS_WATCHDOG:
            logger.warning(
                "[Ingestion] watchdog not installed — file watching disabled. "
                "Install with: pip install watchdog"
            )

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start monitoring all brain drop-folders."""
        if not _HAS_WATCHDOG:
            logger.warning("[Ingestion] Cannot start watcher — watchdog not installed")
            return
        if self._running:
            logger.info("[Ingestion] Watcher already running")
            return

        self._handler = DropFolderHandler(self.extractor, self.parser)
        self._observer = Observer()
        self._observer.schedule(self._handler, self.dropbox, recursive=True)
        self._observer.start()
        self._running = True

        logger.info(
            "[Ingestion] DropFolderMonitor started — watching %s "
            "(brains: %s)",
            self.dropbox,
            ", ".join(sorted(BRAIN_FOLDER_MAP.keys())),
        )

    def stop(self) -> None:
        """Stop the file watcher."""
        if self._observer and self._running:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._running = False
            logger.info("[Ingestion] DropFolderMonitor stopped")

    def process_all_existing(self) -> dict[str, int]:
        """Process any files already present in the drop-folders.

        Returns:
            Dict mapping brain type → number of triplets added.
        """
        results: dict[str, int] = {}
        base = Path(self.dropbox)

        for folder, brain_type in BRAIN_FOLDER_MAP.items():
            folder_path = base / folder
            if not folder_path.exists():
                continue

            brain_count = 0
            for file_path in sorted(folder_path.iterdir()):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() in (".tmp", ".part", ".download", ".crdownload", ".processed"):
                    continue
                count = self.extractor.process_file(brain_type, str(file_path))
                brain_count += count
                if count > 0:
                    # Rename to .processed to avoid re-processing
                    try:
                        file_path.rename(file_path.with_suffix(file_path.suffix + ".processed"))
                    except OSError:
                        pass

            if brain_count > 0:
                multi_brain_manager.save_brain(brain_type)
            results[brain_type] = brain_count

        total = sum(results.values())
        logger.info("[Ingestion] Processed %d triplets from existing files", total)
        return results


# ═════════════════════════════════════════════════════════════════════════════
#  Standalone runner
# ═════════════════════════════════════════════════════════════════════════════


def run_ingestion_once(
    brain_type: Optional[str] = None,
    dropbox_dir: Optional[str] = None,
) -> dict[str, int]:
    """Process all files in one or all drop-folders immediately.

    Args:
        brain_type: If set, process only this brain's folder.
        dropbox_dir: Override the drop-box base directory.

    Returns:
        Dict mapping brain type → number of triplets added.
    """
    base = Path(dropbox_dir or get_dropbox_base())
    extractor = get_extractor()
    parser = IngestionParser()
    results: dict[str, int] = {}

    folders_to_process = (
        [(brain_type, brain_type)]
        if brain_type and brain_type in BRAIN_FOLDER_MAP
        else BRAIN_FOLDER_MAP.items()
    )

    for folder, bt in folders_to_process:
        folder_path = base / folder
        if not folder_path.exists():
            continue
        brain_count = 0
        for file_path in sorted(folder_path.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() in (".tmp", ".part", ".download", ".crdownload", ".processed"):
                continue
            count = extractor.process_file(bt, str(file_path))
            brain_count += count
            if count > 0:
                # Only rename on success so failed files are retried
                try:
                    file_path.rename(file_path.with_suffix(file_path.suffix + ".processed"))
                except OSError:
                    pass
        if brain_count > 0:
            multi_brain_manager.save_brain(bt)
        results[bt] = brain_count

    return results


# ═════════════════════════════════════════════════════════════════════════════
#  CLI Entrypoint
# ═════════════════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI entrypoint for the ingestion pipeline.

    Usage::

        python -m memory_knowledge.ingestion --watch
        python -m memory_knowledge.ingestion --once
        python -m memory_knowledge.ingestion --once --brain ai_chats
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="BARQ Ingestion Pipeline — drop-folder watcher & triplet extraction",
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Start the file watcher (monitor drop-folders continuously)",
    )
    parser.add_argument(
        "--once", "-1",
        action="store_true",
        help="Process all existing files in drop-folders and exit",
    )
    parser.add_argument(
        "--brain", "-b",
        type=str,
        default=None,
        help="Restrict --once to a specific brain type (e.g. ai_chats)",
    )
    parser.add_argument(
        "--dropbox", "-d",
        type=str,
        default=None,
        help="Override the drop-box base directory",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.once:
        logger.info("Running one-shot ingestion%s", f" for brain '{args.brain}'" if args.brain else "")
        results = run_ingestion_once(brain_type=args.brain, dropbox_dir=args.dropbox)
        for brain_type, count in results.items():
            print(f"  {brain_type}: {count} triplets")
        print(f"  Total: {sum(results.values())} triplets")

    if args.watch:
        monitor = DropFolderMonitor(dropbox_dir=args.dropbox)
        monitor.process_all_existing()
        monitor.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down ...")
            monitor.stop()

    if not args.once and not args.watch:
        parser.print_help()


if __name__ == "__main__":
    main()
