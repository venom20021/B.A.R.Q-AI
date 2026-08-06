"""
BARQ Conversation Memory Agent (W5) — Orchestrator-Workers pattern.

After a chat/voice exchange, extracts durable knowledge and distributes it:

    transcript ──→ LLM extract (action items, facts, entities, summary)
                          ├──→ MemoryBus category 'action_items'
                          ├──→ MemoryBus category 'conversation'
                          ├──→ MemoryBus category 'relationships'
                          └──→ activity log + optional knowledge graph

Fire-and-forget safe: any failure is logged, never raised to the caller.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from utils.ollama_client import OllamaClient

EXTRACTION_SYSTEM_PROMPT = """You are BARQ's conversation memory extractor. Given a
conversation turn between the user and an AI assistant, extract durable,
worth-remembering information.

Output ONLY valid JSON with this exact schema:
{
  "action_items": [{"text": "what the user needs to do", "due": ""}],
  "facts": [{"key": "short_snake_case_key", "value": "concise fact", "category": "identity|preferences|projects|notes"}],
  "entities": [{"name": "person/company/project name", "type": "person|company|project|tool", "note": "what BARQ learned"}],
  "summary": "one-sentence summary of this exchange"
}

Rules:
- ONLY extract information explicitly stated. Never invent facts.
- Skip trivial chit-chat (greetings, small talk) — return empty arrays.
- Facts are timeless preferences/identity/project info the user would want
  remembered across sessions. Action items are explicit tasks/requests.
- If nothing worth remembering, return {"action_items": [], "facts": [], "entities": [], "summary": ""}"""


def _parse_extraction(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


async def extract_from_turn(user_text: str, ai_text: str = "") -> dict[str, Any]:
    """Extract structured memories from a single conversation turn.

    Returns:
        dict with action_items, facts, entities, summary, stored counts.
    """
    if not user_text or len(user_text.strip()) < 3:
        return {"extracted": False, "reason": "empty turn"}

    turn = f"User: {user_text}"
    if ai_text:
        turn += f"\n\nAssistant: {ai_text}"

    try:
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": turn[:3000]},
        ]
        # Route through the AgentKernel so extraction is rate-limited and
        # shares the global LLM concurrency budget (never bypasses it).
        try:
            from agent.agent_kernel import get_agent_kernel
            response = await get_agent_kernel().chat(
                messages, agent_name="conversation_memory"
            )
        except Exception as kernel_err:
            print(f"[ConversationMemory] Kernel unavailable ({kernel_err}) — direct fallback")
            llm = OllamaClient(temperature=0.2)
            response = await llm.chat(messages)
        data = _parse_extraction(response)
    except Exception as e:
        print(f"[ConversationMemory] Extraction failed: {e}")
        return {"extracted": False, "reason": str(e)}

    action_items = data.get("action_items", []) or []
    facts = data.get("facts", []) or []
    entities = data.get("entities", []) or []
    summary = str(data.get("summary", "") or "")

    stored = {"action_items": 0, "facts": 0, "entities": 0}
    try:
        from memory.memory_bus import get_memory_bus
        bus = get_memory_bus()

        for item in action_items[:5]:
            text = item.get("text", "")
            if text:
                due = item.get("due", "")
                value = f"{text}" + (f" (due: {due})" if due else "")
                stable_key = re.sub(r"\W+", "_", text.lower())[:50] or "action"
                await bus.store(
                    f"action_{stable_key}",
                    value, category="action_items", source="conversation",
                    ttl_seconds=14 * 24 * 3600,
                )
                stored["action_items"] += 1

        for fact in facts[:8]:
            key = fact.get("key", "")
            value = fact.get("value", "")
            category = fact.get("category", "notes")
            if key and value:
                await bus.store(
                    key, value, category=category, source="conversation",
                )
                stored["facts"] += 1

        for entity in entities[:8]:
            name = entity.get("name", "")
            etype = entity.get("type", "person")
            note = entity.get("note", "")
            if name:
                await bus.store(
                    f"entity_{name.lower().replace(' ', '_')[:40]}",
                    f"{etype}: {name}" + (f" — {note}" if note else ""),
                    category="relationships", source="conversation",
                    ttl_seconds=90 * 24 * 3600,
                )
                stored["entities"] += 1
    except Exception as e:
        print(f"[ConversationMemory] Memory store failed: {e}")

    # Persist the session summary for morning recall (existing session-memory flow)
    if summary:
        try:
            from memory.agent_memory_manager import save_session_summary
            save_session_summary(summary[:280])
        except Exception as e:
            print(f"[ConversationMemory] Session summary save failed: {e}")

    total = sum(stored.values())
    print(f"[ConversationMemory] Stored {total} item(s) from turn: {stored}")

    if total == 0 and not summary:
        return {"extracted": False, "reason": "nothing worth remembering"}

    return {
        "extracted": True,
        "action_items": action_items[:5],
        "facts": facts[:8],
        "entities": entities[:8],
        "summary": summary,
        "stored": stored,
        "total_stored": total,
    }


async def process_conversation_turn(user_text: str, ai_text: str = "") -> dict[str, Any]:
    """Public entry point (also used by the /agent/memory/conversation route)."""
    return await extract_from_turn(user_text, ai_text)


async def conversation_memory_skill(**kwargs: Any) -> str:
    """Skill handler for the planner/executor."""
    user_text = kwargs.get("user_text") or kwargs.get("message") or ""
    ai_text = kwargs.get("ai_text", "")
    result = await extract_from_turn(user_text, ai_text)
    if not result.get("extracted"):
        return "Nothing worth remembering in that exchange."
    stored = result.get("stored", {})
    return (
        f"Saved conversation memory: {result.get('total_stored', 0)} item(s) "
        f"(actions: {stored.get('action_items', 0)}, facts: {stored.get('facts', 0)}, "
        f"entities: {stored.get('entities', 0)})."
    )
