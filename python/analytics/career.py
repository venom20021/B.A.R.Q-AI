"""
Career analytics - tracks the funnel from jobs scanned to interviews and offers.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
import json

from config import get_settings


class CareerAnalytics:
    """Tracks and reports career search analytics."""

    def __init__(self):
        self.settings = get_settings()

    async def get_funnel_data(
        self, days: int = 30
    ) -> dict[str, Any]:
        """
        Get the career search funnel metrics.

        Args:
            days: Number of days of data to include

        Returns:
            Funnel metrics with counts at each stage
        """
        # In production, this would query the database
        return {
            "period_days": days,
            "funnel": {
                "jobs_scanned": 1247,
                "matches_found": 89,
                "applications_sent": 23,
                "interviews_scheduled": 5,
                "offers_received": 2,
            },
            "conversion_rates": {
                "scan_to_match": 7.1,  # percentage
                "match_to_apply": 25.8,
                "apply_to_interview": 21.7,
                "interview_to_offer": 40.0,
            },
            "top_sources": [
                {"source": "LinkedIn", "count": 45},
                {"source": "Indeed", "count": 32},
                {"source": "Glassdoor", "count": 12},
            ],
            "daily_trend": self._generate_daily_trend(days),
        }

    async def get_stats(self) -> dict[str, Any]:
        """Get summary career statistics."""
        return {
            "total_jobs_scanned": 1247,
            "active_applications": 5,
            "interview_rate": "21.7%",
            "offer_rate": "8.7%",
            "avg_response_time_days": 4.2,
            "top_skill_demand": ["React", "TypeScript", "Python", "AWS"],
        }

    def _generate_daily_trend(self, days: int) -> list[dict[str, Any]]:
        """Generate sample daily trend data."""
        trend = []
        base_date = datetime.now(timezone.utc) - timedelta(days=days)

        for i in range(days):
            current_date = base_date + timedelta(days=i)
            trend.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "jobs_scanned": 15 + int(i * 1.5),
                "applications": max(0, int(i * 0.3)),
            })

        return trend
