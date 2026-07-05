"""
Content Calendar — schedule, view, and manage social media posting schedules.
Provides weekly/monthly calendar views and scheduling endpoints.
"""

from datetime import datetime, timedelta, date, timezone
from typing import Any, Optional

from database import social_dao


class ContentCalendar:
    """Manages content scheduling and provides calendar views."""

    async def get_calendar_month(
        self,
        year: int,
        month: int,
    ) -> dict[str, Any]:
        """
        Get a calendar overview for a given month.

        Returns:
            Dict with days of the month, each containing scheduled/queued posts.
        """
        # Calculate month range
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        # Get all scheduled/queued posts in this range
        scheduled = await social_dao.get_scheduled_posts(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        # Get all posted content for history
        posted = await social_dao.get_posts_by_status("posted", limit=200)

        # Group by date
        days: dict[str, list[dict[str, Any]]] = {}
        for post in scheduled:
            dt = post.get("scheduled_at", "")[:10] or post.get("created_at", "")[:10]
            if dt:
                days.setdefault(dt, []).append({**post, "type": "scheduled"})

        for post in posted:
            dt = post.get("posted_at", "")[:10] or post.get("created_at", "")[:10]
            if dt:
                days.setdefault(dt, []).append({**post, "type": "posted"})

        return {
            "year": year,
            "month": month,
            "days": days,
            "total_scheduled": len(scheduled),
            "total_posted": len(posted),
        }

    async def get_calendar_week(self, start: str) -> dict[str, Any]:
        """
        Get a calendar overview for a week starting from the given date.
        """
        start_dt = datetime.fromisoformat(start).date()
        end_dt = start_dt + timedelta(days=7)

        scheduled = await social_dao.get_scheduled_posts(
            start_date=start_dt.isoformat(),
            end_date=end_dt.isoformat(),
        )
        posted = await social_dao.get_posts_by_status("posted", limit=100)

        days: dict[str, list[dict[str, Any]]] = {}
        for i in range(7):
            day = start_dt + timedelta(days=i)
            days[day.isoformat()] = []

        for post in scheduled:
            dt = post.get("scheduled_at", "")[:10] or post.get("created_at", "")[:10]
            if dt in days:
                days[dt].append({**post, "type": "scheduled"})

        for post in posted:
            dt = post.get("posted_at", "")[:10] or post.get("created_at", "")[:10]
            if dt in days:
                days[dt].append({**post, "type": "posted"})

        return {
            "week_start": start_dt.isoformat(),
            "week_end": end_dt.isoformat(),
            "days": days,
            "total_scheduled": len(scheduled),
            "total_posted": len(posted),
        }

    async def schedule_post(
        self,
        video_id: int,
        platforms: list[str],
        scheduled_date: str,
        title: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """
        Schedule a video for posting on multiple platforms at a future date.

        Args:
            video_id: ID of the rendered video
            platforms: List of platforms to post to
            scheduled_date: ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            title: Optional title override
            description: Optional description

        Returns:
            Dict with scheduled post IDs per platform
        """
        results = []
        for platform in platforms:
            post_id = await social_dao.insert_post({
                "video_id": video_id,
                "platform": platform,
                "title": title or "Scheduled Content",
                "description": description or "",
                "status": "scheduled",
                "scheduled_at": scheduled_date,
            })
            results.append({
                "platform": platform,
                "post_id": post_id,
            })

        return {
            "video_id": video_id,
            "scheduled_date": scheduled_date,
            "platforms": results,
            "status": "scheduled",
        }

    async def cancel_scheduled_post(self, post_id: int) -> bool:
        """Cancel a scheduled post."""
        await social_dao.update_post_status(post_id, "queued", error_message="Cancelled by user")
        return True

    async def get_upcoming_schedule(self, days: int = 14) -> list[dict[str, Any]]:
        """Get all scheduled posts for the next N days."""
        today = date.today()
        end = today + timedelta(days=days)

        scheduled = await social_dao.get_scheduled_posts(
            start_date=today.isoformat(),
            end_date=end.isoformat(),
        )

        # Enrich with video and script details
        enriched = []
        for post in scheduled:
            try:
                full = await social_dao.get_post(post["id"])
                enriched.append(full or post)
            except Exception:
                enriched.append(post)

        return enriched

    async def get_calendar_stats(self) -> dict[str, Any]:
        """Get calendar statistics."""
        today = date.today()
        month_start = date(today.year, today.month, 1)

        counts = await social_dao.get_pipeline_counts()

        # Scheduled this month
        if today.month == 12:
            month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

        this_month = await social_dao.get_scheduled_posts(
            start_date=month_start.isoformat(),
            end_date=month_end.isoformat(),
        )

        # Platform distribution
        platform_dist: dict[str, int] = {}
        for post in this_month:
            plat = post.get("platform", "unknown")
            platform_dist[plat] = platform_dist.get(plat, 0) + 1

        return {
            "total_scheduled": counts.get("posts_queued", 0),
            "total_posted": counts.get("posts_posted", 0),
            "scheduled_this_month": len(this_month),
            "platform_distribution": platform_dist,
            "videos_ready": counts.get("videos_ready", 0),
            "scripts_draft": counts.get("scripts_draft", 0),
        }
