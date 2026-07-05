"""
Response rate analytics and follow-up automation for job applications.

Tracks:
- Response times per company/platform
- Response rates by source board
- Follow-up schedules and automation
- Analytics insights
"""

from datetime import datetime, timezone
from typing import Any, Optional
from database import db_connection, analytics_dao


class ResponseTracker:
    """Tracks application responses and computes analytics."""

    async def record_response(
        self,
        application_id: int,
        response_type: str,
        response_text: Optional[str] = None,
        interview_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record a response (interview, rejection, offer) for an application."""
        now = datetime.now(timezone.utc).isoformat()
        update_data = {
            "response_received_at": now,
            "response_type": response_type,
        }
        if interview_date:
            update_data["interview_date"] = interview_date

        # Get the application to compute response time
        app = await db_connection.fetch_one(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        )
        if not app:
            return {"status": "error", "message": "Application not found"}

        # Calculate response time in days
        response_time = None
        if app.get("submitted_at"):
            submitted = datetime.fromisoformat(app["submitted_at"])
            now_dt = datetime.now(timezone.utc)
            response_time = round((now_dt - submitted.replace(tzinfo=timezone.utc)).total_seconds() / 86400, 1)

        # Update the application
        sets = ["response_received_at = ?", "response_type = ?", "updated_at = datetime('now')"]
        params = [now, response_type]

        if interview_date:
            sets.append("interview_date = ?")
            params.append(interview_date)

        if response_type == "interview":
            sets.append("status = 'interview'")
        elif response_type == "rejection":
            sets.append("status = 'rejected'")
        elif response_type == "offer":
            sets.append("status = 'offer'")

        params.append(application_id)
        sql = f"UPDATE applications SET {', '.join(sets)} WHERE id = ?"
        await db_connection.update(sql, tuple(params))

        # Log the response
        await analytics_dao.log_activity(
            "job", "response_received",
            f"Application #{application_id}: {response_type} (response time: {response_time or 'N/A'} days)",
        )

        return {
            "status": "recorded",
            "application_id": application_id,
            "response_type": response_type,
            "response_time_days": response_time,
        }

    async def get_response_analytics(self) -> dict[str, Any]:
        """Get comprehensive response rate analytics."""
        # Response rate by source board
        board_stats = await db_connection.fetch_all("""
            SELECT
                j.source_board,
                COUNT(DISTINCT a.id) as total_apps,
                SUM(CASE WHEN a.response_received_at IS NOT NULL THEN 1 ELSE 0 END) as responded,
                SUM(CASE WHEN a.response_type = 'interview' THEN 1 ELSE 0 END) as interviews,
                SUM(CASE WHEN a.response_type = 'rejection' THEN 1 ELSE 0 END) as rejections,
                SUM(CASE WHEN a.response_type = 'offer' THEN 1 ELSE 0 END) as offers,
                ROUND(AVG(
                    CASE WHEN a.submitted_at IS NOT NULL AND a.response_received_at IS NOT NULL
                    THEN (julianday(a.response_received_at) - julianday(a.submitted_at))
                    ELSE NULL END
                ), 1) as avg_response_time_days
            FROM applications a
            JOIN job_listings j ON j.id = a.job_listing_id
            WHERE a.submitted_at IS NOT NULL
            GROUP BY j.source_board
            ORDER BY total_apps DESC
        """)

        # Overall stats
        overall = await db_connection.fetch_one("""
            SELECT
                COUNT(*) as total_apps,
                SUM(CASE WHEN submitted_at IS NOT NULL THEN 1 ELSE 0 END) as submitted,
                SUM(CASE WHEN response_received_at IS NOT NULL THEN 1 ELSE 0 END) as responded,
                SUM(CASE WHEN response_type = 'interview' THEN 1 ELSE 0 END) as interviews,
                SUM(CASE WHEN response_type = 'rejection' THEN 1 ELSE 0 END) as rejections,
                SUM(CASE WHEN response_type = 'offer' THEN 1 ELSE 0 END) as offers,
                SUM(CASE WHEN response_type IS NULL AND submitted_at IS NOT NULL
                    AND julianday('now') - julianday(submitted_at) > 14 THEN 1 ELSE 0 END) as pending_followup
            FROM applications
        """)

        # Response funnel for charting
        funnel = await db_connection.fetch_all("""
            SELECT
                strftime('%Y-%m', submitted_at) as month,
                COUNT(*) as submitted,
                SUM(CASE WHEN response_received_at IS NOT NULL THEN 1 ELSE 0 END) as responded,
                SUM(CASE WHEN response_type = 'interview' THEN 1 ELSE 0 END) as interviews,
                SUM(CASE WHEN response_type = 'offer' THEN 1 ELSE 0 END) as offers
            FROM applications
            WHERE submitted_at IS NOT NULL
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """)

        # Recent responses
        recent = await db_connection.fetch_all("""
            SELECT
                a.id, a.response_type, a.response_received_at,
                j.title, j.company, j.source_board
            FROM applications a
            JOIN job_listings j ON j.id = a.job_listing_id
            WHERE a.response_received_at IS NOT NULL
            ORDER BY a.response_received_at DESC
            LIMIT 20
        """)

        total = overall
        response_rate = round((total["responded"] / max(total["submitted"], 1)) * 100, 1) if total else 0
        interview_rate = round((total["interviews"] / max(total["submitted"], 1)) * 100, 1) if total else 0
        offer_rate = round((total["offers"] / max(total["submitted"], 1)) * 100, 1) if total else 0

        return {
            "overall": {
                "total_applications": total["total_apps"] if total else 0,
                "submitted": total["submitted"] if total else 0,
                "responded": total["responded"] if total else 0,
                "interviews": total["interviews"] if total else 0,
                "rejections": total["rejections"] if total else 0,
                "offers": total["offers"] if total else 0,
                "pending_followup": total["pending_followup"] if total else 0,
                "response_rate": response_rate,
                "interview_rate": interview_rate,
                "offer_rate": offer_rate,
            },
            "by_source": [
                {
                    "source": row["source_board"],
                    "total": row["total_apps"],
                    "responded": row["responded"],
                    "interviews": row["interviews"],
                    "rejections": row["rejections"],
                    "offers": row["offers"],
                    "response_rate": round((row["responded"] / max(row["total_apps"], 1)) * 100, 1),
                    "avg_response_time_days": row["avg_response_time_days"],
                }
                for row in board_stats
            ],
            "funnel": [
                {
                    "month": row["month"],
                    "submitted": row["submitted"],
                    "responded": row["responded"],
                    "interviews": row["interviews"],
                    "offers": row["offers"],
                }
                for row in funnel
            ],
            "recent_responses": [
                {
                    "id": row["id"],
                    "type": row["response_type"],
                    "date": row["response_received_at"],
                    "title": row["title"],
                    "company": row["company"],
                    "source": row["source_board"],
                }
                for row in recent
            ],
        }

    async def get_followup_candidates(self) -> list[dict[str, Any]]:
        """Get applications that need follow-up (submitted > 14 days, no response)."""
        candidates = await db_connection.fetch_all("""
            SELECT
                a.id, a.submitted_at, a.status,
                j.title, j.company, j.source_board,
                julianday('now') - julianday(a.submitted_at) as days_since_submission
            FROM applications a
            JOIN job_listings j ON j.id = a.job_listing_id
            WHERE a.submitted_at IS NOT NULL
              AND a.response_received_at IS NULL
              AND julianday('now') - julianday(a.submitted_at) > 14
              AND a.status NOT IN ('rejected', 'withdrawn')
            ORDER BY days_since_submission DESC
        """)
        return candidates

    async def get_followup_history(self) -> list[dict[str, Any]]:
        """Get the history of follow-ups sent."""
        followups = await db_connection.fetch_all("""
            SELECT *
            FROM activity_log
            WHERE type = 'job' AND action = 'followup_sent'
            ORDER BY created_at DESC
            LIMIT 50
        """)
        return followups


class FollowUpAutomation:
    """Automates follow-up emails for applications without responses."""

    async def generate_followup(
        self,
        application: dict[str, Any],
        followup_number: int = 1,
    ) -> str:
        """Generate a follow-up email for an application."""
        company = application.get("company", "")
        title = application.get("title", "")

        templates = {
            1: (
                f"Hi {{company}} Team,\n\n"
                f"I'm writing to follow up on my application for the {title} position. "
                f"I'm very excited about the opportunity and wanted to reiterate my interest.\n\n"
                f"I believe my experience in [key skill] would be a great fit for this role.\n\n"
                f"Please let me know if you need any additional information from me.\n\n"
                f"Best regards,\n[Your Name]"
            ),
            2: (
                f"Hi {{company}} Team,\n\n"
                f"I wanted to check in again regarding my application for the {title} position. "
                f"I'm still very interested in joining {{company}} and contributing to your team.\n\n"
                f"I've continued to [relevant achievement] since applying.\n\n"
                f"I'd appreciate any update on the hiring process.\n\n"
                f"Best regards,\n[Your Name]"
            ),
            3: (
                f"Hi {{company}} Team,\n\n"
                f"I understand you're busy, but I wanted to touch base one more time "
                f"about the {title} position. I'm still enthusiastic about the opportunity.\n\n"
                f"If the position has been filled, I'd appreciate knowing so I can adjust my job search accordingly.\n\n"
                f"Thank you for your time.\n\n"
                f"Best regards,\n[Your Name]"
            ),
        }

        template = templates.get(followup_number, templates[3])
        return template.replace("{company}", company)

    async def schedule_followups(self) -> list[dict[str, Any]]:
        """Check all applications and schedule follow-ups where needed."""
        tracker = ResponseTracker()
        candidates = await tracker.get_followup_candidates()
        scheduled = []

        for app in candidates:
            days_since = app["days_since_submission"]
            if not days_since:
                continue

            # Determine follow-up number based on days
            if 14 <= days_since < 21:
                followup_num = 1
            elif 21 <= days_since < 35:
                followup_num = 2
            elif days_since >= 35:
                followup_num = 3
            else:
                continue

            # Check if we already sent a follow-up for this period
            existing = await db_connection.fetch_one(
                """SELECT COUNT(*) as count FROM activity_log
                   WHERE type = 'job' AND action = 'followup_sent'
                   AND description LIKE ?""",
                (f"%Application #{app['id']}%",),
            )
            if existing and existing["count"] >= followup_num:
                continue

            followup_text = await self.generate_followup(app, followup_num)
            scheduled.append({
                "application_id": app["id"],
                "company": app["company"],
                "title": app["title"],
                "followup_number": followup_num,
                "days_since": days_since,
                "followup_text": followup_text,
            })

        return scheduled

    async def send_followup(self, application_id: int, followup_number: int = 1) -> dict[str, Any]:
        """Mark a follow-up as sent for an application."""
        try:
            app = await db_connection.fetch_one(
                """SELECT a.*, j.title, j.company
                   FROM applications a
                   JOIN job_listings j ON j.id = a.job_listing_id
                   WHERE a.id = ?""",
                (application_id,),
            )
            if not app:
                return {"status": "error", "message": "Application not found"}

            # Log the follow-up
            await analytics_dao.log_activity(
                "job", "followup_sent",
                f"Application #{application_id} at {app['company']}: Follow-up #{followup_number} sent ({datetime.now(timezone.utc).isoformat()})",
            )

            return {
                "status": "sent",
                "application_id": application_id,
                "company": app["company"],
                "title": app["title"],
                "followup_number": followup_number,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
