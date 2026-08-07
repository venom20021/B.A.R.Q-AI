"""
Glassdoor Job Application Strategy.

Handles Glassdoor-specific flows:
  1. Navigate to job page
  2. Click Apply button (detected by AI)
  3. Handle Glassdoor's redirect to the employer ATS / multi-page forms
  4. Resume upload if required
"""

import logging
from typing import Any

from ..applier.form_filler import FormFiller
from ..browser.stealth import StealthConfig
from ..dom.extractor import DOMExtractor
from .base import JobBoardStrategy

logger = logging.getLogger("barq.auto_applier.glassdoor")


class GlassdoorStrategy(JobBoardStrategy):
    """Glassdoor job application strategy."""

    async def prepare(self, page: Any, job_url: str) -> dict[str, Any]:
        """Glassdoor doesn't require login for most applications."""
        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            await StealthConfig.human_delay(page, 2000, 3000)
            return {"success": True}
        except Exception as exc:
            logger.error("Glassdoor prepare failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def apply(
        self,
        page: Any,
        job_url: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Glassdoor application flow."""
        result = {"submitted": False, "errors": [], "pages_completed": 0}
        try:
            # Let AI find and click the Apply button
            extractor = DOMExtractor(page)
            form_context = await extractor.extract_form_context()
            apply_btn = await context["selector"].find_matching_button(
                form_context, ["apply now", "apply on glassdoor", "apply"],
            )
            if apply_btn and apply_btn.get("element_id") != "unknown":
                btn_id = apply_btn["element_id"]
                btn_locator = page.locator(f"#{btn_id}")
                if await btn_locator.count() == 0:
                    btn_locator = page.get_by_role("button", name="Apply")
                await btn_locator.click()
                await StealthConfig.human_delay(page, 1500, 2500)

            # Glassdoor often redirects to the employer's external ATS.
            # If we landed on a different domain, the AI form filler still
            # handles it generically — fill + submit via the guided loop.
            resume_uploader = context.get("resume_uploader")
            form_filler = FormFiller(page, self.ollama, resume_uploader=resume_uploader)
            fill_result = await form_filler.fill_application(
                job_context=context.get("job_context", ""),
            )
            result.update(fill_result)
        except Exception as exc:
            logger.error("Glassdoor apply error: %s", exc)
            result["errors"].append(str(exc))
        return result
