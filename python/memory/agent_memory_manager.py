"""
BARQ Agent Memory Manager — structured long-term memory with auto-extraction.

Inspired by MARK XXXIX-OR's memory_manager.py, this module provides
categorized long-term memory that BARQ uses to remember user facts,
preferences, projects, relationships, and more across sessions.

Memory is stored in a JSON file and automatically trimmed to stay
within size limits.  An LLM-powered extraction function scans
conversations for memorable facts and saves them automatically.

Categories:
    - identity: name, age, birthday, city, job, nationality, language
    - preferences: favorite food/color/music/film/game/sport, hobbies
    - projects: active projects, goals, things being built
    - relationships: friends, family, partner, colleagues
    - wishes: future plans, things to buy, travel dreams
    - notes: habits, schedule, anything else worth remembering
"""

import json
import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

# ─── Configuration ───────────────────────────────────────────────────────────

MEMORY_DIR = Path(__file__).parent
MEMORY_PATH = MEMORY_DIR / "long_term.json"

_lock = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200


# ─── Memory Data ─────────────────────────────────────────────────────────────

def _empty_memory() -> dict:
    """Create an empty memory structure with all categories."""
    return {
        "identity": {},
        "preferences": {},
        "projects": {},
        "relationships": {},
        "wishes": {},
        "notes": {},
    }


def load_memory() -> dict:
    """Load the complete memory from disk.

    Returns:
        Dict with all memory categories.
        Returns an empty structure if no memory file exists.
    """
    if not MEMORY_PATH.exists():
        return _empty_memory()

    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[AgentMemory] WARN Load error: {e}")
            return _empty_memory()


def save_memory(memory: dict) -> None:
    """Save memory to disk, trimming if needed.

    Args:
        memory: The complete memory dict.
    """
    if not isinstance(memory, dict):
        return

    memory = _trim_to_limit(memory)

    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def update_memory(memory_update: dict) -> dict:
    """Merge a partial memory update into the stored memory.

    Args:
        memory_update: Dict with categories/keys to update.
            Example: ``{"identity": {"name": {"value": "John"}}}``

    Returns:
        The complete memory dict after the update.
    """
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[AgentMemory] SAVED: {list(memory_update.keys())}")
    return memory


def remember(key: str, value: str, category: str = "notes") -> str:
    """Quickly remember a single fact.

    Args:
        key: Short snake_case key (e.g. 'favorite_color').
        value: The value to remember.
        category: One of: identity, preferences, projects, relationships, wishes, notes.

    Returns:
        Confirmation message.
    """
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    """Forget a specific fact.

    Args:
        key: The key to forget.
        category: The category the key belongs to.

    Returns:
        Confirmation message.
    """
    memory = load_memory()
    cat = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


