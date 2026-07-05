"""
Tests for ContentCalendar — calendar views, scheduling, and stats.
"""

import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from database import social_dao

# ─── Fixture: patch social_dao for isolated calendar tests ─────────────────

@pytest.fixture
def calendar():
    """Import ContentCalendar for testing."""
    from social.calendar import ContentCalendar
    return ContentCalendar()


# ─── get_calendar_month ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_month_empty(calendar):
    """get_calendar_month should return empty days for a month with no activity."""
    result = await calendar.get_calendar_month(2026, 7)

    assert result["year"] == 2026
    assert result["month"] == 7
    assert isinstance(result["days"], dict)
    assert result["total_scheduled"] == 0
    assert result["total_posted"] == 0


@pytest.mark.asyncio
async def test_calendar_month_with_scheduled(calendar):
    """get_calendar_month should include scheduled posts."""
    # Create prerequisites: script -> video -> scheduled post
    script_id = await social_dao.insert_script({
        "title": "Cal Script", "topic": "Test", "script_content": "Content",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Cal Video", "file_path": "/tmp/v.mp4",
    })
    await social_dao.insert_post({
        "video_id": video_id, "platform": "youtube", "title": "Scheduled Post",
        "status": "scheduled", "scheduled_at": "2026-07-15T10:00:00",
    })

    result = await calendar.get_calendar_month(2026, 7)

    assert result["total_scheduled"] == 1
    assert "2026-07-15" in result["days"]
    assert len(result["days"]["2026-07-15"]) == 1
    assert result["days"]["2026-07-15"][0]["type"] == "scheduled"


@pytest.mark.asyncio
async def test_calendar_month_with_posted(calendar):
    """get_calendar_month should include posted content."""
    script_id = await social_dao.insert_script({
        "title": "Posted Script", "topic": "Test", "script_content": "Content",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Posted Vid", "file_path": "/tmp/v.mp4",
    })
    await social_dao.insert_post({
        "video_id": video_id, "platform": "twitter", "title": "Posted Tweet",
        "status": "posted", "scheduled_at": "2026-07-20T14:00:00",
    })

    # Update the post status to 'posted' which also sets posted_at
    await social_dao.update_post_status(
        (await social_dao.get_posts_by_platform("twitter"))[0]["id"],
        "posted",
        platform_post_id="tw-456",
    )

    result = await calendar.get_calendar_month(2026, 7)

    assert result["total_posted"] >= 1


@pytest.mark.asyncio
async def test_calendar_month_year_boundary(calendar):
    """get_calendar_month should handle December->January transition."""
    # No error for December
    result_dec = await calendar.get_calendar_month(2026, 12)
    assert result_dec["year"] == 2026
    assert result_dec["month"] == 12

    # No error for January
    result_jan = await calendar.get_calendar_month(2027, 1)
    assert result_jan["year"] == 2027
    assert result_jan["month"] == 1


# ─── get_calendar_week ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_week_empty(calendar):
    """get_calendar_week should return 7 empty days for a week with no activity."""
    start = "2026-07-13"  # Monday
    result = await calendar.get_calendar_week(start)

    assert result["week_start"] == start
    assert len(result["days"]) == 7
    assert result["total_scheduled"] == 0
    assert result["total_posted"] == 0


@pytest.mark.asyncio
async def test_calendar_week_with_scheduled(calendar):
    """get_calendar_week should include scheduled posts within the week."""
    script_id = await social_dao.insert_script({
        "title": "Week Script", "topic": "Test", "script_content": "Content",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Week Vid", "file_path": "/tmp/v.mp4",
    })
    await social_dao.insert_post({
        "video_id": video_id, "platform": "youtube", "title": "Midweek Post",
        "status": "scheduled", "scheduled_at": "2026-07-15T12:00:00",
    })

    result = await calendar.get_calendar_week("2026-07-13")

    assert result["total_scheduled"] == 1
    assert "2026-07-15" in result["days"]
    assert result["days"]["2026-07-15"][0]["type"] == "scheduled"


# ─── schedule_post ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_post(calendar):
    """schedule_post should create posts for each platform."""
    script_id = await social_dao.insert_script({
        "title": "Schedule Script", "topic": "Test", "script_content": "Content",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Schedule Vid", "file_path": "/tmp/v.mp4",
    })

    result = await calendar.schedule_post(
        video_id=video_id,
        platforms=["youtube", "tiktok"],
        scheduled_date="2026-08-01T09:00:00",
        title="Scheduled Content",
        description="Auto-generated",
    )

    assert result["status"] == "scheduled"
    assert result["video_id"] == video_id
    assert len(result["platforms"]) == 2
    assert result["platforms"][0]["platform"] == "youtube"
    assert result["platforms"][1]["platform"] == "tiktok"
    assert result["platforms"][0]["post_id"] > 0
    assert result["platforms"][1]["post_id"] > 0


