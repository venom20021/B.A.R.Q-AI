"""
Gemini Chat Importer — imports real Google Gemini conversation data
into the ``gemini_chats`` knowledge graph brain.

Supports three input formats:
1. **Google Takeout JSON** — ``Takeout/Gemini/MyActivity.json`` (conversations array)
2. **Google AI Studio export** — ``{contents: [{role, parts}]}``
3. **Generic chat JSON** — array of ``{role, content}`` or ``{author, content}``

Each conversation is parsed, entities are extracted from messages, and
knowledge triplets are created in the ``gemini_chats`` brain via
``MultiBrainManager``.  No Ollama call is needed — the extraction uses
lightweight NLP heuristics (keyword extraction, title parsing, relation
inference) so importing 100+ conversations is nearly instant.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from memory_knowledge.multi_brain import multi_brain_manager

logger = logging.getLogger("barq.gemini_importer")

# ─── Constants ───────────────────────────────────────────────────────────────

BRAIN_TYPE = "gemini_chats"
RELATED_TO = "RELATED_TO"
ASKED_ABOUT = "ASKED_ABOUT"
EXPLAINED = "EXPLAINED"
DISCUSSED_IN = "DISCUSSED_IN"

# Common English stop-words and very short words to skip during entity extraction
_STOP_WORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "up", "about", "into", "over", "after", "before", "between", "under",
    "and", "or", "but", "not", "so", "yet", "if", "because", "as",
    "until", "while", "though", "than", "then", "else", "also", "just",
    "very", "too", "quite", "really", "almost", "enough", "how", "when",
    "where", "what", "which", "who", "whom", "this", "that", "these",
    "those", "i", "me", "my", "we", "us", "our", "you", "your", "he",
    "him", "his", "she", "her", "it", "its", "they", "them", "their",
    "no", "yes", "please", "thanks", "thank", "ok", "okay", "sure",
    "tell", "let", "make", "get", "give", "take", "know", "think",
    "want", "like", "help", "can", "could", "answer", "question",
}


@dataclass
class GeminiMessage:
    """A single message from a Gemini conversation."""
    role: str  # "user", "model", "system", "unknown"
    content: str
    timestamp: Optional[str] = None


@dataclass
class GeminiConversation:
    """A single Gemini conversation with its messages."""
    title: str = ""
    messages: list[GeminiMessage] = field(default_factory=list)
    created_at: Optional[str] = None
    source: str = "unknown"  # "takeout", "ai_studio", "generic"
    conversation_id: Optional[str] = None


# ─── Import Results ──────────────────────────────────────────────────────────

@dataclass
class ImportResult:
    """Result of a single import operation."""
    conversations_found: int = 0
    conversations_imported: int = 0
    triplets_added: int = 0
    errors: list[str] = field(default_factory=list)
    file_path: str = ""
    file_format: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_format": self.file_format,
            "conversations_found": self.conversations_found,
            "conversations_imported": self.conversations_imported,
            "triplets_added": self.triplets_added,
            "errors": self.errors,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  Format Detectors & Parsers
# ═════════════════════════════════════════════════════════════════════════════


def _detect_format(data: Any) -> str:
    """Detect the format of a parsed JSON structure.

    Returns one of ``"takeout"``, ``"ai_studio"``, ``"generic"``.
    """
    if isinstance(data, dict):
        # Google Takeout: has "conversations" key (or "activity" key)
        if "conversations" in data:
            return "takeout"
        # AI Studio: has "contents" key
        if "contents" in data:
            return "ai_studio"
        # May have a "messages" key at top level
        if "messages" in data:
            return "generic"
    if isinstance(data, list):
        return "generic"
    return "generic"


def _parse_takeout_conversations(data: dict) -> list[GeminiConversation]:
    """Parse Google Takeout Gemini export JSON.

    Expected structure::
        {
          "conversations": [
            {
              "title": "...",
              "createTime": "...",
              "messages": [
                {
                  "author": "user" | "model",
                  "content": [{"text": "..."}],
                  "createTime": "..."
                }
              ]
            }
          ]
        }
    """
    conversations: list[GeminiConversation] = []
    raw = data.get("conversations", [])

    for conv_data in raw:
        title = conv_data.get("title", "") or ""
        created_at = conv_data.get("createTime", conv_data.get("updateTime"))
        conv_id = conv_data.get("conversationId", conv_data.get("id"))

        messages: list[GeminiMessage] = []
        raw_messages = conv_data.get("messages", [])
        if not raw_messages:
            # Some Takeout exports nest messages under "events" or omit them
            raw_messages = conv_data.get("events", [])

        for msg in raw_messages:
            author = str(msg.get("author", msg.get("role", "unknown"))).lower()
            # Map "model" or "assistant" to "model"
            if author in ("model", "assistant", "bard", "gemini"):
                role = "model"
            elif author in ("user", "human"):
                role = "user"
            else:
                role = "unknown"

            content_parts = msg.get("content", [])
            if isinstance(content_parts, str):
                text = content_parts
            elif isinstance(content_parts, list):
                text = " ".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content_parts
                )
            elif isinstance(content_parts, dict):
                text = content_parts.get("text", "")
            else:
                text = str(content_parts) if content_parts else ""

            if text.strip():
                messages.append(GeminiMessage(
                    role=role,
                    content=text.strip(),
                    timestamp=msg.get("createTime"),
                ))

        if messages:
            # Derive title from first user message if no title set
            if not title:
                first_user = next((m for m in messages if m.role == "user"), None)
                if first_user:
                    title = first_user.content[:80]
                    if len(first_user.content) > 80:
                        title += "…"

            conversations.append(GeminiConversation(
                title=title,
                messages=messages,
                created_at=created_at,
                source="takeout",
                conversation_id=conv_id,
            ))

    return conversations


def _parse_ai_studio_conversations(data: dict) -> list[GeminiConversation]:
    """Parse Google AI Studio export JSON.

    Expected structure::
        {
          "contents": [
            {
              "role": "user" | "model",
              "parts": [{"text": "..."}]
            }
          ]
        }

    AI Studio exports are single conversations (no title field).
    """
    conversations: list[GeminiConversation] = []
    raw_messages = data.get("contents", [])

    messages: list[GeminiMessage] = []
    for msg in raw_messages:
        role = str(msg.get("role", "unknown")).lower()
        parts = msg.get("parts", [])
        text_parts: list[str] = []
        for part in parts:
            if isinstance(part, dict):
                text_parts.append(part.get("text", ""))
            else:
                text_parts.append(str(part))
        text = " ".join(tp for tp in text_parts if tp.strip())

        if text.strip():
            messages.append(GeminiMessage(
                role=role,
                content=text.strip(),
            ))

    if messages:
        first_user = next((m for m in messages if m.role == "user"), None)
        title = first_user.content[:80] + "…" if first_user and len(first_user.content) > 80 else (first_user.content if first_user else "Gemini AI Studio Chat")
        conversations.append(GeminiConversation(
            title=title,
            messages=messages,
            source="ai_studio",
        ))

    return conversations


def _parse_generic_chat(data: Any) -> list[GeminiConversation]:
    """Parse a generic chat JSON format.

    Accepts:
    - A JSON list of ``{"role": ..., "content": ...}`` or ``{"author": ..., "content": ...}``
    - A dict with ``"messages"`` key containing such a list
    - A dict with ``"chats"`` or ``"conversation"`` key
    """
    messages_list: list[dict] = []

    if isinstance(data, list):
        messages_list = data
    elif isinstance(data, dict):
        messages_list = (
            data.get("messages") or
            data.get("chats") or
            data.get("conversation") or
            data.get("history") or
            []
        )
    else:
        return []

    if not isinstance(messages_list, list):
        return []

    messages: list[GeminiMessage] = []
    for msg in messages_list:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", msg.get("author", msg.get("from", "unknown")))).lower()
        if role in ("model", "assistant", "bard", "gemini", "ai"):
            role = "model"
        elif role in ("user", "human", "me"):
            role = "user"

        content = str(msg.get("content", msg.get("text", msg.get("message", ""))))

        if content.strip():
            messages.append(GeminiMessage(
                role=role,
                content=content.strip(),
                timestamp=msg.get("timestamp", msg.get("createTime")),
            ))

    if not messages:
        return []

    first_user = next((m for m in messages if m.role == "user"), None)
    title = first_user.content[:80] + "…" if first_user and len(first_user.content) > 80 else (first_user.content if first_user else "Imported Chat")

    return [GeminiConversation(
        title=title,
        messages=messages,
        source="generic",
    )]


# ═════════════════════════════════════════════════════════════════════════════
#  Entity Extraction (lightweight NLP heuristics)
# ═════════════════════════════════════════════════════════════════════════════


# Technical terms / domain keywords that are valuable entities
_TECH_TERMS: set[str] = {
    # Programming languages
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
    "swift", "kotlin", "ruby", "php", "scala", "perl", "lua", "r",
    # Frameworks & libraries
    "react", "angular", "vue", "django", "flask", "fastapi", "spring",
    "tensorflow", "pytorch", "keras", "pandas", "numpy", "matplotlib",
    "node.js", "express", "next.js", "svelte", "tailwind",
    # Tools & platforms
    "docker", "kubernetes", "aws", "azure", "gcp", "git", "linux",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    # AI/ML concepts
    "machine learning", "deep learning", "neural network", "llm",
    "transformer", "gpt", "diffusion", "gan", "reinforcement learning",
    "natural language processing", "computer vision",
    # Cloud & DevOps
    "ci/cd", "terraform", "ansible", "jenkins", "github actions",
    "prometheus", "grafana", "datadog", "sentry",
}

# Common question words (triggers for ASKED_ABOUT relations)
_QUESTION_WORDS: set[str] = {
    "what", "how", "why", "when", "where", "which", "who", "can", "could",
    "would", "should", "is", "are", "do", "does", "did", "explain",
    "define", "describe", "tell", "show", "write", "create", "generate",
    "compare", "difference", "example", "tutorial", "guide",
}


def _extract_key_entities(text: str) -> set[str]:
    """Extract meaningful entity-like phrases from text.

    Uses lightweight heuristics:
    - Capitalised phrases (proper nouns)
    - Known technical terms (from _TECH_TERMS)
    - Noun phrases (2-4 word sequences of meaningful words)
    - Skip stop words, single chars, numbers-only
    """
    entities: set[str] = set()
    text_lower = text.lower().strip()

    # 1. Direct tech term matches (multi-word)
    for term in _TECH_TERMS:
        if term in text_lower:
            entities.add(term)

    # 2. Extract potential entities from text
    # Split into sentences and look for noun-like phrases
    sentences = re.split(r'[.!?]+', text)

    for sentence in sentences:
        words = sentence.strip().split()
        if len(words) < 2:
            continue

        # Look for capitalised phrases (potential named entities)
        caps_phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', sentence)
        for phrase in caps_phrases:
            phrase_lower = phrase.lower()
            words_in_phrase = phrase_lower.split()
            # Skip if all words are stop words
            if all(w in _STOP_WORDS for w in words_in_phrase):
                continue
            # Skip very short phrases
            if len(phrase) < 3:
                continue
            entities.add(phrase_lower[:60])

        # 3. Extract 2-3 word n-grams that aren't stop-word-only
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            bigram_clean = " ".join(
                w for w in bigram.split()
                if w.lower() not in _STOP_WORDS
            )
            if bigram_clean and len(bigram_clean) > 3:
                entities.add(bigram_clean.lower()[:60])

        if i < len(words) - 2:
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            trigram_clean = " ".join(
                w for w in trigram.split()
                if w.lower() not in _STOP_WORDS
            )
            if trigram_clean and len(trigram_clean) > 3 and len(trigram_clean.split()) >= 2:
                entities.add(trigram_clean.lower()[:60])

    return entities


def _is_question(text: str) -> bool:
    """Check if text is likely a question."""
    text_lower = text.strip().lower()
    if text_lower.endswith("?"):
        return True
    first_word = text_lower.split()[0] if text_lower.split() else ""
    return first_word in _QUESTION_WORDS


def _extract_entities_from_conversation(conv: GeminiConversation) -> list[tuple[str, str, str]]:
    """Extract knowledge triplets from a Gemini conversation.

    Strategy:
    1. The conversation title becomes a central entity
    2. Key entities from user messages become ASKED_ABOUT entities
    3. Key entities from model responses become EXPLAINED/BY associations
    4. Same-context co-occurrences become RELATED_TO
    """
    triplets: list[tuple[str, str, str]] = []

    # Normalise title as the conversation topic
    title_entity = conv.title.strip().lower()[:60]
    if not title_entity:
        return triplets

    # Collect all user entities and model entities separately
    user_entities: set[str] = set()
    model_entities: set[str] = set()

    # Track the last user question context
    last_user_text = ""

    for msg in conv.messages:
        entities = _extract_key_entities(msg.content)

        if msg.role == "user":
            user_entities.update(entities)
            last_user_text = msg.content
        elif msg.role == "model":
            model_entities.update(entities)
            # If there's a preceding user question, link it
            if last_user_text:
                last_user_entities = _extract_key_entities(last_user_text)
                for ue in last_user_entities:
                    for me in entities:
                        if ue != me:
                            triplets.append((ue, EXPLAINED, me))

    # Link user entities to the conversation title
    for ue in user_entities:
        if ue != title_entity:
            triplets.append((ue, ASKED_ABOUT, title_entity))
            triplets.append((ue, DISCUSSED_IN, title_entity))

    # Link model entities to the conversation title
    for me in model_entities:
        if me != title_entity:
            triplets.append((me, EXPLAINED, f"gemini {title_entity}" if title_entity else "gemini"))
            triplets.append((me, DISCUSSED_IN, title_entity))

    # Co-occurrence: entities in the same conversation are RELATED_TO each other
    all_entities = user_entities | model_entities
    entity_list = list(all_entities)
    # Limit to avoid combinatorial explosion: max 10 entities → ~45 pairs
    if len(entity_list) > 10:
        # Keep the most important ones (prefer tech terms and multi-word phrases)
        entity_list.sort(key=lambda e: (
            len(e.split()) > 1,  # multi-word first
            e in _TECH_TERMS,     # tech terms second
        ), reverse=True)
        entity_list = entity_list[:10]

    for i in range(len(entity_list)):
        for j in range(i + 1, len(entity_list)):
            if entity_list[i] != entity_list[j]:
                triplets.append((entity_list[i], RELATED_TO, entity_list[j]))

    return triplets


# ═════════════════════════════════════════════════════════════════════════════
#  Main Importer
# ═════════════════════════════════════════════════════════════════════════════


class GeminiChatImporter:
    """Import Google Gemini chat conversations into the ``gemini_chats`` brain.

    Usage::

        importer = GeminiChatImporter()
        result = importer.import_file("Takeout/Gemini/MyActivity.json")
        print(result.to_dict())

        # Or import all JSON files from a directory
        directory_result = importer.import_directory("Takeout/Gemini/")
    """

    def __init__(self) -> None:
        self._brain_type = BRAIN_TYPE
        self._ensure_brain_manager()

    @staticmethod
    def _ensure_brain_manager() -> None:
        """Ensure MultiBrainManager is available."""
        if not multi_brain_manager.is_valid_brain(BRAIN_TYPE):
            raise RuntimeError(
                f"Brain type '{BRAIN_TYPE}' is not registered. "
                "Check BRAIN_REGISTRY in multi_brain.py"
            )

    # ── Public API ──────────────────────────────────────────────────────

    def import_file(self, file_path: str | os.PathLike) -> ImportResult:
        """Import Gemini conversations from a single JSON file.

        Args:
            file_path: Path to a JSON file (Takeout, AI Studio, or generic).

        Returns:
            ``ImportResult`` with counts and any errors.
        """
        result = ImportResult(file_path=str(file_path))
        path = Path(file_path)

        if not path.exists():
            result.errors.append(f"File not found: {file_path}")
            result.file_format = "unknown"
            return result

        if path.suffix.lower() not in (".json", ".jsonl"):
            result.errors.append(f"Unsupported file type: {path.suffix}")
            result.file_format = "unknown"
            return result

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            result.errors.append(f"Failed to read/parse JSON: {exc}")
            return result

        # Detect format and parse
        fmt = _detect_format(data)
        result.file_format = fmt

        if fmt == "takeout":
            conversations = _parse_takeout_conversations(data)
        elif fmt == "ai_studio":
            conversations = _parse_ai_studio_conversations(data)
        else:
            conversations = _parse_generic_chat(data)

        result.conversations_found = len(conversations)

        if not conversations:
            result.errors.append(f"No valid conversations found in {path.name}")
            return result

        # Process each conversation
        for conv in conversations:
            triplets = _extract_entities_from_conversation(conv)
            if triplets:
                for subj, rel, obj in triplets:
                    multi_brain_manager.add_triplet(self._brain_type, subj, rel, obj)
                result.conversations_imported += 1
                result.triplets_added += len(triplets)

        # Persist the brain to disk after import
        if result.triplets_added > 0:
            try:
                multi_brain_manager.save_brain(self._brain_type)
            except Exception as exc:
                logger.warning("Failed to save brain after import: %s", exc)

        logger.info(
            "Gemini import: %s → %d/%d conversations, %d triplets",
            path.name,
            result.conversations_imported,
            result.conversations_found,
            result.triplets_added,
        )

        return result

    def import_text(self, json_text: str, source_name: str = "direct_input") -> ImportResult:
        """Import Gemini conversations from a JSON string.

        Args:
            json_text: JSON string containing conversations.
            source_name: Label for the source (used in result logging).

        Returns:
            ``ImportResult`` with counts and any errors.
        """
        result = ImportResult(file_path=source_name)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            result.errors.append(f"Invalid JSON: {exc}")
            return result

        fmt = _detect_format(data)
        result.file_format = fmt

        if fmt == "takeout":
            conversations = _parse_takeout_conversations(data)
        elif fmt == "ai_studio":
            conversations = _parse_ai_studio_conversations(data)
        else:
            conversations = _parse_generic_chat(data)

        result.conversations_found = len(conversations)

        for conv in conversations:
            triplets = _extract_entities_from_conversation(conv)
            if triplets:
                for subj, rel, obj in triplets:
                    multi_brain_manager.add_triplet(self._brain_type, subj, rel, obj)
                result.conversations_imported += 1
                result.triplets_added += len(triplets)

        if result.triplets_added > 0:
            try:
                multi_brain_manager.save_brain(self._brain_type)
            except Exception as exc:
                logger.warning("Failed to save brain after import: %s", exc)

        return result

    def import_directory(self, directory_path: str | os.PathLike) -> list[ImportResult]:
        """Import all Gemini conversation JSON files from a directory.

        Scans for ``*.json`` and ``*.jsonl`` files recursively.

        Args:
            directory_path: Path to a directory containing Gemini export files.

        Returns:
            List of ``ImportResult``, one per file.
        """
        base = Path(directory_path)
        if not base.exists() or not base.is_dir():
            return [ImportResult(
                file_path=str(directory_path),
                file_format="unknown",
                errors=[f"Directory not found: {directory_path}"],
            )]

        results: list[ImportResult] = []
        for f in sorted(base.rglob("*")):
            if f.suffix.lower() in (".json", ".jsonl") and f.is_file():
                result = self.import_file(f)
                results.append(result)
                if result.errors:
                    logger.warning("Import errors for %s: %s", f.name, result.errors)

        total_triplets = sum(r.triplets_added for r in results)
        total_convs = sum(r.conversations_imported for r in results)
        logger.info(
            "Directory import complete: %d files, %d conversations, %d triplets",
            len(results), total_convs, total_triplets,
        )

        return results

    def get_brain_stats(self) -> dict[str, Any]:
        """Return current statistics for the ``gemini_chats`` brain."""
        try:
            return multi_brain_manager.get_statistics(BRAIN_TYPE)
        except KeyError:
            return {"brain_type": BRAIN_TYPE, "error": "Brain not found"}

    @staticmethod
    def list_formats() -> list[dict[str, str]]:
        """Return supported import formats with descriptions."""
        return [
            {
                "id": "takeout",
                "name": "Google Takeout",
                "description": "Google Takeout Gemini export (MyActivity.json with conversations array)",
                "file_types": [".json"],
            },
            {
                "id": "ai_studio",
                "name": "Google AI Studio",
                "description": "Google AI Studio export (contents array with role/parts)",
                "file_types": [".json"],
            },
            {
                "id": "generic",
                "name": "Generic Chat JSON",
                "description": "Any JSON array of {role, content} or {author, content} messages",
                "file_types": [".json", ".jsonl"],
            },
        ]


# ─── Module-level convenience function ──────────────────────────────────────

def get_gemini_importer() -> GeminiChatImporter:
    """Return a singleton ``GeminiChatImporter`` instance."""
    return GeminiChatImporter()


# ═════════════════════════════════════════════════════════════════════════════
#  CLI Entrypoint
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """CLI entrypoint for the Gemini Chat Importer.

    Usage::

        python -m knowledge.gemini_importer import Takeout/Gemini/MyActivity.json
        python -m knowledge.gemini_importer import-dir Takeout/
        python -m knowledge.gemini_importer status
        python -m knowledge.gemini_importer formats
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="BARQ Gemini Chat Importer — import Google Gemini conversations into the gemini_chats brain",
    )
    subparsers = parser.add_subparsers(dest="command")

    # import
    import_parser = subparsers.add_parser("import", help="Import a single JSON file")
    import_parser.add_argument("file", type=str, help="Path to Gemini export JSON file")

    # import-dir
    dir_parser = subparsers.add_parser("import-dir", help="Import all JSON files from a directory")
    dir_parser.add_argument("directory", type=str, help="Path to directory with Gemini export files")

    # status
    subparsers.add_parser("status", help="Show gemini_chats brain stats")

    # formats
    subparsers.add_parser("formats", help="List supported import formats")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    importer = get_gemini_importer()

    if args.command == "import":
        result = importer.import_file(args.file)
        print(f"File:             {result.file_path}")
        print(f"Format:           {result.file_format}")
        print(f"Conversations:    {result.conversations_imported}/{result.conversations_found}")
        print(f"Triplets added:   {result.triplets_added}")
        if result.errors:
            print("Errors:")
            for err in result.errors:
                print(f"  ⚠ {err}")

    elif args.command == "import-dir":
        results = importer.import_directory(args.directory)
        total_triplets = sum(r.triplets_added for r in results)
        total_convs = sum(r.conversations_imported for r in results)
        print(f"Files processed:  {len(results)}")
        print(f"Conversations:    {total_convs}")
        print(f"Triplets added:   {total_triplets}")
        errors = [r for r in results if r.errors]
        if errors:
            print(f"Files with errors: {len(errors)}")

    elif args.command == "status":
        stats = importer.get_brain_stats()
        print(f"Brain type:   {stats.get('brain_type', 'N/A')}")
        print(f"Nodes:        {stats.get('nodes', 0)}")
        print(f"Edges:        {stats.get('edges', 0)}")
        print(f"Density:      {stats.get('density', 0)}")
        print(f"Components:   {stats.get('connected_components', 0)}")
        top = stats.get("top_entities", [])
        if top:
            print("Top entities:")
            for e in top:
                print(f"  • {e.get('entity', '?')} (centrality: {e.get('centrality', 0):.4f})")

    elif args.command == "formats":
        for fmt in importer.list_formats():
            print(f"{fmt['id']:15s}  {fmt['name']}")
            print(f"{'':15s}  {fmt['description']}")
            print(f"{'':15s}  Files: {', '.join(fmt['file_types'])}")
            print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