def format_memory_for_prompt(memory: Optional[dict] = None) -> str:
    """Format stored memory into a string that can be injected into LLM prompts.

    The formatted text tells the LLM what it knows about the user.

    Args:
        memory: Optional memory dict. Loads from disk if not provided.

    Returns:
        Formatted string with all memorable facts, or empty string if no memory.
    """
    if memory is None:
        memory = load_memory()

    if not memory:
        return ""

    lines = []

    # Identity (show inline without section header)
    identity = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  {field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"  {key.replace('_', ' ').title()}: {val}")

    # Preferences
    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("  Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"    - {key.replace('_', ' ').title()}: {val}")

    # Projects
    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("  Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"    - {key.replace('_', ' ').title()}: {val}")

    # Relationships
    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("  People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"    - {key.replace('_', ' ').title()}: {val}")

    # Wishes
    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("  Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"    - {key.replace('_', ' ').title()}: {val}")

    # Notes
    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("  Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"    - {key}: {val}")

    if not lines:
        return ""

    header = "[What I know about this person — use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"


# ─── Auto-Extraction from Conversations ─────────────────────────────────────

async def should_extract_memory_async(user_text: str, ai_text: str) -> bool:
    """Check if a conversation turn contains anything worth remembering.

    Uses the LLM (via Ollama) to make a quick YES/NO decision.

    Args:
        user_text: What the user said.
        ai_text: What BARQ responded.

    Returns:
        True if the conversation contains memorable information.
    """
    from utils.ollama_client import OllamaClient

    llm = OllamaClient()
    combined = f"User: {user_text[:300]}\nBARQ: {ai_text[:1000]}"

    try:
        messages = [
            {"role": "system", "content": "You are a memory relevance checker. Reply only YES or NO."},
            {"role": "user", "content": (
                f"Does this conversation contain ANY of the following?\n"
                f"- Personal facts (name, age, city, job, birthday, nationality)\n"
                f"- Preferences or favorites (food, color, music, sport, game, film, book)\n"
                f"- Active projects or goals the user is working on\n"
                f"- People in the user's life (friends, family, partner, colleagues)\n"
                f"- Things the user wants to do or buy in the future\n"
                f"- Any other fact worth remembering long-term\n\n"
                f"Reply only YES or NO.\n\nConversation:\n{combined}"
            )},
        ]
        result = await llm.chat(messages)
        return "YES" in result.upper()
    except Exception as e:
        print(f"[AgentMemory] WARN Memory relevance check failed: {e}")
        return False


async def extract_memory_async(user_text: str, ai_text: str) -> dict:
    """Extract memorable facts from a conversation turn.

    Uses the LLM to parse facts and return them in the structured memory format.

    Args:
        user_text: What the user said.
        ai_text: What BARQ responded.

    Returns:
        Dict with category -> key -> value mappings, or empty dict if nothing found.
    """
    from utils.ollama_client import OllamaClient

    llm = OllamaClient()
    combined = f"User: {user_text[:600]}\nBARQ: {ai_text[:300]}"

    prompt = (
        f"Extract ALL memorable personal facts from this conversation.\n"
        f"Return ONLY valid JSON. Use {{}} if nothing is worth saving.\n\n"
        f"Category guide:\n"
        f"  identity      → name, age, birthday, city, country, job, school, nationality, language\n"
        f"  preferences   → ANY favorite or preferred thing:\n"
        f"                  favorite_food, favorite_color, favorite_music, favorite_film,\n"
        f"                  favorite_game, favorite_sport, favorite_book, hobbies, etc.\n"
        f"  projects      → projects being built, ongoing work, goals, ideas in progress\n"
        f"  relationships → people mentioned: friends, family, partner, colleagues\n"
        f"  wishes        → future plans, things to buy, travel plans, dreams\n"
        f"  notes         → anything else worth remembering (habits, schedule, etc.)\n\n"
        f"IMPORTANT:\n"
        f"- Be LIBERAL: if something MIGHT be worth remembering, include it.\n"
        f"- Skip: weather, reminders, search results, one-time commands.\n"
        f"- Use concise English values regardless of conversation language.\n\n"
        f"Format:\n"
        f'{{"identity":{{"name":{{"value":"John"}}}},\n'
        f' "preferences":{{"favorite_color":{{"value":"blue"}}}}}}\n\n'
        f"Conversation:\n{combined}\n\nJSON:"
    )

    try:
        messages = [
            {"role": "system", "content": "Return ONLY valid JSON. No markdown, no explanation, no extra text."},
            {"role": "user", "content": prompt},
        ]
        raw = await llm.chat(messages)

        clean = raw.strip()
        clean = re.sub(r"```(?:json)?", "", clean).strip().rstrip("`").strip()

        if not clean or clean == "{}":
            return {}

        data = json.loads(clean)
        return data

    except (json.JSONDecodeError, Exception) as e:
        if "429" not in str(e):
            print(f"[AgentMemory] WARN Extract failed: {e}")
        return {}


# ─── Internal Helpers ───────────────────────────────────────────────────────

def _all_entries(memory: dict) -> list[tuple]:
    """Get all (category, key, entry) tuples from the memory."""
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    """Remove oldest entries if memory exceeds the character limit."""
    serialized = json.dumps(memory, ensure_ascii=False)
    if len(serialized) <= MEMORY_MAX_CHARS:
        return memory

    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))

    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[AgentMemory] TRIM {cat}/{key} (limit: {MEMORY_MAX_CHARS} chars)")

    return memory


def _truncate_value(val: str) -> str:
    """Truncate a value if it exceeds the maximum length."""
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    """Deep-merge updates into the target dict.

    Returns True if any changes were made.
    """
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue

        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            if isinstance(value, dict) and "value" in value:
                new_val = _truncate_value(str(value["value"]))
            else:
                new_val = _truncate_value(str(value))

            entry = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True

    return changed
