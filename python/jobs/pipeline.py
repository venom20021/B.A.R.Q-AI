"""
BARQ Job Application Pipeline — end-to-end pipeline orchestrator.

Connects: Scanner → Matcher → Resume Optimizer → Cover Letter Generator
→ PDF Generator → Application Documents → Auto-Apply OR Telegram Notification

The pipeline processes approved/queued applications by:
1. Parsing the user's resume
2. Optimizing it for each specific job description
3. Generating a tailored cover letter
4. Generating PDF documents
5. Either auto-applying via Playwright OR sending a Telegram notification
   with the job link, optimized resume, and cover letter summary
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("barq.pipeline")

from database import analytics_dao, db_connection, jobs_dao, settings_dao
from knowledge.auto_extractor import AutoExtractor
from notifications.manager import notification_manager

from .applier import JobApplier
from .cover_letter import CoverLetterGenerator
from .optimizer import ResumeOptimizer
from .pdf_generator import ResumePDFGenerator, GENERATED_DIR
from .resume_parser import DEFAULT_RESUME_PATH, parse_resume

# ─── Pipeline Settings ──────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "mode": "notify",           # "notify" → Telegram, "auto_apply" → Playwright submit
    "auto_apply": False,        # Whether to actually submit forms (requires Playwright)
    "max_per_run": 10,          # Max jobs to process per pipeline run
    "generate_pdf": True,       # Generate PDF copies of resume and cover letter
    "send_telegram": True,      # Send Telegram notification with job link + docs
    "min_match_score": 60,      # Minimum match percentage to process
}

# ─── Pipeline State ─────────────────────────────────────────────────────────

_pipeline_state: dict[str, Any] = {
    "status": "idle",           # idle | running | paused | complete | error
    "phase": "",
    "phase_index": 0,
    "total_phases": 6,
    "progress_pct": 0,
    "jobs_total": 0,
    "jobs_processed": 0,
    "jobs_succeeded": 0,
    "jobs_failed": 0,
    "current_job": "",
    "message": "",
    "started_at": None,
    "elapsed_seconds": 0,
    "results": [],
}

PHASES = [
    "Loading user resume",
    "Fetching approved jobs",
    "Optimizing resumes",
    "Generating cover letters",
    "Generating application documents",
    "Notifying & applying",
]


def get_pipeline_settings() -> dict[str, Any]:
    """Get current pipeline settings (cached in pipeline_state)."""
    return dict(DEFAULT_SETTINGS)


def get_pipeline_progress() -> dict[str, Any]:
    """Return a snapshot of pipeline progress."""
    p = _pipeline_state
    if p["started_at"]:
        p["elapsed_seconds"] = round(time.time() - p["started_at"], 1)
    return dict(p)


def reset_pipeline_state():
    """Reset pipeline state to idle."""
    for key in ("status", "phase", "current_job", "message"):
        _pipeline_state[key] = "" if key in ("phase", "current_job", "message") else "idle" if key == "status" else 0
    _pipeline_state["phase_index"] = 0
    _pipeline_state["progress_pct"] = 0
    _pipeline_state["jobs_total"] = 0
    _pipeline_state["jobs_processed"] = 0
    _pipeline_state["jobs_succeeded"] = 0
    _pipeline_state["jobs_failed"] = 0
    _pipeline_state["started_at"] = None
    _pipeline_state["elapsed_seconds"] = 0
    _pipeline_state["results"] = []


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline Runner
# ═══════════════════════════════════════════════════════════════════════════


async def run_pipeline(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Execute the full job application pipeline.

    Args:
        settings: Override DEFAULT_SETTINGS values

    Returns:
        Summary dict with status, processed count, and results
    """
    cfg = {**DEFAULT_SETTINGS, **(settings or {})}

    reset_pipeline_state()
    _pipeline_state["status"] = "running"
    _pipeline_state["started_at"] = time.time()
    results: list[dict[str, Any]] = []

    try:
        # ── Phase 1: Load Resume ──────────────────────────────────────
        _pipeline_state["phase"] = PHASES[0]
        _pipeline_state["phase_index"] = 0
        _pipeline_state["progress_pct"] = 5
        _pipeline_state["message"] = "Parsing user resume..."
        await asyncio.sleep(0.2)

        resume = parse_resume()
        if resume.get("_error") or not resume.get("raw_md"):
            _pipeline_state["status"] = "error"
            _pipeline_state["message"] = f"Resume not found. Expected at: {DEFAULT_RESUME_PATH}"
            return {"status": "error", "message": _pipeline_state["message"], "results": []}

        resume_md = resume["raw_md"]
        print(f"[Pipeline] Resume loaded: {resume.get('full_name', 'Unknown')} ({len(resume_md)} chars)")

        # ── Phase 2: Fetch Approved Jobs ──────────────────────────────
        _pipeline_state["phase"] = PHASES[1]
        _pipeline_state["phase_index"] = 1
        _pipeline_state["progress_pct"] = 10
        _pipeline_state["message"] = "Fetching approved jobs from database..."
        await asyncio.sleep(0.2)

        # Get jobs that are approved/queued AND have good match scores
        queued = await jobs_dao.get_applications_by_status("queued", limit=cfg["max_per_run"])
        approved = await jobs_dao.get_applications_by_status("approved", limit=cfg["max_per_run"])

        # Also get ready_for_review
        review = await jobs_dao.get_applications_by_status("ready_for_review", limit=cfg["max_per_run"])

        all_apps = queued + approved + review

        # Deduplicate by job_listing_id
        seen_ids = set()
        unique_apps = []
        for app in all_apps:
            jid = app["job_listing_id"]
            if jid not in seen_ids:
                seen_ids.add(jid)
                unique_apps.append(app)

        # Filter by match score threshold
        filtered_apps = []
        for app in unique_apps:
            # Get the job listing with its evaluation
            job = await jobs_dao.get_job_listing(app["job_listing_id"])
            if not job:
                continue
            eval_data = await jobs_dao.get_evaluation(app["job_listing_id"])
            match_pct = eval_data.get("match_percentage", 0) if eval_data else 0
            if match_pct >= cfg["min_match_score"] or match_pct == 0:
                # Include even unscored jobs for review
                app["job"] = job
                app["evaluation"] = eval_data or {}
                app["match_percentage"] = match_pct
                filtered_apps.append(app)

        if not filtered_apps:
            _pipeline_state["status"] = "complete"
            _pipeline_state["progress_pct"] = 100
            _pipeline_state["message"] = "No approved/queued jobs found to process"
            print("[Pipeline] No jobs to process")
            return {"status": "complete", "message": "No jobs to process", "results": []}

        _pipeline_state["jobs_total"] = len(filtered_apps)
        print(f"[Pipeline] Processing {len(filtered_apps)} jobs...")

        # Initialize generators
        optimizer = ResumeOptimizer()
        cover_gen = CoverLetterGenerator()
        pdf_gen = ResumePDFGenerator()
        applier = JobApplier()

        # ── Phases 3-6: Process Each Job ─────────────────────────────
        for idx, app in enumerate(filtered_apps):
            job = app["job"]
            job_id = job.get("id", 0)
            job_title = job.get("title", "Unknown")
            company = job.get("company", "Unknown")
            source_url = job.get("source_url", "")
            match_pct = app.get("match_percentage", 0)

            _pipeline_state["current_job"] = f"{job_title} at {company}"
            app_result = {
                "application_id": app.get("id", 0),
                "job_listing_id": job_id,
                "title": job_title,
                "company": company,
                "url": source_url,
                "match_percentage": match_pct,
                "status": "processing",
                "optimized_resume": "",
                "cover_letter": "",
                "pdf_paths": {},
                "telegram_sent": False,
                "auto_applied": False,
                "error": "",
            }

            try:
                # ── Phase 3: Optimize Resume ──────────────────────────
                pct_base = 15 + (idx / max(len(filtered_apps), 1)) * 60
                _pipeline_state["phase"] = PHASES[2]
                _pipeline_state["phase_index"] = 2
                _pipeline_state["progress_pct"] = round(pct_base, 1)
                _pipeline_state["message"] = f"Optimizing resume for {job_title} at {company}..."

                # Run optimizer to tailor resume for this specific JD
                match_analysis = {
                    "missing_skills": [],
                    "matching_skills": [],
                }
                if app.get("evaluation"):
                    eval_data = app["evaluation"]
                    try:
                        pros = json.loads(eval_data.get("pros", "[]")) if isinstance(eval_data.get("pros"), str) else eval_data.get("pros", [])
                        cons = json.loads(eval_data.get("cons", "[]")) if isinstance(eval_data.get("cons"), str) else eval_data.get("cons", [])
                        match_analysis = {
                            "matching_skills": pros[:5] if isinstance(pros, list) else [],
                            "missing_skills": cons[:5] if isinstance(cons, list) else [],
                        }
                    except (json.JSONDecodeError, TypeError):
                        pass

                optimized = await optimizer.optimize(resume_md, job, match_analysis)
                optimized_md = optimized.get("optimized_md", resume_md)
                app_result["optimized_resume"] = optimized_md
                app_result["keywords_injected"] = optimized.get("keywords_injected", [])

                # ── Phase 4: Generate Cover Letter ────────────────────
                _pipeline_state["phase"] = PHASES[3]
                _pipeline_state["phase_index"] = 3
                _pipeline_state["progress_pct"] = round(pct_base + 15, 1)
                _pipeline_state["message"] = f"Writing cover letter for {job_title}..."

                cover_letter = await cover_gen.generate(job, resume, optimized_md)
                app_result["cover_letter"] = cover_letter

                # ── Phase 5: Generate PDFs ────────────────────────────
                _pipeline_state["phase"] = PHASES[4]
                _pipeline_state["phase_index"] = 4
                _pipeline_state["progress_pct"] = round(pct_base + 30, 1)
                _pipeline_state["message"] = f"Generating documents for {job_title}..."

                pdf_paths = {}
                if cfg["generate_pdf"]:
                    # Create a job-specific resume data dict with optimized content
                    pdf_resume_data = {**resume, "raw_md": optimized_md}
                    job_slug = f"{company}_{job_title}".replace(" ", "_").replace("/", "_")[:50]

                    # Generate resume PDF
                    resume_pdf_result = await pdf_gen.generate(
                        pdf_resume_data,
                        output_dir=str(GENERATED_DIR / f"optimized_{job_slug}"),
                        filename=f"Resume_{job_slug}",
                    )
                    if resume_pdf_result.get("status") == "completed":
                        pdf_paths["resume"] = resume_pdf_result["pdf_path"]

                    # Generate cover letter as a simple text file (PDF via fpdf)
                    if cover_letter:
                        cl_dir = GENERATED_DIR / f"cover_letter_{job_slug}"
                        cl_dir.mkdir(parents=True, exist_ok=True)
                        cl_path = str(cl_dir / f"Cover_Letter_{job_slug}.txt")
                        with open(cl_path, "w", encoding="utf-8") as f:
                            f.write(cover_letter)
                        pdf_paths["cover_letter"] = cl_path

                app_result["pdf_paths"] = pdf_paths

                # Update the application status in DB
                await jobs_dao.update_application_status(
                    app["id"],
                    "generating",
                    notes=json.dumps({
                        "pipeline_processed_at": datetime.now(timezone.utc).isoformat(),
                        "optimized": True,
                        "cover_letter_generated": bool(cover_letter),
                        "pdf_generated": bool(pdf_paths),
                        "match_percentage": match_pct,
                    }),
                )

                # Store documents in DB
                if optimized_md and app["id"]:
                    await jobs_dao.insert_document({
                        "application_id": app["id"],
                        "document_type": "resume",
                        "content": optimized_md,
                        "file_path": pdf_paths.get("resume", ""),
                        "format": "markdown",
                        "generated_by": "llm",
                    })
                if cover_letter and app["id"]:
                    await jobs_dao.insert_document({
                        "application_id": app["id"],
                        "document_type": "cover_letter",
                        "content": cover_letter,
                        "file_path": pdf_paths.get("cover_letter", ""),
                        "format": "markdown",
                        "generated_by": "llm",
                    })

                # ── Phase 6: Notify & Apply ──────────────────────────
                _pipeline_state["phase"] = PHASES[5]
                _pipeline_state["phase_index"] = 5
                _pipeline_state["progress_pct"] = round(pct_base + 45, 1)
                _pipeline_state["message"] = f"Sending notification for {job_title}..."

                telegram_sent = False
                auto_applied = False

                if cfg["send_telegram"]:
                    telegram_sent = await _send_telegram_notification(
                        job_title=job_title,
                        company=company,
                        job_url=source_url,
                        match_pct=match_pct,
                        app_id=app["id"],
                        resume_snippet=optimized_md[:500] if optimized_md else "",
                        cover_letter_snippet=cover_letter[:300] if cover_letter else "",
                    )

                if cfg["auto_apply"] and source_url:
                    user_profile = {
                        "full_name": resume.get("full_name", ""),
                        "email": resume.get("email", ""),
                        "phone": resume.get("phone", ""),
                        "linkedin_url": resume.get("linkedin_url", ""),
                        "skills": resume.get("skills", []),
                    }
                    auto_apply_result = await applier.auto_fill_application(
                        source_url, user_profile, pdf_paths.get("resume")
                    )
                    auto_applied = auto_apply_result.get("status") == "completed"
                    app_result["auto_apply_result"] = auto_apply_result

                # Mark application as submitted or ready_for_review
                if auto_applied:
                    await jobs_dao.update_application_status(
                        app["id"], "submitted",
                        submitted_at=datetime.now(timezone.utc).isoformat(),
                    )
                elif telegram_sent:
                    await jobs_dao.update_application_status(
                        app["id"], "ready_for_review",
                    )
                else:
                    await jobs_dao.update_application_status(
                        app["id"], "ready_for_review",
                    )

                app_result["status"] = "completed"
                app_result["telegram_sent"] = telegram_sent
                app_result["auto_applied"] = auto_applied

                _pipeline_state["jobs_succeeded"] += 1
                results.append(app_result)

                # Log success
                # Auto-extract knowledge triplets from the job description
                try:
                    extractor = AutoExtractor()
                    await extractor.extract_from_job(
                        job_id=job_id,
                        title=job_title,
                        description=job.get("description", ""),
                        company=company,
                    )
                except Exception as exc:
                    logger.warning("[Extraction] Failed to extract from job %d: %s", job_id, exc)

                await analytics_dao.log_activity(
                    "job", "pipeline_processed",
                    f"Pipeline: {job_title} at {company} "
                    f"(match: {match_pct}%, telegram: {telegram_sent}, auto-apply: {auto_applied})",
                )

            except Exception as e:
                print(f"[Pipeline] Error processing {job_title} at {company}: {e}")
                app_result["status"] = "failed"
                app_result["error"] = str(e)
                _pipeline_state["jobs_failed"] += 1
                results.append(app_result)

            _pipeline_state["jobs_processed"] += 1

        # ── Complete ─────────────────────────────────────────────────
        _pipeline_state["status"] = "complete"
        _pipeline_state["progress_pct"] = 100
        _pipeline_state["message"] = (
            f"Pipeline complete — "
            f"{_pipeline_state['jobs_succeeded']} succeeded, "
            f"{_pipeline_state['jobs_failed']} failed "
            f"out of {_pipeline_state['jobs_total']} jobs"
        )
        _pipeline_state["elapsed_seconds"] = round(time.time() - _pipeline_state["started_at"], 1)
        _pipeline_state["results"] = results

        print(f"[Pipeline] Complete: {len(results)} jobs processed")
        await analytics_dao.log_activity(
            "job", "pipeline_complete",
            f"Pipeline: {_pipeline_state['jobs_succeeded']} succeeded, "
            f"{_pipeline_state['jobs_failed']} failed in "
            f"{_pipeline_state['elapsed_seconds']}s",
        )

        # Auto-reset after delay
        asyncio.create_task(_auto_reset())

        return {
            "status": "complete",
            "total": len(filtered_apps),
            "succeeded": _pipeline_state["jobs_succeeded"],
            "failed": _pipeline_state["jobs_failed"],
            "elapsed_seconds": _pipeline_state["elapsed_seconds"],
            "results": results,
        }

    except Exception as e:
        _pipeline_state["status"] = "error"
        _pipeline_state["message"] = f"Pipeline failed: {e}"
        print(f"[Pipeline] Fatal error: {e}")
        await analytics_dao.log_activity(
            "job", "pipeline_error", f"Pipeline failed: {e}", severity="error",
        )
        return {"status": "error", "message": str(e), "results": results}


