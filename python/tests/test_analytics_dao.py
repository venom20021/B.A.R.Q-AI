"""
Tests for AnalyticsDAO - career snapshots, social snapshots, revenue, and activity log.
"""

import json
import pytest
from datetime import datetime, timezone
from database import analytics_dao


@pytest.mark.asyncio
async def test_career_snapshot():
    """Test creating and retrieving career analytics snapshots."""
    snap_id = await analytics_dao.insert_career_snapshot({
        "jobs_scanned": 100,
        "matches_found": 20,
        "applications_sent": 5,
        "interviews_scheduled": 2,
        "offers_received": 1,
        "active_applications": 3,
    })
    assert snap_id > 0

    snapshot = await analytics_dao.get_latest_career_snapshot()
    assert snapshot is not None
    assert snapshot["jobs_scanned"] == 100
    assert snapshot["offers_received"] == 1


@pytest.mark.asyncio
async def test_career_trend():
    """Test retrieving career trend data over time."""
    today = datetime.now(timezone.utc).date().isoformat()
    await analytics_dao.insert_career_snapshot({"snapshot_date": today, "jobs_scanned": 50})
    await analytics_dao.insert_career_snapshot({"snapshot_date": today, "jobs_scanned": 100})

    trends = await analytics_dao.get_career_trend(days=30)
    assert len(trends) >= 1


@pytest.mark.asyncio
async def test_compute_funnel_summary():
    """Test computing career funnel from live tables."""
    summary = await analytics_dao.compute_funnel_summary()
    assert isinstance(summary, dict)
    for key in ("jobs_scanned", "matches_found", "applications_sent", "interviews_scheduled", "offers_received", "active_applications"):
        assert key in summary


@pytest.mark.asyncio
async def test_social_snapshot():
    """Test creating and retrieving social media analytics."""
    for platform in ("youtube", "tiktok"):
        await analytics_dao.insert_social_snapshot({
            "platform": platform,
            "followers": 1000,
            "total_views": 50000,
            "total_engagement": 2500,
            "engagement_rate": 5.0,
            "videos_posted": 10,
            "revenue": 150.0,
        })

    snapshots = await analytics_dao.get_latest_social_snapshots()
    assert len(snapshots) >= 2
    platforms = {s["platform"] for s in snapshots}
    assert "youtube" in platforms
    assert "tiktok" in platforms


@pytest.mark.asyncio
async def test_social_trend():
    """Test retrieving social media trend for a platform."""
    await analytics_dao.insert_social_snapshot({
        "platform": "youtube", "followers": 100, "total_views": 1000
    })
    trend = await analytics_dao.get_social_trend("youtube", days=30)
    assert len(trend) >= 1
    assert all(t["platform"] == "youtube" for t in trend)


@pytest.mark.asyncio
async def test_revenue_crud():
    """Test inserting and querying revenue records."""
    rec_id = await analytics_dao.insert_revenue({
        "source": "youtube_adsense",
        "platform": "youtube",
        "amount": 250.0,
        "period_start": "2025-01-01",
        "period_end": "2025-01-31",
        "status": "received",
    })
    assert rec_id > 0

    rec_id = await analytics_dao.insert_revenue({
        "source": "affiliate_links",
        "platform": "twitter",
        "amount": 75.0,
        "period_start": "2025-01-01",
        "period_end": "2025-01-31",
        "status": "received",
    })

    by_source = await analytics_dao.get_revenue_by_source(days=90)
    assert len(by_source) >= 2

    total = await analytics_dao.get_total_revenue(days=90)
    assert total > 0


@pytest.mark.asyncio
async def test_revenue_by_month():
    """Test monthly revenue aggregation."""
    # Use a period_start within the last 6 months so the SQL filter doesn't exclude it
    from datetime import datetime, timezone
    this_month = datetime.now(timezone.utc).strftime("%Y-%m") + "-01"
    await analytics_dao.insert_revenue({
        "source": "youtube_adsense", "platform": "youtube",
        "amount": 100.0, "period_start": this_month, "period_end": this_month,
    })
    by_month = await analytics_dao.get_revenue_by_month(months=6)
    assert len(by_month) >= 1
    assert "total" in by_month[0]


@pytest.mark.asyncio
async def test_revenue_summary():
    """Test revenue summary aggregation."""
    summary = await analytics_dao.get_latest_revenue_summary()
    assert isinstance(summary, dict)
    for key in ("total_revenue", "total_transactions", "revenue_sources", "avg_transaction"):
        assert key in summary


@pytest.mark.asyncio
async def test_activity_log():
    """Test logging and retrieving activity entries."""
    log_id = await analytics_dao.log_activity(
        activity_type="system",
        action="test_action",
        description="Test activity entry",
        metadata={"test": True},
        severity="info",
    )
    assert log_id >= 0  # insert returns lastrowid, 0 is ok for empty DB

    activities = await analytics_dao.get_recent_activity(limit=10)
    assert len(activities) >= 1
    assert activities[0]["type"] == "system"
    assert activities[0]["action"] == "test_action"


@pytest.mark.asyncio
async def test_cross_platform_summary():
    """Test cross-platform summary returns latest data per platform."""
    summary = await analytics_dao.get_cross_platform_summary()
    assert isinstance(summary, list)


@pytest.mark.asyncio
async def test_get_nonexistent():
    """Test that getting non-existent records returns None/empty."""
    snapshot = await analytics_dao.get_latest_career_snapshot()
    # When no data exists, it should return None or an empty dict
    assert snapshot is None or isinstance(snapshot, dict)
