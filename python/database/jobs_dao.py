"""
Data access layer for job search module.
Handles CRUD for job listings, evaluations, and applications.
"""

import hashlib
import re

from datetime import datetime, timezone
from typing import Any, Optional

from .connection import db_connection


def _sanitize_url(url: str) -> str:
    """Sanitize a URL for safe database storage.

    Returns the URL as-is if it starts with http:// or https://.
    If the URL looks like a bare domain (e.g. "example.com/jobs/123")
    or starts with a slash (relative path), prepends https://
    and the domain context.
    Returns empty string for filesystem paths, garbage, or empty input.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url

    # Reject Windows paths (B:/, C:\\, etc.) or pure numbers/symbols
    if re.match(r'^[A-Za-z]:\\', url) or re.match(r'^[A-Za-z]:/', url):
        return ""
    if not re.match(r'^[\w\-./:?#\[\]@!$&\'()*+,;=~%]+$', url):
        return ""

    # Bare domain or path: prepend https://
    if url.startswith("/"):  # Relative path — can't resolve to full URL
        return ""
    if "." in url and not url.startswith((".", "..")):
        # Looks like a domain — prepend https://
        return f"https://{url}"

    return ""


def _normalize_text(value: Any) -> str:
    """Lowercase, strip punctuation, and collapse whitespace for fingerprinting."""
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _job_fingerprint(job: dict[str, Any]) -> str:
    """Stable dedup fingerprint for a job lacking a stable external id / URL.

    Built from normalized title + company + location so the same posting seen
    on multiple scans (or from boards that omit URLs) maps to one row.
    Returns an empty string when there is nothing to fingerprint.
    """
    parts = [
        _normalize_text(job.get("title", "")),
        _normalize_text(job.get("company", "")),
        _normalize_text(job.get("location", "")),
    ]
    raw = "|".join(p for p in parts if p)
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class JobsDAO:
    """DAO for job-related database operations."""

    # ─── Job Listings ──────────────────────────────────────────────────────

    async def _find_existing_listing_id(self, job: dict[str, Any]) -> Optional[int]:
        """Locate an existing listing matching this job (dedup lookup).

        Deduplication keys (first match wins):
          1. (source_board, external_id) when the board supplies a stable id
          2. source_url when present
          3. fingerprint of normalized title + company + location (boards that
             omit ids/urls — e.g. BambooHR, Workday — still collapse to one row)
        """
        board = (job.get("source_board") or job.get("source") or "").strip()
        external_id = (job.get("external_id") or job.get("listing_id") or "").strip()
        source_url = _sanitize_url(job.get("source_url") or job.get("url") or "")
        fingerprint = _job_fingerprint(job)

        if board and external_id:
            row = await db_connection.fetch_one(
                "SELECT id FROM job_listings "
                "WHERE source_board = ? AND external_id = ? AND external_id != '' LIMIT 1",
                (board, external_id),
            )
            if row:
                return row["id"]

        if source_url:
            row = await db_connection.fetch_one(
                "SELECT id FROM job_listings "
                "WHERE source_url = ? AND source_url != '' LIMIT 1",
                (source_url,),
            )
            if row:
                return row["id"]

        if fingerprint:
            row = await db_connection.fetch_one(
                "SELECT id FROM job_listings "
                "WHERE fingerprint = ? AND fingerprint != '' LIMIT 1",
                (fingerprint,),
            )
            if row:
                return row["id"]

        return None

    async def _insert_listing_row(self, job: dict[str, Any]) -> int:
        """Insert the row, resolving the surviving id when a concurrent scan wins."""
        board = (job.get("source_board") or job.get("source") or "").strip()
        source_url = _sanitize_url(job.get("source_url") or job.get("url") or "")
        fingerprint = _job_fingerprint(job)

        sql = """
            INSERT OR IGNORE INTO job_listings (
                external_id, title, company, location, description,
                salary_min, salary_max, salary_currency, salary_period,
                employment_type, remote_status, source_board, source_url,
                posted_date, company_rating, skills_required, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        inserted_id = await db_connection.insert(sql, (
            job.get("external_id", ""),
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("description", ""),
            job.get("salary_min", 0),
            job.get("salary_max", 0),
            job.get("salary_currency", "USD"),
            job.get("salary_period", "yearly"),
            job.get("employment_type", "full_time"),
            job.get("remote_status", "unknown"),
            board,
            source_url,
            job.get("posted_date", datetime.now(timezone.utc).isoformat()),
            job.get("company_rating", 0.0),
            job.get("skills_required", "[]"),
            fingerprint,
        ))
        # A concurrent scan may have inserted the same job between our SELECT
        # and this INSERT — OR IGNORE silently skipped it and inserted_id is
        # stale. Resolve the winner by fingerprint (jobs always carry one
        # here; fingerprint-less rows aren't covered by the unique indexes).
        if fingerprint:
            row = await db_connection.fetch_one(
                "SELECT id FROM job_listings "
                "WHERE fingerprint = ? AND fingerprint != '' LIMIT 1",
                (fingerprint,),
            )
            if row:
                return row["id"]
        return inserted_id

    async def insert_job_listing(self, job: dict[str, Any]) -> int:
        """Find-or-insert a job listing, returning the id of the existing or new row."""
        existing = await self._find_existing_listing_id(job)
        if existing is not None:
            return existing
        return await self._insert_listing_row(job)

    async def insert_job_listing_if_new(self, job: dict[str, Any]) -> Optional[int]:
        """Insert only genuinely new jobs.

        Returns the new listing id, or ``None`` when a matching listing already
        exists (dedup by board+external_id, source_url, or fingerprint). Scan
        flows use this so already-known jobs are never re-counted, re-evaluated,
        or re-notified.
        """
        if await self._find_existing_listing_id(job) is not None:
            return None
        return await self._insert_listing_row(job)

    async def get_job_listing(self, job_id: int) -> Optional[dict]:
        """Get a job listing by ID."""
        return await db_connection.fetch_one(
            "SELECT * FROM job_listings WHERE id = ?", (job_id,)
        )

    async def get_active_jobs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Get active (non-expired) job listings with their evaluations."""
        sql = """
            SELECT j.*, e.overall_score, e.match_percentage, e.evaluated_at,
                   e.pros as eval_pros, e.cons as eval_cons, e.reasoning as eval_reasoning
            FROM job_listings j
            LEFT JOIN job_evaluations e ON j.id = e.job_listing_id
            WHERE j.is_active = 1
            ORDER BY e.match_percentage DESC, j.scanned_at DESC
            LIMIT ? OFFSET ?
        """
        return await db_connection.fetch_all(sql, (limit, offset))

    async def get_jobs_by_source(self, source_board: str, limit: int = 50) -> list[dict]:
        """Get jobs from a specific board."""
        return await db_connection.fetch_all(
            "SELECT * FROM job_listings WHERE source_board = ? AND is_active = 1 ORDER BY scanned_at DESC LIMIT ?",
            (source_board, limit),
        )

    async def search_jobs(self, query: str, limit: int = 50) -> list[dict]:
        """Search jobs by title or company."""
        search_term = f"%{query}%"
        sql = """
            SELECT j.*, e.overall_score, e.match_percentage
            FROM job_listings j
            LEFT JOIN job_evaluations e ON j.id = e.job_listing_id
            WHERE j.is_active = 1
              AND (j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)
            ORDER BY e.match_percentage DESC
            LIMIT ?
        """
        return await db_connection.fetch_all(sql, (search_term, search_term, search_term, limit))

    async def deactivate_expired_jobs(self) -> int:
        """Mark jobs past their expiration date as inactive."""
        return await db_connection.update(
            "UPDATE job_listings SET is_active = 0 WHERE expires_date < datetime('now') AND is_active = 1"
        )

    # ─── Job Evaluations ───────────────────────────────────────────────────

    async def insert_evaluation(self, eval_data: dict[str, Any]) -> int:
        """Insert an AI evaluation for a job listing."""
        sql = """
            INSERT INTO job_evaluations (
                job_listing_id, overall_score, role_fit_score, culture_score,
                compensation_score, growth_score, red_flag_score,
                match_percentage, reasoning, pros, cons, evaluated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            eval_data["job_listing_id"],
            eval_data.get("overall_score", 0),
            eval_data.get("role_fit_score", 0),
            eval_data.get("culture_score", 0),
            eval_data.get("compensation_score", 0),
            eval_data.get("growth_score", 0),
            eval_data.get("red_flag_score", 0),
            eval_data.get("match_percentage", 0),
            eval_data.get("reasoning", ""),
            eval_data.get("pros", "[]"),
            eval_data.get("cons", "[]"),
            eval_data.get("evaluated_by", "llm"),
        ))

    async def get_evaluation(self, listing_id: int) -> Optional[dict]:
        """Get the evaluation for a specific job listing."""
        return await db_connection.fetch_one(
            "SELECT * FROM job_evaluations WHERE job_listing_id = ? ORDER BY evaluated_at DESC LIMIT 1",
            (listing_id,),
        )

    async def get_top_matches(self, min_score: float = 3.0, limit: int = 20) -> list[dict]:
        """Get top-scoring job matches — one row per listing (latest evaluation)."""
        sql = """
            SELECT j.*, e.overall_score, e.match_percentage, e.reasoning,
                   e.pros, e.cons, e.role_fit_score, e.culture_score,
                   e.compensation_score, e.growth_score
            FROM (
                SELECT * FROM job_evaluations
                WHERE id IN (
                    SELECT MAX(id) FROM job_evaluations GROUP BY job_listing_id
                )
            ) e
            JOIN job_listings j ON j.id = e.job_listing_id
            WHERE e.overall_score >= ? AND j.is_active = 1
            ORDER BY e.overall_score DESC, e.match_percentage DESC
            LIMIT ?
        """
        return await db_connection.fetch_all(sql, (min_score, limit))

    # ─── Applications ──────────────────────────────────────────────────────

    async def insert_application(self, app_data: dict[str, Any]) -> int:
        """Create a new job application record."""
        sql = """
            INSERT INTO applications (
                job_listing_id, status, application_type, notes
            ) VALUES (?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            app_data["job_listing_id"],
            app_data.get("status", "draft"),
            app_data.get("application_type", "auto"),
            app_data.get("notes", ""),
        ))

    async def get_application(self, app_id: int) -> Optional[dict]:
        """Get an application by ID with job details."""
        sql = """
            SELECT a.*, j.title, j.company, j.location, j.salary_min, j.salary_max,
                   j.source_board, j.source_url
            FROM applications a
            JOIN job_listings j ON j.id = a.job_listing_id
            WHERE a.id = ?
        """
        return await db_connection.fetch_one(sql, (app_id,))

    async def get_applications_by_status(
        self, status: str, limit: int = 50, exclude_notified: bool = False
    ) -> list[dict]:
        """Get applications filtered by status.

        When ``exclude_notified`` is set, applications that already have a
        ``notified_at`` timestamp are skipped, so pipeline runs don't
        re-notify (or re-generate documents for) known jobs.
        """
        notified_filter = "AND a.notified_at IS NULL " if exclude_notified else ""
        sql = f"""
            SELECT a.*, j.title, j.company, j.location, j.salary_min, j.salary_max
            FROM applications a
            JOIN job_listings j ON j.id = a.job_listing_id
            WHERE a.status = ? {notified_filter}
            ORDER BY a.updated_at DESC
            LIMIT ?
        """
        return await db_connection.fetch_all(sql, (status, limit))

    async def get_pending_review_applications(self) -> list[dict]:
        """Get applications awaiting user review."""
        return await self.get_applications_by_status("ready_for_review")

    async def update_application_status(
        self, app_id: int, status: str, **kwargs
    ) -> int:
        """Update application status and optional fields."""
        sets = ["status = ?", "updated_at = datetime('now')"]
        params = [status]

        for field, value in kwargs.items():
            if field in ("submitted_at", "response_received_at", "interview_date", "notified_at"):
                sets.append(f"{field} = ?")
                params.append(value)
            elif field in ("response_type", "rejection_reason", "offer_details", "notes", "score"):
                sets.append(f"{field} = ?")
                params.append(value)

        params.append(app_id)
        sql = f"UPDATE applications SET {', '.join(sets)} WHERE id = ?"
        return await db_connection.update(sql, tuple(params))

    async def get_application_count_by_status(self) -> list[dict]:
        """Get count of applications grouped by status."""
        return await db_connection.fetch_all(
            "SELECT status, COUNT(*) as count FROM applications GROUP BY status"
        )

    # ─── Application Documents ─────────────────────────────────────────────

    async def insert_document(self, doc_data: dict[str, Any]) -> int:
        """Store a generated resume or cover letter."""
        sql = """
            INSERT INTO application_documents (
                application_id, document_type, content, file_path, format, generated_by
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            doc_data["application_id"],
            doc_data["document_type"],
            doc_data.get("content", ""),
            doc_data.get("file_path", ""),
            doc_data.get("format", "markdown"),
            doc_data.get("generated_by", "llm"),
        ))

    async def get_active_documents(self, application_id: int) -> list[dict]:
        """Get all active documents for an application."""
        return await db_connection.fetch_all(
            "SELECT * FROM application_documents WHERE application_id = ? AND is_active = 1 ORDER BY version DESC",
            (application_id,),
        )

    # ─── Application Status Lookup ──────────────────────────────────────

    async def get_application_statuses_for_jobs(
        self, job_listing_ids: list[int]
    ) -> dict[int, str]:
        """Get the latest application status for multiple job listings at once.

        Returns a dict mapping job_listing_id -> status.
        Jobs with no application will not appear in the dict.
        """
        if not job_listing_ids:
            return {}
        placeholders = ",".join("?" for _ in job_listing_ids)
        rows = await db_connection.fetch_all(
            f"""SELECT job_listing_id, status FROM applications
               WHERE job_listing_id IN ({placeholders})
               AND id IN (
                   SELECT MAX(id) FROM applications
                   WHERE job_listing_id IN ({placeholders})
                   GROUP BY job_listing_id
               )""",
            (*job_listing_ids, *job_listing_ids),
        )
        return {r["job_listing_id"]: r["status"] for r in rows}

    # ─── Match Analytics ──────────────────────────────────────────────────

    async def get_match_analytics(self) -> dict:
        """Get job match analytics: score tiers, sources, scan stats."""
        # Total jobs + evaluations
        total_jobs = await db_connection.fetch_one(
            "SELECT COUNT(*) as cnt FROM job_listings WHERE is_active = 1"
        )
        total_evaluated = await db_connection.fetch_one(
            "SELECT COUNT(DISTINCT job_listing_id) as cnt FROM job_evaluations"
        )

        # Score tiers
        tiers = await db_connection.fetch_all("""
            SELECT
                CASE
                    WHEN e.match_percentage >= 80 THEN 'excellent'
                    WHEN e.match_percentage >= 70 THEN 'strong'
                    WHEN e.match_percentage >= 60 THEN 'good'
                    ELSE 'fair'
                END as tier,
                COUNT(*) as count,
                ROUND(AVG(e.match_percentage), 1) as avg_pct
            FROM job_evaluations e
            JOIN job_listings j ON j.id = e.job_listing_id AND j.is_active = 1
            GROUP BY tier
            ORDER BY avg_pct DESC
        """)

        # Top sources
        sources = await db_connection.fetch_all("""
            SELECT
                j.source_board,
                COUNT(*) as job_count,
                ROUND(AVG(e.match_percentage), 1) as avg_match
            FROM job_listings j
            JOIN job_evaluations e ON e.job_listing_id = j.id
            WHERE j.is_active = 1 AND j.source_board != ''
            GROUP BY j.source_board
            ORDER BY job_count DESC
            LIMIT 10
        """)

        # Recent scan activity
        scans = await db_connection.fetch_all("""
            SELECT created_at as date, description as summary
            FROM activity_log
            WHERE type = 'job' AND action = 'scan'
            ORDER BY created_at DESC
            LIMIT 5
        """)

        # Application status breakdown
        app_statuses = await db_connection.fetch_all(
            "SELECT status, COUNT(*) as count FROM applications GROUP BY status ORDER BY count DESC"
        )

        return {
            "total_jobs": total_jobs["cnt"] if total_jobs else 0,
            "total_evaluated": total_evaluated["cnt"] if total_evaluated else 0,
            "score_tiers": [
                {"tier": r["tier"], "count": r["count"], "avg_percentage": r["avg_pct"]}
                for r in tiers
            ],
            "top_sources": [
                {"source": r["source_board"], "job_count": r["job_count"], "avg_match": r["avg_match"]}
                for r in sources
            ],
            "recent_scans": [
                {"date": r["date"], "summary": r["summary"]}
                for r in scans
            ],
            "application_statuses": [
                {"status": r["status"], "count": r["count"]}
                for r in app_statuses
            ],
        }
