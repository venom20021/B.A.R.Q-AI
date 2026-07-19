"""
LinkedIn Easy Apply Strategy.

Handles LinkedIn-specific flows:
  1. Ensure logged in (via storage state or .env credentials)
  2. Navigate to job page
  3. Click Easy Apply button
  4. Fill multi-page form using the AI-guided FormFiller
  5. Handle review/submit page
"""

import asyncio
import logging
from typing import Any

from ..applier.form_filler import FormFiller
from ..browser.stealth import StealthConfig
from ..config import CONFIG
from ..dom.extractor import DOMExtractor
from .base import JobBoardStrategy

logger = logging.getLogger("barq.auto_applier.linkedin")


class LinkedInStrategy(JobBoardStrategy):
    """LinkedIn job application strategy."""

    async def prepare(self, page: Any, job_url: str) -> dict[str, Any]:
        """Ensure logged into LinkedIn before applying."""
        try:
            # Navigate to LinkedIn to check login state
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
            await StealthConfig.human_delay(page, 1000, 2000)

            # Check if we're logged in by looking for the feed URL or user avatar
            current_url = page.url
            if "login" in current_url or "checkpoint" in current_url:
                logger.info("LinkedIn session expired — attempting re-login")
                success = await self._login(page)
                if not success:
                    return {"success": False, "error": "LinkedIn login failed"}
            else:
                logger.info("LinkedIn session is active")

            return {"success": True}

        except Exception as exc:
            logger.error("LinkedIn prepare failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def apply(
        self,
        page: Any,
        job_url: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute LinkedIn Easy Apply flow."""
        result = {"submitted": False, "errors": [], "pages_completed": 0}

        try:
            # Navigate to the job page
            await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            await StealthConfig.human_delay(page, 2000, 3000)

            # Click Easy Apply button (detected by AI)
            extractor = DOMExtractor(page)
            form_context = await extractor.extract_form_context()

            # Find Easy Apply button
            easy_apply_btn = await context["selector"].find_matching_button(
                form_context,
                ["easy apply", "apply", "apply now"],
            )

            if not easy_apply_btn or easy_apply_btn.get("element_id") == "unknown":
                # Check if it's an external apply
                external_btn = await context["selector"].find_matching_button(
                    form_context,
                    ["apply externally", "apply on company site"],
                )
                if external_btn and external_btn.get("element_id") != "unknown":
                    # External apply — open in new tab and use generic AI filler
                    result["external_apply"] = True
                    logger.info("External apply detected — will open in new tab")
                    return result
                else:
                    result["errors"].append("Could not find Apply button")
                    return result

            # Click the Easy Apply button
            btn_id = easy_apply_btn["element_id"]
            btn_locator = page.locator(f"#{btn_id}")
            if await btn_locator.count() == 0:
                btn_locator = page.get_by_role("button", name="Easy Apply")
            await btn_locator.click()
            await StealthConfig.human_delay(page, 1500, 2500)

            # Fill the multi-page form using the AI FormFiller
            resume_uploader = context.get("resume_uploader")
            form_filler = FormFiller(page, self.ollama, resume_uploader=resume_uploader)
            fill_result = await form_filler.fill_application(
                job_context=context.get("job_context", ""),
            )

            result.update(fill_result)
            logger.info("LinkedIn apply result: submitted=%s, pages=%d",
                        fill_result.get("submitted"), fill_result.get("pages_completed"))

        except Exception as exc:
            error_msg = f"LinkedIn apply error: {exc}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        return result

    async def _login(self, page: Any) -> bool:
        """Log into LinkedIn using credentials from .env."""
        if not CONFIG.linkedin_email or not CONFIG.linkedin_password:
            logger.warning("LinkedIn credentials not configured in .env")
            return False

        try:
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            await StealthConfig.human_delay(page, 1000, 2000)

            # Fill email
            email_input = page.locator("#username")
            await email_input.wait_for(state="visible", timeout=10000)
            await email_input.fill(CONFIG.linkedin_email)
            await StealthConfig.human_delay(page, 500, 1000)

            # Fill password
            password_input = page.locator("#password")
            await password_input.fill(CONFIG.linkedin_password)
            await StealthConfig.human_delay(page, 500, 1000)

            # Click sign in
            signin_btn = page.locator("button[type='submit']")
            await signin_btn.click()

            # Wait for redirect to feed
            await page.wait_for_url("**/feed/**", timeout=30000)
            logger.info("LinkedIn login successful")

            # Save session state
            from ..browser.launcher import BrowserLauncher
            # The launcher's session save is handled by the engine
            return True

        except Exception as exc:
            logger.error("LinkedIn login failed: %s", exc)
            return False
