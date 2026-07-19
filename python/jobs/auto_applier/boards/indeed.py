"""
Indeed Job Application Strategy.

Handles Indeed-specific flows:
  1. Navigate to job page
  2. Click Apply button (detected by AI)
  3. Handle Indeed's multi-page application forms
  4. Resume upload if required
"""

import logging
from typing import Any

from ..applier.form_filler import FormFiller
from ..browser.stealth import StealthConfig
from ..dom.extractor import DOMExtractor
from .base import JobBoardStrategy

logger = logging.getLogger("barq.auto_applier.indeed")


class IndeedStrategy(JobBoardStrategy):
    """Indeed job application strategy."""

    async def prepare(self, page: Any, job_url: str) -> dict[str, Any]:
        """Indeed doesn't require login for most applications."""
        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            await StealthConfig.human_delay(page, 2000, 3000)
            return {"success": True}
        except Exception as exc:
            logger.error("Indeed prepare failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def apply(
        self,
        page: Any,
        job_url: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Indeed application flow."""
        result = {"submitted": False, "errors": [], "pages_completed": 0}
        try:
            # Let AI find and click the Apply button
            extractor = DOMExtractor(page)
            form_context = await extractor.extract_form_context()
            apply_btn = await context["selector"].find_matching_button(
                form_context, ["apply now", "apply on indeed", "start your application"],
            )
            if apply_btn and apply_btn.get("element_id") != "unknown":
                btn_id = apply_btn["element_id"]
                btn_locator = page.locator(f"#{btn_id}")
                if await btn_locator.count() == 0:
                    btn_locator = page.get_by_role("button", name="Apply")
                await btn_locator.click()
                await StealthConfig.human_delay(page, 1500, 2500)

            # Fill form using AI-guided filler with resume upload support
            resume_uploader = context.get("resume_uploader")
            form_filler = FormFiller(page, self.ollama, resume_uploader=resume_uploader)
            fill_result = await form_filler.fill_application(
                job_context=context.get("job_context", ""),
            )
            result.update(fill_result)
        except Exception as exc:
            logger.error("Indeed apply error: %s", exc)
            result["errors"].append(str(exc))
        return result