@pytest.mark.asyncio
async def test_schedule_post_defaults(calendar):
    """schedule_post should use defaults for omitted title/description."""
    script_id = await social_dao.insert_script({
        "title": "Default Script", "topic": "Test", "script_content": "Content",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Default Vid", "file_path": "/tmp/v.mp4",
    })

    result = await calendar.schedule_post(
        video_id=video_id,
        platforms=["twitter"],
        scheduled_date="2026-08-15",
    )

    assert result["status"] == "scheduled"
    assert result["platforms"][0]["post_id"] > 0

    # Verify the post was stored with default title
    post = await social_dao.get_post(result["platforms"][0]["post_id"])
    assert post is not None
    assert post["title"] == "Scheduled Content"  # Default title
    assert post["status"] == "scheduled"
    assert post["scheduled_at"] is not None


# ─── cancel_scheduled_post ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_scheduled_post(calendar):
    """cancel_scheduled_post should set status to queued with cancellation note."""
    script_id = await social_dao.insert_script({
        "title": "Cancel Script", "topic": "Test", "script_content": "Content",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Cancel Vid", "file_path": "/tmp/v.mp4",
    })
    post_id = await social_dao.insert_post({
        "video_id": video_id, "platform": "youtube", "title": "To Cancel",
        "status": "scheduled", "scheduled_at": "2026-09-01T12:00:00",
    })

    result = await calendar.cancel_scheduled_post(post_id)
    assert result is True

    post = await social_dao.get_post(post_id)
    assert post is not None
    assert post["status"] == "queued"


@pytest.mark.asyncio
async def test_cancel_non_existent_post(calendar):
    """cancel_scheduled_post on non-existent id should not raise."""
    # Should not raise an exception — update_post_status returns rowcount 0
    result = await calendar.cancel_scheduled_post(99999)
    assert result is True  # Method always returns True


# ─── get_upcoming_schedule ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_upcoming_schedule_empty(calendar):
    """get_upcoming_schedule should return empty list if nothing scheduled."""
    result = await calendar.get_upcoming_schedule(days=14)
    assert isinstance(result, list)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_upcoming_schedule_with_posts(calendar):
    """get_upcoming_schedule should return future scheduled posts."""
    script_id = await social_dao.insert_script({
        "title": "Upcoming Script", "topic": "Test", "script_content": "Content",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Upcoming Vid", "file_path": "/tmp/v.mp4",
    })

    # Schedule for 3 days from now
    future_date = (date.today() + timedelta(days=3)).isoformat()
    await social_dao.insert_post({
        "video_id": video_id, "platform": "youtube", "title": "Future Post",
        "status": "scheduled", "scheduled_at": f"{future_date}T10:00:00",
    })
    # Post far in the future (outside default 14-day window if days=7)
    far_future = (date.today() + timedelta(days=30)).isoformat()
    await social_dao.insert_post({
        "video_id": video_id, "platform": "twitter", "title": "Far Future",
        "status": "scheduled", "scheduled_at": f"{far_future}T10:00:00",
    })

    result = await calendar.get_upcoming_schedule(days=14)

    assert len(result) >= 1  # At least the one within 14 days

    # With days=7, only the first post should be included
    result_7 = await calendar.get_upcoming_schedule(days=7)
    assert len(result_7) == 1


# ─── get_calendar_stats ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_calendar_stats_empty(calendar):
    """get_calendar_stats should return zero counts when nothing exists."""
    stats = await calendar.get_calendar_stats()

    assert stats["total_scheduled"] == 0
    assert stats["total_posted"] == 0
    assert stats["scheduled_this_month"] == 0
    assert stats["platform_distribution"] == {}
    assert stats["videos_ready"] == 0
    assert stats["scripts_draft"] == 0


@pytest.mark.asyncio
async def test_get_calendar_stats_with_data(calendar):
    """get_calendar_stats should reflect actual counts."""
    # Create a script (draft)
    script_id = await social_dao.insert_script({
        "title": "Stats Script", "topic": "Test", "script_content": "Content",
    })

    # Create a completed video
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": "Stats Vid",
        "file_path": "/tmp/v.mp4", "status": "completed",
    })

    # Schedule a post for this month
    today = date.today()
    this_month = f"{today.year}-{today.month:02d}"
    await social_dao.insert_post({
        "video_id": video_id, "platform": "youtube", "title": "Month Post",
        "status": "scheduled",
        "scheduled_at": f"{this_month}-15T12:00:00",
    })
    await social_dao.insert_post({
        "video_id": video_id, "platform": "tiktok", "title": "Month Post 2",
        "status": "scheduled",
        "scheduled_at": f"{this_month}-20T12:00:00",
    })

    stats = await calendar.get_calendar_stats()

    assert stats["scripts_draft"] >= 1
    assert stats["videos_ready"] >= 1
    assert stats["scheduled_this_month"] >= 2
    assert len(stats["platform_distribution"]) >= 2
    assert stats["platform_distribution"].get("youtube", 0) >= 1
    assert stats["platform_distribution"].get("tiktok", 0) >= 1


# ─── Edge Cases ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_month_leap_year(calendar):
    """get_calendar_month should handle February in a leap year."""
    result = await calendar.get_calendar_month(2024, 2)  # 2024 is a leap year
    assert result["year"] == 2024
    assert result["month"] == 2
    # Verify no crash — 29 days in Feb 2024 expected
    assert isinstance(result["days"], dict)
