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
import html as html_mod
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("barq.pipeline")

from database import analytics_dao, db_connection, jobs_dao, settings_dao
from knowledge.auto_extractor import AutoExtractor
from notifications.manager import notification_manager
from utils import safe_filename

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
                    job_slug = safe_filename(f"{company}_{job_title}".replace(" ", "_"), max_len=50)

                    # Generate resume PDF with JD-aware filtering
                    job_description = job.get("description", "")
                    resume_pdf_result = await pdf_gen.generate(
                        pdf_resume_data,
                        output_dir=str(GENERATED_DIR / f"optimized_{job_slug}"),
                        filename=f"Resume_{job_slug}",
                        job_description=job_description,
                    )
                    if resume_pdf_result.get("status") == "completed":
                        pdf_paths["resume"] = resume_pdf_result["pdf_path"]

                    # Save cover letter as text file (PDF template not available for cover letters)
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
                        resume=resume,
                        evaluation=app.get("evaluation"),
                        resume_snippet=optimized_md[:500] if optimized_md else "",
                        cover_letter_snippet=cover_letter[:300] if cover_letter else "",
                        pdf_paths=pdf_paths,
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


def _format_resume_html(resume: dict[str, Any]) -> str:
    """
    Format resume data as clean Telegram-compatible HTML following the ATS template.

    Template structure:
    <b>Name</b>
    Location | Email | LinkedIn | GitHub | Portfolio

    <b>SUMMARY</b>
    Professional summary paragraph...

    <b>TECHNICAL SKILLS</b>
    Backend: ...
    Frontend: ...
    Cloud & DevOps: ...
    Databases: ...
    Core Concepts: ...

    <b>EXPERIENCE</b>
    <b>Role</b>
    Company | Dates | Location
    • achievement

    <b>PROJECTS</b>
    <b>Name</b>: description

    <b>EDUCATION</b>
    Degree
    University | Year

    <b>CERTIFICATIONS</b>
    Name — Issuer (Date)
    """

    raw_md = resume.get("raw_md", "")
    lines: list[str] = []

    # ── Header ──────────────────────────────────────────────────────
    name = resume.get("full_name", "Sai Prabhat")
    lines.append(f"<b>{html_mod.escape(name)}</b>")

    # Build contact line: Location | Email | LinkedIn | GitHub | Portfolio
    location = "Lucknow, India"
    loc_m = re.search(r"(?im)^\*\*Location:\*\*\s*(.+)", raw_md)
    if loc_m:
        location = loc_m.group(1).strip()

    email = resume.get("email", "")
    linkedin_url = resume.get("linkedin_url", "")
    github_url = resume.get("github_url", "")
    portfolio_url = resume.get("portfolio_url", "")

    contact_parts = []
    contact_parts.append(html_mod.escape(location))
    if email:
        contact_parts.append(html_mod.escape(email))
    if linkedin_url:
        display = linkedin_url.replace("https://", "").replace("http://", "").rstrip("/")
        display = display.replace("www.", "")
        contact_parts.append(f'<a href="{html_mod.escape(linkedin_url)}">{html_mod.escape(display)}</a>')
    if github_url:
        display = github_url.replace("https://", "").replace("http://", "").rstrip("/")
        display = display.replace("www.", "")
        contact_parts.append(f'<a href="{html_mod.escape(github_url)}">{html_mod.escape(display)}</a>')
    if portfolio_url:
        display = portfolio_url.replace("https://", "").replace("http://", "").rstrip("/")
        display = display.replace("www.", "")
        contact_parts.append(f'<a href="{html_mod.escape(portfolio_url)}">{html_mod.escape(display)}</a>')

    lines.append(" | ".join(contact_parts))
    lines.append("")

    # ── Summary ─────────────────────────────────────────────────────
    lines.append("<b>SUMMARY</b>")
    summary = resume.get("summary", "") or resume.get("headline", "")
    if summary:
        lines.append(html_mod.escape(summary.strip()[:400]))
    else:
        lines.append("Full Stack Engineer with 3+ years experience architecting scalable backend systems.")
    lines.append("")

    # ── Technical Skills ────────────────────────────────────────────
    lines.append("<b>TECHNICAL SKILLS</b>")
    skill_groups: dict[str, list[str]] = {
        "Backend": [], "Frontend": [], "Cloud & DevOps": [],
        "Databases": [], "Core Concepts": [],
    }
    skills_match = re.search(
        r"(?i)(?:^|\n)##\s*(?:skills|technical skills|technologies)\s*\n(.*?)(?=\n##\s|\Z)",
        raw_md, re.DOTALL,
    )
    if skills_match:
        for skill_line in skills_match.group(1).split("\n"):
            cl = skill_line.strip().lstrip("-* ").strip()
            if ":" in cl and not cl.startswith("http"):
                gp, ip = cl.split(":", 1)
                cg = gp.strip().strip("*").strip()
                if cg in skill_groups:
                    skill_groups[cg] = [
                        x.strip().strip("*").strip()
                        for x in ip.split(",") if x.strip()
                    ]
    for gn in ["Backend", "Frontend", "Cloud & DevOps", "Databases", "Core Concepts"]:
        items = skill_groups.get(gn, [])
        line = f"<b>{gn}:</b> {html_mod.escape(', '.join(items[:8]))}" if items else ""
        if line:
            lines.append(line)
    lines.append("")

    # ── Experience (up to 3 entries) ─────────────────────────────────
    exp_list = resume.get("experience", [])
    if exp_list:
        lines.append("<b>EXPERIENCE</b>")
        for exp in exp_list[:3]:
            role = exp.get("role", "")
            company_name = exp.get("company", "")
            raw_date_line = exp.get("date_range", "")
            bullets = exp.get("bullets", [])

            # Parse date & location from date_range
            location_str = "Remote"
            clean_dates = raw_date_line
            if raw_date_line:
                pipe_parts = [p.strip() for p in raw_date_line.split("|")]
                if len(pipe_parts) >= 2:
                    location_str = pipe_parts[-1].replace("*", "").strip()
                    for part in pipe_parts:
                        dm = re.search(
                            r"(\w+\s+\d{4})\s*[-\u2013\u2014to]+\s*(\w+\s+\d{4}|present|current|now)",
                            part, re.IGNORECASE,
                        )
                        if dm:
                            clean_dates = dm.group(0)
                            break

            # Build sub-header: Company | Dates | Location
            sub_parts = []
            if company_name:
                sub_parts.append(html_mod.escape(company_name))
            if clean_dates:
                sub_parts.append(html_mod.escape(clean_dates.replace("|", "").strip()))
            sub_parts.append(location_str)

            lines.append(f"<b>{html_mod.escape(role)}</b>")
            lines.append(" | ".join(sub_parts))
            for b in bullets[:3]:
                if b:
                    lines.append(f"  • {html_mod.escape(b[:200])}")
            lines.append("")

    # ── Projects (up to 3 entries) ──────────────────────────────────
    proj_list = resume.get("projects", [])
    if proj_list:
        lines.append("<b>PROJECTS</b>")
        for proj in proj_list[:3]:
            name = proj.get("name", "")
            desc = proj.get("description", "")
            if name:
                desc_text = html_mod.escape(desc[:150]) if desc else ""
                if desc_text:
                    lines.append(f"  • <b>{html_mod.escape(name)}</b>: {desc_text}")
                else:
                    lines.append(f"  • <b>{html_mod.escape(name)}</b>")
        lines.append("")

    # ── Education ───────────────────────────────────────────────────
    edu_list = resume.get("education", [])
    if edu_list:
        lines.append("<b>EDUCATION</b>")
        for edu in edu_list[:2]:
            title = edu.get("title", "")
            if title:
                lines.append(f"  • {html_mod.escape(title)}")
        lines.append("")

    # ── Certifications (from structured parser data) ───────────────
    cert_list = resume.get("certifications", [])
    if cert_list:
        lines.append("<b>CERTIFICATIONS</b>")
        for cert in cert_list[:3]:
            name = cert.get("name", "")
            issuer = cert.get("issuer", "")
            date = cert.get("date", "")
            credential = cert.get("credential", "")
            parts = [html_mod.escape(name)]
            if issuer:
                parts.append(html_mod.escape(issuer))
            if date:
                parts.append(html_mod.escape(date))
            cert_line = " — ".join(parts)
            lines.append(f"  • {cert_line}")
            if credential:
                cred_display = html_mod.escape(credential[:80])
                lines.append(f"    Credential: {cred_display}")

    return "\n".join(lines)


