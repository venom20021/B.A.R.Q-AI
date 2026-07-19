"""
Main Application Engine.

Orchestrates the full lifecycle:
  Launch headful browser → Navigate to job URL → 
  Detect platform → Apply strategy → Fill forms → Submit → Log
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..browser.launcher import BrowserLauncher
from ..browser.stealth import StealthConfig
from ..boards.base import JobBoardStrategy
from ..boards.linkedin import LinkedInStrategy
from ..dom.extractor import DOMExtractor
from ..failure.evo_logger import EvoLogger
from ..llm.element_selector import ElementSelector
from ..llm.ollama_client import OllamaClient
from ..llm.qa_generator import QAGenerator
from .form_filler import FormFiller
from .resume_uploader import ResumeUploader
from ..config import PROFILE, CONFIG

logger = logging.getLogger("barq.auto_applier.engine")


class ApplicationEngine:
    """Orchestrates job application from URL to submission."""

    def __init__(self):
        self.browser: Optional[BrowserLauncher] = None
        self._ollama = OllamaClient()
        self._selector = ElementSelector(self._ollama)
        self._qa = QAGenerator(self._ollama)
        self._evo = EvoLogger()
        self._strategies: dict[str, type[JobBoardStrategy]] = {}

    def register_strategy(self, domain: str, strategy: type[JobBoardStrategy]) -> None:
        """Register a job board strategy for a given domain pattern."""
        self._strategies[domain.lower()] = strategy

    async def apply_to_job(
        self,
        job_url: str,
        company: str = "",
        title: str = "",
        job_context: str = "",
        resume_path: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> dict[str, Any]:
        """Apply to a single job URL end-to-end.

        Args:
            job_url: Full URL to the job posting/application.
            company: Company name for logging.
            title: Job title for logging.
            job_context: Job description text for context-aware answers.
            resume_path: Optional path to a tailored resume PDF. If None,
                         uses the default resume from CONFIG.resume_pdf_path.
            progress_callback: Optional async callback(stage, message).

        Returns:
            dict with status, errors, submitted, etc.
        """
        result = {
            "job_url": job_url,
            "company": company or "Unknown",
            "title": title or "Unknown",
            "status": "initializing",
            "submitted": False,
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # 1. Launch headful browser
            if progress_callback:
                await progress_callback("launching", "Launching browser...")

            self.browser = BrowserLauncher()
            page = await self.browser.launch()

            # 2. Set up tailored resume for upload if provided
            resume_uploader = ResumeUploader(page)
            if resume_path:
                resume_uploader.set_resume_path(resume_path)
                logger.info("Using tailored resume: %s", resume_path)
                result["resume_path"] = resume_path

            # 3. Navigate to job URL
            if progress_callback:
                await progress_callback("navigating", f"Navigating to {job_url[:80]}...")

            await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await StealthConfig.apply_to_page(page)
            await StealthConfig.human_delay(page, 1000, 2000)

            # 4. Detect platform and get strategy
            domain = self._extract_domain(job_url)
            strategy = self._get_strategy(domain)

            if strategy:
                logger.info("Using strategy '%s' for %s", strategy.__class__.__name__, domain)
                # Let the strategy handle platform-specific setup (login, navigation)
                result["strategy"] = strategy.__class__.__name__
                prep_result = await strategy.prepare(page, job_url)
                if not prep_result.get("success", False):
                    result["errors"].append(f"Strategy preparation failed: {prep_result.get('error', 'unknown')}")
                    result["status"] = "failed"
                    await self._close_browser()
                    return result

                # Delegate form filling to the strategy (which may use FormFiller)
                apply_result = await strategy.apply(page, job_url, {
                    "ollama": self._ollama,
                    "selector": self._selector,
                    "qa": self._qa,
                    "profile": PROFILE,
                    "job_context": job_context,
                    "resume_uploader": resume_uploader,
                })
                result.update(apply_result)
                result["submitted"] = apply_result.get("submitted", False)
            else:
                # No specific strategy — use generic AI-guided form filling
                logger.info("No specific strategy for '%s' — using AI-guided form filling", domain)
                result["strategy"] = "AI_Guided"
                form_filler = FormFiller(page, self._ollama, resume_uploader=resume_uploader)
                fill_result = await form_filler.fill_application(
                    job_context=job_context,
                    progress_callback=progress_callback,
                )
                result["submitted"] = fill_result.get("submitted", False)
                result["pages_completed"] = fill_result.get("pages_completed", 0)
                result["fields_filled"] = fill_result.get("fields_filled", 0)
                result["form_errors"] = fill_result.get("errors", [])

            # 4. Save session state after successful interactions
            await self.browser.save_session()

            result["status"] = "submitted" if result.get("submitted") else "incomplete"
            result["completed_at"] = datetime.now(timezone.utc).isoformat()

            logger.info("Application result for %s @ %s: %s (submitted=%s)",
                        result["title"], result["company"],
                        result["status"], result["submitted"])

        except Exception as exc:
            error_msg = f"Application engine error: {exc}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["status"] = "error"

            # EvoMap failure logging
            dom_snapshot = ""
            try:
                if self.browser and self.browser.page:
                    dom_snapshot = await self.browser.page.content()
            except Exception:
                pass

            await self._evo.log_failure(
                url=job_url,
                error_type=type(exc).__name__,
                error_message=str(exc),
                dom_snapshot=dom_snapshot[:3000],
                context={"company": company, "title": title},
            )
        finally:
            await self._close_browser()

        return result

    async def apply_batch(
        self,
        jobs: list[dict[str, Any]],
        progress_callback: Optional[Callable] = None,
    ) -> list[dict[str, Any]]:
        """Apply to multiple jobs sequentially.

        Args:
            jobs: List of dicts with keys: url, company, title, context
            progress_callback: Optional async callback

        Returns:
            List of result dicts for each job.
        """
        results = []
        for idx, job in enumerate(jobs):
            logger.info("=== Job %d/%d: %s @ %s ===",
                        idx + 1, len(jobs), job.get("title", "?"), job.get("company", "?"))
            if progress_callback:
                await progress_callback("batch_progress",
                    f"Job {idx + 1}/{len(jobs)}: {job.get('title', '')[:40]}")

            result = await self.apply_to_job(
                job_url=job["url"],
                company=job.get("company", ""),
                title=job.get("title", ""),
                job_context=job.get("context", ""),
                resume_path=job.get("resume_path"),
                progress_callback=progress_callback,
            )
            results.append(result)

            # Cooldown between applications
            if idx < len(jobs) - 1:
                delay = 5 + (idx % 3) * 2  # 5-11s randomized delay
                logger.info("Cooldown %ds before next application...", delay)
                await asyncio.sleep(delay)

        successes = sum(1 for r in results if r.get("submitted"))
        logger.info("Batch complete: %d/%d submitted", successes, len(jobs))
        return results

    # ── Internals ───────────────────────────────────────────────────────

    def _extract_domain(self, url: str) -> str:
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc.lower()
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return url

    def _get_strategy(self, domain: str) -> Optional[JobBoardStrategy]:
        """Find a matching strategy by domain pattern."""
        for pattern, strategy_cls in self._strategies.items():
            if pattern in domain:
                strategy = strategy_cls()
                strategy.ollama = self._ollama
                strategy.selector = self._selector
                strategy.qa = self._qa
                return strategy
        return None

    async def _close_browser(self) -> None:
        if self.browser:
            try:
                await self.browser.close()
            except Exception as exc:
                logger.warning("Browser close error: %s", exc)
            self.browser = None
