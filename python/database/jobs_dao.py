"""
Data access layer for job search module.
Handles CRUD for job listings, evaluations, and applications.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from .connection import db_connection


class JobsDAO:
    """DAO for job-related database operations."""

    # ─── Job Listings ──────────────────────────────────────────────────────

    async def insert_job_listing(self, job: dict[str, Any]) -> int:
        """Insert a new job listing."""
        sql = """
            INSERT INTO job_listings (
                external_id, title, company, location, description,
                salary_min, salary_max, salary_currency, salary_period,
                employment_type, remote_status, source_board, source_url,
                posted_date, company_rating, skills_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
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
            job.get("source_board", ""),
            job.get("source_url", ""),
            job.get("posted_date", datetime.now(timezone.utc).isoformat()),
            job.get("company_rating", 0.0),
            job.get("skills_required", "[]"),
        ))

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
        """Get top-scoring job matches."""
        sql = """
            SELECT j.*, e.overall_score, e.match_percentage, e.reasoning,
                   e.pros, e.cons, e.role_fit_score, e.culture_score,
                   e.compensation_score, e.growth_score
            FROM job_evaluations e
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

    async def get_applications_by_status(self, status: str, limit: int = 50) -> list[dict]:
        """Get applications filtered by status."""
        sql = """
            SELECT a.*, j.title, j.company, j.location, j.salary_min, j.salary_max
            FROM applications a
            JOIN job_listings j ON j.id = a.job_listing_id
            WHERE a.status = ?
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
            if field in ("submitted_at", "response_received_at", "interview_date"):
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