async def _send_telegram_notification(
    job_title: str,
    company: str,
    job_url: str,
    match_pct: float,
    app_id: int,
    resume: dict[str, Any] | None = None,
    evaluation: dict[str, Any] | None = None,
    resume_snippet: str = "",
    cover_letter_snippet: str = "",
    pdf_paths: dict[str, str] | None = None,
) -> bool:
    """
    Send a Telegram notification with job details and generated PDF documents.

    1. Sends the match alert via notification_manager
    2. Sends the resume PDF and cover letter PDF as Telegram document attachments
    3. Sends a follow-up message with job link and preview text
    """
    try:
        from notifications.base import Category, NotificationEvent, Priority
        from notifications.telegram import TelegramChannel

        telegram = TelegramChannel()
        if not await telegram.is_enabled():
            print("[Pipeline] Telegram not configured; skipping detailed notification")
            return False

        # 1. Send the match alert
        await notification_manager.send_job_match_alert(
            job_title=job_title,
            company=company,
            match_score=match_pct,
            job_id=app_id,
        )

        priority = "high" if match_pct >= 80 else "normal"
        safe_title = html_mod.escape(job_title)
        safe_company = html_mod.escape(company)

        # 2. Send actual PDF documents as Telegram file attachments
        pdfs_sent = 0

        # Send resume PDF
        resume_pdf = (pdf_paths or {}).get("resume", "")
        if resume_pdf and os.path.isfile(resume_pdf):
            resume_caption = (
                f"📄 <b>Optimized Resume</b>: {safe_title} @ {safe_company} "
                f"(Match: {match_pct:.0f}%)"
            )
            doc_result = await telegram.send_document(
                document_path=resume_pdf,
                caption=resume_caption,
            )
            if doc_result.success:
                pdfs_sent += 1
                print(f"[Pipeline] Resume PDF sent for {job_title}")

        # Send cover letter PDF
        cl_pdf = (pdf_paths or {}).get("cover_letter", "")
        if cl_pdf and os.path.isfile(cl_pdf) and cl_pdf.endswith(".pdf"):
            cl_caption = (
                f"✉️ <b>Cover Letter</b>: {safe_title} @ {safe_company}"
            )
            doc_result = await telegram.send_document(
                document_path=cl_pdf,
                caption=cl_caption,
            )
            if doc_result.success:
                pdfs_sent += 1
                print(f"[Pipeline] Cover letter PDF sent for {job_title}")

        # 3. Build the full notification body
        detailed_body = (
            f"🎯 <b>{safe_title}</b> at <b>{safe_company}</b>\n"
            f"📊 <b>Match Score:</b> {match_pct:.0f}%"
        )

        # ── Prominent Job Link ────────────────────────────────────────
        if job_url:
            detailed_body += (
                f"\n\n🔗 <a href=\"{html_mod.escape(job_url)}\">"
                f"<b>⬅️ OPEN APPLICATION LINK ➡️</b></a>"
            )

        # ── Match Reasoning (Pros/Cons) ──────────────────────────────
        if evaluation:
            try:
                pros_raw = evaluation.get("pros", "[]")
                cons_raw = evaluation.get("cons", "[]")
                pros = json.loads(pros_raw) if isinstance(pros_raw, str) else (pros_raw or [])
                cons = json.loads(cons_raw) if isinstance(cons_raw, str) else (cons_raw or [])
                reasoning = evaluation.get("reasoning", "")
            except (json.JSONDecodeError, TypeError):
                pros, cons, reasoning = [], [], ""

            if reasoning:
                detailed_body += f"\n\n💡 <b>Why this match?</b>\n{html_mod.escape(reasoning[:200])}"
            if pros:
                detailed_body += "\n\n✅ <b>Strengths:</b>"
                for p in pros[:3]:
                    detailed_body += f"\n• {html_mod.escape(str(p)[:100])}"
            if cons:
                detailed_body += "\n\n⚠️ <b>Considerations:</b>"
                for c in cons[:3]:
                    detailed_body += f"\n• {html_mod.escape(str(c)[:100])}"

        # ── Formatted Resume ─────────────────────────────────────────
        if resume:
            formatted_resume = _format_resume_html(resume)
            detailed_body += f"\n\n━━━ 📄 RESUME ━━━\n\n{formatted_resume}"

        # ── Cover Letter Snippet ──────────────────────────────────────
        if cover_letter_snippet:
            brief_cl = html_mod.escape(cover_letter_snippet[:200].strip())
            detailed_body += f"\n━━━ ✉️ COVER LETTER ━━━\n\n<pre>{brief_cl}</pre>\n"

        detailed_body += f"\n✅ Application #{app_id} — PDFs delivered above"

        # ── Telegram has 4096 char limit; split into multiple messages if needed ──
        messages_to_send: list[str] = []

        # Message 1: Header + link + match reasoning (always fits)
        msg1 = f"🎯 <b>{safe_title}</b> at <b>{safe_company}</b>\n📊 <b>Match Score:</b> {match_pct:.0f}%"
        if job_url:
            msg1 += f"\n\n🔗 <a href=\"{html_mod.escape(job_url)}\"><b>⬅️ OPEN APPLICATION LINK ➡️</b></a>"
        if evaluation:
            try:
                pros_raw = evaluation.get("pros", "[]")
                cons_raw = evaluation.get("cons", "[]")
                eval_pros = json.loads(pros_raw) if isinstance(pros_raw, str) else (pros_raw or [])
                eval_cons = json.loads(cons_raw) if isinstance(cons_raw, str) else (cons_raw or [])
                eval_reasoning = evaluation.get("reasoning", "")
            except (json.JSONDecodeError, TypeError):
                eval_pros, eval_cons, eval_reasoning = [], [], ""
            if eval_reasoning:
                msg1 += f"\n\n💡 <b>Why this match?</b>\n{html_mod.escape(eval_reasoning[:200])}"
            if eval_pros:
                msg1 += "\n\n✅ <b>Strengths:</b>"
                for p in eval_pros[:3]:
                    msg1 += f"\n• {html_mod.escape(str(p)[:100])}"
            if eval_cons:
                msg1 += "\n\n⚠️ <b>Considerations:</b>"
                for c in eval_cons[:3]:
                    msg1 += f"\n• {html_mod.escape(str(c)[:100])}"
        messages_to_send.append(msg1)

        # Message 2: Formatted resume
        if resume:
            msg2 = f"━━━ 📄 RESUME ━━━\n\n{_format_resume_html(resume)}"
            messages_to_send.append(msg2)

        # Message 3: Cover letter snippet (optional)
        if cover_letter_snippet:
            brief_cl = html_mod.escape(cover_letter_snippet[:200].strip())
            msg3 = f"━━━ ✉️ COVER LETTER ━━━\n\n<pre>{brief_cl}</pre>"
            messages_to_send.append(msg3)

        # Add footer to the last message
        messages_to_send[-1] += f"\n\n✅ Application #{app_id}"

        # Send each message — use send_html_message() for the resume (msg1)
        # to bypass _format_message() double-escaping, and standard send()
        # for plain-text messages (msg2, msg3).
        all_sent = True
        for idx, msg in enumerate(messages_to_send):
            if len(msg) > 4096:
                if idx == 1 and resume:
                    # Build compressed resume (header + summary + skills only)
                    compressed = (
                        f"<b>{html_mod.escape(resume.get('full_name','Sai Prabhat'))}</b>\n"
                        f"{html_mod.escape(resume.get('email',''))} | "
                        f"{html_mod.escape(resume.get('linkedin_url',''))}"
                    )
                    summary = (resume.get("summary", "") or "").strip()[:200]
                    if summary:
                        compressed += f"\n\n{html_mod.escape(summary)}"
                    compressed += "\n\n<i>Full resume attached as PDF. See document above.</i>"
                    msg = f"━━━ 📄 RESUME (condensed) ━━━\n\n{compressed}"
                    if len(msg) > 4096:
                        msg = msg[:4090] + "..."

            # Use send_html_message() for resume which already has HTML tags,
            # use standard send() for plain-text messages (match alert, cover letter)
            if idx == 1:
                # Resume message — already HTML formatted, bypass double-escaping
                result = await telegram.send_html_message(
                    text=msg,
                    title=f"📄 Resume: {job_title}",
                    disable_notification=(priority != "high"),
                )
            else:
                # Match alert or cover letter — plain text, use standard send()
                event = NotificationEvent(
                    title=f"🎯 Job Match: {job_title}" if idx == 0 else f"✉️ Cover Letter: {job_title}",
                    body=msg,
                    priority=Priority(priority),
                    category=Category.JOB_MATCH,
                    metadata={
                        "application_id": app_id,
                        "company": company,
                        "title": job_title,
                        "match_score": f"{match_pct:.0f}%",
                        "job_url": job_url,
                        "pdfs_sent": pdfs_sent,
                        "part": f"{idx + 1}/{len(messages_to_send)}",
                    },
                )
                result = await telegram.send(event)

            if not result.success:
                all_sent = False
                print(f"[Pipeline] Failed to send message part {idx + 1}: {result.error}")

        return all_sent or pdfs_sent > 0

    except Exception as e:
        print(f"[Pipeline] Telegram notification error: {e}")
        return False


async def _auto_reset():
    """Reset pipeline state to idle after a delay."""
    await asyncio.sleep(15)
    if _pipeline_state["status"] in ("complete", "error"):
        _pipeline_state["status"] = "idle"
        _pipeline_state["progress_pct"] = 0
