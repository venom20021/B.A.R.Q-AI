"""
Zero-Selector AI Element Selector.

Given a cleaned DOM context and a target action (e.g. "find the submit button"),
the LLM reasons about which interactive element matches the intent.
"""

import json
import logging
from typing import Any, Optional

from .ollama_client import OllamaClient, OllamaError
from ..config import PROFILE

logger = logging.getLogger("barq.auto_applier.selector")

# ─── Prompts ──────────────────────────────────────────────────────────────

ELEMENT_SELECT_SYSTEM = (
    "You are a DOM analysis AI. Given a description of interactive elements on a page "
    "and a user's requested action, you output a JSON object identifying the single "
    "best-matching element. Be precise: match by label text, placeholder, role, or tag."
)

ELEMENT_SELECT_PROMPT = """\
INTERACTIVE ELEMENTS ON PAGE:
{form_context}

REQUESTED ACTION: {action}

Which element should be interacted with? Consider:
- Labels, placeholders, aria-labels, and visible text
- The element's tag and type
- Whether it's required vs optional
- For buttons: match by visible text content

Output JSON:
{{
  "element_id": "id of the chosen element",
  "reason": "one sentence why this matches",
  "interaction": "click | type | select | upload",
  "value": "the value to type or select (if applicable, else null)"
}}
"""


class ElementSelector:
    """Uses Ollama to decide which DOM element to interact with."""

    def __init__(self, ollama: Optional[OllamaClient] = None):
        self.ollama = ollama or OllamaClient()

    async def select(
        self,
        action: str,
        form_context: str,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Ask LLM which element matches the requested action.

        Args:
            action: e.g. "find the submit button", "find the email input",
                    "find the 'Next' button"
            form_context: Output from DOMExtractor.extract_form_context()

        Returns:
            dict with keys: element_id, reason, interaction, value
        """
        prompt = ELEMENT_SELECT_PROMPT.format(
            form_context=form_context.strip()[:3000],
            action=action,
        )

        for attempt in range(1, max_retries + 1):
            try:
                result = await self.ollama.generate_json(
                    prompt=prompt,
                    system=ELEMENT_SELECT_SYSTEM,
                    temperature=0.1,
                )

                # Validate required keys
                if "element_id" not in result:
                    result["element_id"] = "unknown"
                if "interaction" not in result:
                    result["interaction"] = "click"
                if "reason" not in result:
                    result["reason"] = "matched by LLM analysis"

                return result

            except OllamaError as exc:
                logger.warning("Element select attempt %d/%d failed: %s",
                               attempt, max_retries, exc)
                if attempt == max_retries:
                    raise

        # Fallback for type safety
        return {"element_id": "unknown", "reason": "all attempts failed",
                "interaction": "click", "value": None}

    async def find_matching_button(
        self,
        form_context: str,
        button_texts: list[str],
    ) -> Optional[dict[str, Any]]:
        """Search for a button matching one of the given text labels."""
        action = f"find a button with text matching one of: {', '.join(button_texts)}"
        return await self.select(action, form_context)

    async def find_input_for_label(
        self,
        form_context: str,
        field_label: str,
    ) -> Optional[dict[str, Any]]:
        """Find an input field associated with the given label text."""
        action = f"find the input field for '{field_label}'"
        return await self.select(action, form_context)
