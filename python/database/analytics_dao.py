"""
Data access layer for analytics module.
Handles career funnel snapshots, social performance, and revenue tracking.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from .connection import db_connection


class AnalyticsDAO:
    """DAO for analytics operations."""

    # ─── Career Analytics ──────────────────────────────────────────────────

    async def insert_career_snapshot(self, data: dict[str, Any]) -> int:
        """Record a career funnel snapshot."""
        sql = """
            INSERT INTO career_analytics_snapshots (
                snapshot_date, jobs_scanned, matches_found, applications_sent,
                interviews_scheduled, offers_received, active_applications,
                avg_response_time_days, top_sources
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            data.get("snapshot_date", datetime.now(timezone.utc).date().isoformat()),
            data.get("jobs_scanned", 0),
            data.get("matches_found", 0),
            data.get("applications_sent", 0),
            data.get("interviews_scheduled", 0),
            data.get("offers_received", 0),
            data.get("active_applications", 0),
            data.get("avg_response_time_days", 0.0),
            data.get("top_sources", "[]"),
        ))

    async def get_latest_career_snapshot(self) -> Optional[dict]:
        """Get the most recent career analytics snapshot."""
        return await db_connection.fetch_one(
            "SELECT * FROM career_analytics_snapshots ORDER BY snapshot_date DESC, created_at DESC LIMIT 1"
        )

    async def get_career_trend(self, days: int = 30) -> list[dict]:
        """Get career analytics trend over time."""
        return await db_connection.fetch_all(
            """SELECT * FROM career_analytics_snapshots
               WHERE snapshot_date >= date('now', ? || ' days')
               ORDER BY snapshot_date ASC""",
            (f"-{days}",),
        )

    async def compute_funnel_summary(self) -> dict[str, Any]:
        """Aggregate current funnel metrics from live tables."""
        row = await db_connection.fetch_one("""
            SELECT
                (SELECT COUNT(*) FROM job_listings WHERE is_active = 1) as jobs_scanned,
                (SELECT COUNT(*) FROM job_evaluations WHERE overall_score >= 3.0) as matches_found,
                (SELECT COUNT(*) FROM applications WHERE status IN ('submitted', 'approved')) as applications_sent,
                (SELECT COUNT(*) FROM applications WHERE response_type = 'interview') as interviews_scheduled,
                (SELECT COUNT(*) FROM applications WHERE response_type = 'offer') as offers_received,
                (SELECT COUNT(*) FROM applications WHERE status NOT IN ('rejected', 'withdrawn')) as active_applications
        """)
        return dict(row) if row else {}

    # ─── Social Analytics ──────────────────────────────────────────────────

    async def insert_social_snapshot(self, data: dict[str, Any]) -> int:
        """Record a social media analytics snapshot."""
        sql = """
            INSERT INTO social_analytics_snapshots (
                snapshot_date, platform, followers, total_views,
                total_engagement, engagement_rate, videos_posted, revenue
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            data.get("snapshot_date", datetime.now(timezone.utc).date().isoformat()),
            data.get("platform", ""),
            data.get("followers", 0),
            data.get("total_views", 0),
            data.get("total_engagement", 0),
            data.get("engagement_rate", 0.0),
            data.get("videos_posted", 0),
            data.get("revenue", 0.0),
        ))

    async def get_latest_social_snapshots(self) -> list[dict]:
        """Get the most recent social snapshot per platform."""
        sql = """
            SELECT s1.*
            FROM social_analytics_snapshots s1
            WHERE s1.created_at = (
                SELECT MAX(s2.created_at)
                FROM social_analytics_snapshots s2
                WHERE s2.platform = s1.platform
            )
            ORDER BY s1.platform
        """
        return await db_connection.fetch_all(sql)

    async def get_social_trend(
        self, platform: str, days: int = 30
    ) -> list[dict]:
        """Get trend data for a specific platform."""
        return await db_connection.fetch_all(
            """SELECT * FROM social_analytics_snapshots
               WHERE platform = ? AND snapshot_date >= date('now', ? || ' days')
               ORDER BY snapshot_date ASC""",
            (platform, f"-{days}"),
        )

    async def get_cross_platform_summary(self) -> list[dict]:
        """Get latest metrics aggregated across all platforms."""
        latest = await self.get_latest_social_snapshots()
        return latest

    async def get_total_revenue(self, days: int = 30) -> float:
        """Get total revenue across all platforms for a period."""
        row = await db_connection.fetch_one(
            "SELECT COALESCE(SUM(amount), 0) as total FROM revenue_records WHERE created_at >= date('now', ? || ' days')",
            (f"-{days}",),
        )
        return row["total"] if row else 0.0

    # ─── Revenue ───────────────────────────────────────────────────────────

    async def insert_revenue(self, record: dict[str, Any]) -> int:
        """Record a revenue entry."""
        sql = """
            INSERT INTO revenue_records (
                source, platform, amount, currency,
                period_start, period_end, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            record.get("source", ""),
            record.get("platform", ""),
            record.get("amount", 0.0),
            record.get("currency", "USD"),
            record.get("period_start", ""),
            record.get("period_end", ""),
            record.get("status", "pending"),
            record.get("notes", ""),
        ))

    async def get_revenue_by_source(self, days: int = 90) -> list[dict]:
        """Get revenue grouped by source."""
        return await db_connection.fetch_all(
            """SELECT source, platform, SUM(amount) as total, COUNT(*) as count
               FROM revenue_records
               WHERE created_at >= date('now', ? || ' days')
               GROUP BY source, platform
               ORDER BY total DESC""",
            (f"-{days}",),
        )

    async def get_revenue_by_month(self, months: int = 6) -> list[dict]:
        """Get monthly revenue totals."""
        return await db_connection.fetch_all(
            """SELECT strftime('%Y-%m', period_start) as month,
                      SUM(amount) as total,
                      GROUP_CONCAT(DISTINCT source) as sources
               FROM revenue_records
               WHERE period_start >= date('now', ? || ' months', 'start of month')
               GROUP BY month
               ORDER BY month DESC""",
            (f"-{months}",),
        )

    async def get_latest_revenue_summary(self) -> dict[str, Any]:
        """Get aggregated revenue summary."""
        row = await db_connection.fetch_one("""
            SELECT
                COALESCE(SUM(amount), 0) as total_revenue,
                COUNT(*) as total_transactions,
                COUNT(DISTINCT source) as revenue_sources,
                COALESCE(AVG(amount), 0) as avg_transaction
            FROM revenue_records
            WHERE status IN ('received', 'verified')
        """)
        return dict(row) if row else {}

    # ─── Activity Log ──────────────────────────────────────────────────────

    async def log_activity(
        self,
        activity_type: str,
        action: str,
        description: str = "",
        metadata: Optional[dict] = None,
        severity: str = "info",
    ) -> int:
        """Log an activity entry."""
        import json
        return await db_connection.insert(
            """INSERT INTO activity_log (type, action, description, metadata, severity)
               VALUES (?, ?, ?, ?, ?)""",
            (activity_type, action, description, json.dumps(metadata or {}), severity),
        )

    async def get_recent_activity(self, limit: int = 50) -> list[dict]:
        """Get the most recent activity log entries."""
        return await db_connection.fetch_all(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
