"""
End-to-end Auto-Apply Pipeline Orchestrator.

Connects: Job Discovery → LLM Scoring → Telegram Dispatch →
Interactive Buttons → Headful Auto-Apply → EvoMap Logging
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from ..applier.engine import ApplicationEngine
from ..boards.linkedin import LinkedInStrategy
from ..config import CONFIG, PROFILE
from ..failure.evo_logger import EvoLogger
from ..resume.dynamic_builder import DynamicResumeBuilder
from ..telegram.bot import AutoApplyBot

logger = logging.getLogger("barq.auto_applier.pipeline")


class AutoApplyPipeline:
    """End-to-end pipeline orchestrator."""

    def __init__(self):
        self.engine = ApplicationEngine()
        self.telegram = AutoApplyBot()
        self.evo = EvoLogger()
        self.resume_builder = DynamicResumeBuilder()

        # Register built-in strategies
        self.engine.register_strategy("linkedin.com", LinkedInStrategy)

        # Wire Telegram callbacks
        self.telegram.on_apply = self._on_telegram_apply
        self.telegram.on_skip = self._on_telegram_skip
        self.telegram.on_scan = self._on_telegram_scan

        # Pipeline state
        self._jobs: list[dict[str, Any]] = []
        self._running = False
        self._progress_callback: Optional[Callable] = None

    # ── Public API ──────────────────────────────────────────────────────

    async def run(
        self,
        jobs: Optional[list[dict[str, Any]]] = None,
        send_digest: bool = True,
    ) -> dict[str, Any]:
        """Run the full auto-apply pipeline.

        Args:
            jobs: List of job dicts with keys: url, company, title, context, score
                  If None, uses previously discovered jobs or triggers a scan.
            send_digest: If True, sends morning dispatch to Telegram.

        Returns:
            Summary dict with processed count, submitted count, errors.
        """
        self._running = True
        start_time = datetime.now(timezone.utc)
        logger.info("=== Auto-Apply Pipeline Started ===")

        result: dict[str, Any] = {
            "started_at": start_time.isoformat(),
            "jobs_found": 0,
            "jobs_processed": 0,
            "jobs_submitted": 0,
            "jobs_failed": 0,
            "errors": [],
        }

        try:
            # 1. Load or discover jobs
            if jobs:
                self._jobs = jobs
            else:
                self._jobs = await self._discover_jobs()

            result["jobs_found"] = len(self._jobs)

            if not self._jobs:
                logger.info("No jobs to process")
                await self.telegram.send_notification("✅ No new jobs found today.")
                return result

            # 2. Sort by match score descending
            self._jobs.sort(key=lambda j: j.get("score", 0), reverse=True)

            # 3. Send morning digest to Telegram
            if send_digest and self._jobs:
                top_jobs = self._jobs[:CONFIG.max_applications_per_run]
                await self.telegram.send_morning_digest(top_jobs)
                logger.info("Morning digest sent: %d jobs", len(top_jobs))

            # 4. Generate tailored resumes for each job
            if CONFIG.max_applications_per_run > 0:
                batch = self._jobs[:CONFIG.max_applications_per_run]
                batch = await self._generate_resumes_for_jobs(batch)

                # 5. Process jobs interactively (user clicks buttons in Telegram)
                #    or auto-process if max_applications_per_run > 0
                results = await self.engine.apply_batch(
                    jobs=batch,
                    progress_callback=self._progress_callback,
                )

                for r in results:
                    if r.get("submitted"):
                        result["jobs_submitted"] += 1
                        await self.evo.log_success(
                            url=r.get("job_url", ""),
                            context={"company": r.get("company"), "title": r.get("title")},
                        )
                    else:
                        result["jobs_failed"] += 1

                result["jobs_processed"] = len(results)

                # Send summary
                summary = (
                    f"📊 <b>Pipeline Complete</b>\n"
                    f"✅ Submitted: {result['jobs_submitted']}\n"
                    f"❌ Failed: {result['jobs_failed']}\n"
                    f"📋 Total processed: {result['jobs_processed']}"
                )
                await self.telegram.send_notification(summary)

        except Exception as exc:
            error_msg = f"Pipeline error: {exc}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            await self.telegram.send_notification(f"❌ Pipeline error: {exc}")

        finally:
            self._running = False
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            result["elapsed_seconds"] = round(elapsed, 1)
            logger.info("=== Pipeline finished in %.1fs ===", elapsed)

        return result

    async def start_telegram(self) -> None:
        """Start the Telegram bot (polling mode by default)."""
        await self.telegram.start_polling()

    def set_progress_callback(self, callback: Callable) -> None:
        """Set a progress callback for UI updates."""
        self._progress_callback = callback

    # ── Telegram Callbacks ──────────────────────────────────────────────

    async def _on_telegram_apply(self, job_ref: str) -> dict[str, Any]:
        """Handle [⚡ Apply Via Bot] button click or /apply command.

        Generates a tailored resume before applying to ensure the resume
        matches the job description.

        Args:
            job_ref: Job index (e.g. "3" or "all") or "all" for batch.

        Returns:
            Application result dict.
        """
        if job_ref == "all":
            batch = await self._generate_resumes_for_jobs(
                self._jobs[:CONFIG.max_applications_per_run]
            )
            return await self.engine.apply_batch(batch)

        try:
            idx = int(job_ref) - 1
            if idx < 0 or idx >= len(self._jobs):
                return {"error": f"Job #{job_ref} not found", "submitted": False}

            job = self._jobs[idx]

            # Generate a tailored resume for this specific job
            if progress_callback := self._progress_callback:
                await progress_callback("resume", f"Generating tailored resume for {job.get('title', '')[:40]}...")

            resume_result = await self.resume_builder.build(
                job_description=job.get("context", ""),
                job_title=job.get("title", ""),
                company=job.get("company", ""),
                timeout=60,
            )
            resume_path = resume_result.pdf_path if resume_result.status != "error" else None

            logger.info(
                "Resume built for %s @ %s: status=%s, path=%s",
                job.get("title"), job.get("company"),
                resume_result.status, resume_path or "default",
            )

            result = await self.engine.apply_to_job(
                job_url=job["url"],
                company=job.get("company", ""),
                title=job.get("title", ""),
                job_context=job.get("context", ""),
                resume_path=resume_path,
            )
            if result.get("submitted"):
                await self.evo.log_success(url=job["url"], context=job)
            else:
                await self.telegram.send_notification(
                    f"⚠️ Application incomplete for {job.get('title', '?')} @ {job.get('company', '?')}"
                )
            return result

        except (ValueError, IndexError) as exc:
            return {"error": f"Invalid job reference: {exc}", "submitted": False}

    async def _on_telegram_skip(self, job_ref: str) -> None:
        """Handle [❌ Skip Role] button click."""
        try:
            idx = int(job_ref) - 1
            if 0 <= idx < len(self._jobs):
                skipped = self._jobs.pop(idx)
                logger.info("Skipped job: %s @ %s", skipped.get("title"), skipped.get("company"))
        except (ValueError, IndexError):
            pass

    async def _on_telegram_scan(self) -> list[dict[str, Any]]:
        """Handle scan command."""
        self._jobs = await self._discover_jobs()
        return self._jobs

    # ── Resume Generation ────────────────────────────────────────────────

    async def _generate_resumes_for_jobs(
        self,
        jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate a tailored resume for each job in the batch.

        Iterates through the jobs list, generates a job-specific resume,
        and attaches the resume path to each job dict. Failed generations
        are logged but don't block the pipeline — the default resume is used.

        Args:
            jobs: List of job dicts with keys: url, company, title, context

        Returns:
            Updated job list with 'resume_path' key added to each.
        """
        if not jobs:
            return jobs

        logger.info("Generating tailored resumes for %d jobs...", len(jobs))

        for idx, job in enumerate(jobs):
            title = job.get("title", "")
            company = job.get("company", "")
            context = job.get("context", "")

            if self._progress_callback:
                await self._progress_callback(
                    "resume_generation",
                    f"Resume {idx + 1}/{len(jobs)}: {title[:40] if title else 'Unknown'} @ {company[:20] if company else 'Unknown'}",
                )

            try:
                resume_result = await self.resume_builder.build(
                    job_description=context,
                    job_title=title,
                    company=company,
                    timeout=60,
                )

                if resume_result.status != "error" and resume_result.pdf_path:
                    job["resume_path"] = resume_result.pdf_path
                    logger.info(
                        "Resume generated for %s @ %s: %s (source=%s, %d bytes)",
                        title, company,
                        resume_result.pdf_path,
                        resume_result.source,
                        resume_result.file_size_bytes,
                    )
                else:
                    logger.warning(
                        "Resume generation failed for %s @ %s: %s — will use default resume",
                        title, company,
                        resume_result.error,
                    )

            except Exception as exc:
                logger.error(
                    "Resume generation exception for %s @ %s: %s",
                    title, company, exc,
                )

            # Brief cooldown between resume generations to avoid
            # hammering Ollama or the AI_Resume_Generator server
            if idx < len(jobs) - 1:
                await asyncio.sleep(1)

        resumes_generated = sum(1 for j in jobs if j.get("resume_path"))
        logger.info("Resume generation complete: %d/%d generated", resumes_generated, len(jobs))
        return jobs

    # ── Job Discovery ───────────────────────────────────────────────────

    async def _discover_jobs(self) -> list[dict[str, Any]]:
        """Discover jobs from configured sources via the discovery aggregator."""
        from ..discovery.aggregator import JobAggregator
        return await JobAggregator().discover_all()
