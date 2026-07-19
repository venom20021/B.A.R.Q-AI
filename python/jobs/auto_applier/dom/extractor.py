"""
Hybrid Zero-Selector DOM Extractor.

Extracts interactive page elements using TWO strategies:
  A. Accessibility tree (Playwright snapshot) — clean, WCAG-structured
  B. Filtered interactive-tag DOM — button, input, select, textarea, a[href]

Strategy C (Hybrid): use A primarily, fall back to B when tree is sparse.
"""

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger("barq.auto_applier.dom")


class DOMExtractor:
    """Extracts cleaned interactive elements from a Playwright page."""

    # Interactive tags that matter for form filling
    INTERACTIVE_TAGS = {"button", "input", "select", "textarea", "a"}
    # Input types that are actionable
    INPUT_TYPES = {"text", "email", "tel", "url", "number", "password",
                   "file", "checkbox", "radio", "submit", "button", "search"}
    # Roles from accessibility tree that indicate form controls
    FORM_ROLES = {"button", "textbox", "combobox", "listbox", "radio",
                  "checkbox", "slider", "spinbutton", "searchbox",
                  "menuitem", "menuitemcheckbox", "switch", "tab", "treeitem"}

    def __init__(self, page: Any):
        self.page = page

    # ── Public API ──────────────────────────────────────────────────────

    async def extract(self, detect_form: bool = True) -> dict[str, Any]:
        """Run hybrid extraction and return a unified interaction map.

        Args:
            detect_form: If True, also detect form boundaries (fieldsets, forms).

        Returns:
            dict with keys:
              - elements: list of {id, tag, type, role, label, value, rect, ...}
              - form_count: number of forms detected
              - method: which extraction method was used ("accessibility" | "dom" | "hybrid")
              - raw: optional raw snapshot for LLM context
        """
        # Strategy A: Try accessibility tree first
        a11y_result = await self._extract_accessibility()

        # Strategy B: Interactive-tag filtered DOM (always run as fallback)
        dom_result = await self._extract_dom_filtered()

        # Strategy C: Hybrid — prefer a11y, supplement with DOM
        if len(a11y_result["elements"]) >= 3:
            elements = self._merge_elements(a11y_result["elements"], dom_result["elements"])
            method = "hybrid"
            logger.info("Hybrid extraction: %d elements (a11y=%d, dom=%d)",
                         len(elements), len(a11y_result["elements"]), len(dom_result["elements"]))
        elif len(dom_result["elements"]) > 0:
            elements = dom_result["elements"]
            method = "dom_fallback"
            logger.info("DOM fallback extraction: %d elements", len(elements))
        else:
            elements = []
            method = "empty"
            logger.warning("No interactive elements found on page")

        return {
            "elements": elements,
            "form_count": max(a11y_result.get("form_count", 0),
                              dom_result.get("form_count", 0)),
            "method": method,
            "raw_a11y": a11y_result.get("raw"),
            "raw_dom": dom_result.get("raw"),
        }

    async def extract_form_context(self, max_chars: int = 4000) -> str:
        """Return a cleaned text description of all form fields for LLM consumption.

        This is the primary input for the zero-selector AI discovery layer.
        The LLM receives this text + the question to decide which element to act on.
        """
        extraction = await self.extract(detect_form=True)
        lines = [f"Form has {extraction['form_count']} form(s) and {len(extraction['elements'])} interactive elements.\n"]

        for el in extraction["elements"]:
            label = el.get("label") or el.get("placeholder") or el.get("aria_label") or el.get("text", "")
            tag = el.get("tag", "?")
            etype = el.get("type", "")
            role = el.get("role", "")
            value = el.get("value", "")
            required = el.get("required", False)
            disabled = el.get("disabled", False)

            if disabled:
                continue

            parts = [f"[{tag}"]
            if etype:
                parts.append(f"type={etype}")
            if role and role != tag:
                parts.append(f"role={role}")
            parts.append(f"label=\"{label[:80]}\"")
            if value:
                parts.append(f"value=\"{value[:60]}\"")
            if required:
                parts.append("required")
            el_id = el.get("id", "?")[:20]
            parts.append(f"id={el_id}]")
            lines.append("  " + " ".join(parts))

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n... (truncated)"
        return result

    # ── Strategy A: Accessibility Tree ──────────────────────────────────

    async def _extract_accessibility(self) -> dict[str, Any]:
        """Use Playwright's accessibility snapshot to find interactive nodes."""
        elements = []
        form_count = 0

        try:
            snapshot = await self.page.accessibility.snapshot()
            if not snapshot:
                return {"elements": [], "form_count": 0, "raw": None}

            self._walk_a11y_tree(snapshot, elements)
            form_count = sum(1 for e in elements if e.get("role") == "form")

            logger.debug("Accessibility tree: %d nodes, %d elements",
                         self._count_nodes(snapshot), len(elements))
            return {
                "elements": elements,
                "form_count": form_count,
                "raw": json.dumps(snapshot, indent=2)[:3000],
            }
        except Exception as exc:
            logger.warning("Accessibility snapshot failed: %s", exc)
            return {"elements": [], "form_count": 0, "raw": None}

    def _walk_a11y_tree(self, node: dict, elements: list[dict], depth: int = 0) -> None:
        """Recursively walk the accessibility tree collecting interactive nodes."""
        if depth > 20:
            return

        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")
        checked = node.get("checked")
        disabled = node.get("disabled", False)

        # Collect interactive form controls
        if role in self.FORM_ROLES and not disabled:
            el = {
                "id": node.get("id", f"a11y-{len(elements)}"),
                "tag": self._role_to_tag(role),
                "type": self._role_to_input_type(role),
                "role": role,
                "label": name,
                "value": str(value) if value else "",
                "required": node.get("required", False),
                "checked": checked,
                "disabled": disabled,
                "level": node.get("level"),
                "rect": node.get("rect"),
                "source": "accessibility",
            }
            elements.append(el)

        # Recurse into children
        for child in node.get("children", []):
            if isinstance(child, dict):
                self._walk_a11y_tree(child, elements, depth + 1)

    @staticmethod
    def _role_to_tag(role: str) -> str:
        mapping = {
            "button": "button",
            "textbox": "input",
            "combobox": "select",
            "listbox": "select",
            "checkbox": "input",
            "radio": "input",
            "searchbox": "input",
            "slider": "input",
            "spinbutton": "input",
            "switch": "button",
        }
        return mapping.get(role, role)

    @staticmethod
    def _role_to_input_type(role: str) -> str:
        mapping = {
            "textbox": "text",
            "searchbox": "search",
            "checkbox": "checkbox",
            "radio": "radio",
            "slider": "range",
            "spinbutton": "number",
            "combobox": "select",
            "button": "button",
        }
        return mapping.get(role, "")

    @staticmethod
    def _count_nodes(node: dict) -> int:
        count = 1
        for child in node.get("children", []):
            if isinstance(child, dict):
                count += DOMExtractor._count_nodes(child)
        return count

    # ── Strategy B: Filtered DOM ────────────────────────────────────────

    async def _extract_dom_filtered(self) -> dict[str, Any]:
        """Query the DOM for interactive elements with text/labels/attributes."""
        elements = []

        try:
            raw = await self.page.evaluate("""
                () => {
                    const results = [];
                    const seen = new Set();
                    const tags = ['button', 'input', 'select', 'textarea', 'a'];

                    tags.forEach(tag => {
                        document.querySelectorAll(tag).forEach(el => {
                            // Skip hidden / disabled
                            if (el.disabled || el.type === 'hidden') return;
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) return;

                            const id = el.id || el.name || `${tag}-${results.length}`;
                            if (seen.has(id)) return;
                            seen.add(id);

                            // Gather text labels from various sources
                            const labelEl = el.labels?.[0];
                            const ariaLabel = el.getAttribute('aria-label');
                            const placeholder = el.getAttribute('placeholder');
                            const label = labelEl?.textContent?.trim()
                                          || ariaLabel
                                          || placeholder
                                          || el.textContent?.trim()
                                          || '';

                            results.push({
                                id: id,
                                tag: tag,
                                type: el.type || '',
                                name: el.name || '',
                                label: label.slice(0, 120),
                                value: (el.value || '').slice(0, 100),
                                placeholder: (placeholder || '').slice(0, 80),
                                aria_label: (ariaLabel || '').slice(0, 80),
                                required: el.required || false,
                                disabled: el.disabled || false,
                                checked: el.checked || false,
                                class: (el.className || '').slice(0, 60),
                                href: (el.href || '').slice(0, 200),
                                rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                                source: 'dom',
                            });
                        });
                    });
                    return results;
                }
            """)

            elements = raw if isinstance(raw, list) else []
            logger.debug("Filtered DOM: %d interactive elements", len(elements))
            return {
                "elements": elements,
                "form_count": await self._count_forms(),
                "raw": json.dumps(elements, indent=2)[:5000],
            }
        except Exception as exc:
            logger.warning("DOM extraction failed: %s", exc)
            return {"elements": [], "form_count": 0, "raw": None}

    async def _count_forms(self) -> int:
        try:
            return await self.page.evaluate("document.forms.length")
        except Exception:
            return 0

    # ── Merge helpers ───────────────────────────────────────────────────

    def _merge_elements(self, a11y_els: list[dict], dom_els: list[dict]) -> list[dict]:
        """Deduplicate and merge a11y and DOM elements, preferring a11y metadata."""
        seen_labels = set()
        merged = []

        for el in a11y_els:
            label = (el.get("label") or el.get("id", "")).lower().strip()
            if label and label not in seen_labels:
                seen_labels.add(label)
                merged.append(el)

        # Add DOM-only elements not already captured
        for el in dom_els:
            label = (el.get("label") or el.get("id", "")).lower().strip()
            if label and label not in seen_labels:
                seen_labels.add(label)
                el["source"] = "dom_only"
                merged.append(el)

        return merged