async def _send_telegram_notification(
    job_title: str,
    company: str,
    job_url: str,
    match_pct: float,
    app_id: int,
    resume_snippet: str = "",
    cover_letter_snippet: str = "",
) -> bool:
    """
    Send a Telegram notification with job details and generated documents.

    Uses the notification_manager's send_job_match_alert for the initial
    alert, then sends a detailed follow-up with the job link and
    resume/cover letter snippets.
    """
    try:
        # First, send the match alert (this is handled by notification_manager)
        await notification_manager.send_job_match_alert(
            job_title=job_title,
            company=company,
            match_score=match_pct,
            job_id=app_id,
        )

        # Then send a detailed message with job link and docs
        priority_map = {
            "high": "high",
            "normal": "normal",
        }
        priority = "high" if match_pct >= 80 else "normal"

        # Build a richer message — use HTML tags since TelegramChannel uses parse_mode="HTML"
        import html as html_mod
        safe_title = html_mod.escape(job_title)
        safe_company = html_mod.escape(company)
        safe_resume = html_mod.escape(resume_snippet[:600])
        safe_cover = html_mod.escape(cover_letter_snippet[:400])

        detailed_body = f"🎯 <b>{safe_title}</b> at <b>{safe_company}</b>\n"
        detailed_body += f"📊 Match: {match_pct:.0f}%\n"
        if job_url:
            detailed_body += f'🔗 <a href="{html_mod.escape(job_url)}">Apply Here</a>\n'
        detailed_body += f"\n📄 <b>Optimized Resume (Preview):</b>\n"
        detailed_body += f"<pre>{safe_resume}...\n</pre>\n"
        if safe_cover:
            detailed_body += f"\n✉️ <b>Cover Letter (Preview):</b>\n"
            detailed_body += f"<pre>{safe_cover}...\n</pre>\n"
        detailed_body += f"\n✅ Application #{app_id} — ready for review"

        from notifications.telegram import TelegramChannel
        from notifications.base import NotificationEvent, Priority, Category, Channel

        telegram = TelegramChannel()
        if not await telegram.is_enabled():
            print("[Pipeline] Telegram not configured; skipping detailed notification")
            return False

        event = NotificationEvent(
            title=f"📄 Job Application Generated: {job_title}",
            body=detailed_body,
            priority=Priority(priority),
            category=Category.JOB_MATCH,
            metadata={
                "application_id": app_id,
                "company": company,
                "title": job_title,
                "match_score": f"{match_pct:.0f}%",
                "job_url": job_url,
                "pipeline_processed": "true",
            },
        )
        result = await telegram.send(event)
        return result.success

    except Exception as e:
        print(f"[Pipeline] Telegram notification error: {e}")
        return False


async def _auto_reset():
    """Reset pipeline state to idle after a delay."""
    await asyncio.sleep(15)
    if _pipeline_state["status"] in ("complete", "error"):
        _pipeline_state["status"] = "idle"
        _pipeline_state["progress_pct"] = 0
