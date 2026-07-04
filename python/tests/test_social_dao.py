"""
Tests for SocialDAO - trends, scripts, videos, and posts CRUD.
"""

import json
import pytest
from database import social_dao


@pytest.mark.asyncio
async def test_trend_crud():
    """Test creating and retrieving trends."""
    trend_id = await social_dao.insert_trend({
        "title": "AI in 2025",
        "source": "reddit",
        "subreddit": "artificial",
        "url": "https://reddit.com/r/artificial/trend",
        "score": 95.0,
        "engagement": 1500,
        "niche": "technology",
    })
    assert trend_id > 0

    trend = await social_dao.get_trend(trend_id)
    assert trend is not None
    assert trend["title"] == "AI in 2025"
    assert trend["source"] == "reddit"


@pytest.mark.asyncio
async def test_get_recent_trends():
    """Test retrieving recent trends filtered by niche."""
    await social_dao.insert_trend({"title": "Trend 1", "source": "reddit", "score": 90.0, "niche": "technology"})
    await social_dao.insert_trend({"title": "Trend 2", "source": "news", "score": 80.0, "niche": "technology"})
    await social_dao.insert_trend({"title": "Gaming Trend", "source": "reddit", "score": 70.0, "niche": "gaming"})

    tech_trends = await social_dao.get_recent_trends(limit=10, niche="technology")
    assert len(tech_trends) >= 2
    assert all(t["niche"] == "technology" for t in tech_trends)

    all_trends = await social_dao.get_recent_trends(limit=10)
    assert len(all_trends) >= 3


@pytest.mark.asyncio
async def test_script_lifecycle():
    """Test full script lifecycle: create -> update status."""
    script_id = await social_dao.insert_script({
        "title": "Test Script",
        "topic": "AI Tools",
        "format": "youtube_shorts",
        "script_content": "Sample script content",
    })
    assert script_id > 0

    script = await social_dao.get_script(script_id)
    assert script["status"] == "draft"

    await social_dao.update_script_status(script_id, "finalized")
    script = await social_dao.get_script(script_id)
    assert script["status"] == "finalized"


@pytest.mark.asyncio
async def test_video_workflow():
    """Test video creation and status updates."""
    script_id = await social_dao.insert_script({"title": "Video Script", "topic": "Test", "script_content": "Content"})

    video_id = await social_dao.insert_video({
        "script_id": script_id,
        "title": "Test Video",
        "file_path": "/tmp/test.mp4",
        "status": "rendering",
    })
    assert video_id > 0

    video = await social_dao.get_video(video_id)
    assert video is not None
    assert video["title"] == "Test Video"
    assert video["script_title"] == "Video Script"

    await social_dao.update_video_status(video_id, "completed", file_size_bytes=1024000)
    video = await social_dao.get_video(video_id)
    assert video["status"] == "completed"
    assert video["file_size_bytes"] == 1024000


@pytest.mark.asyncio
async def test_post_recording():
    """Test creating and querying posts."""
    script_id = await social_dao.insert_script({"title": "Post Script", "topic": "Test", "script_content": "Content"})
    video_id = await social_dao.insert_video({"script_id": script_id, "title": "Post Video", "file_path": "/tmp/v.mp4"})

    post_id = await social_dao.insert_post({
        "video_id": video_id,
        "platform": "youtube",
        "title": "My Post",
        "status": "queued",
    })
    assert post_id > 0

    post = await social_dao.get_post(post_id)
    assert post is not None
    assert post["platform"] == "youtube"
    assert post["video_title"] == "Post Video"

    await social_dao.update_post_status(post_id, "posted", platform_post_id="yt-123")
    post = await social_dao.get_post(post_id)
    assert post["status"] == "posted"
    assert post["platform_post_id"] == "yt-123"


@pytest.mark.asyncio
async def test_pipeline_counts():
    """Test pipeline stage counts."""
    counts = await social_dao.get_pipeline_counts()
    assert isinstance(counts, dict)
    for key in ("scripts_draft", "scripts_finalized", "videos_rendering", "videos_ready", "posts_queued", "posts_posted"):
        assert key in counts


@pytest.mark.asyncio
async def test_update_post_metrics():
    """Test updating engagement metrics on a post."""
    script_id = await social_dao.insert_script({"title": "Metrics Script", "topic": "Test", "script_content": "Content"})
    video_id = await social_dao.insert_video({"script_id": script_id, "title": "Metrics Vid", "file_path": "/tmp/v.mp4"})
    post_id = await social_dao.insert_post({"video_id": video_id, "platform": "tiktok", "title": "Metrics Post"})

    await social_dao.update_post_metrics(post_id, {"views": 1000, "likes": 200, "shares": 50})

    # Read raw from DB to verify JSON was stored
    from database.connection import db_connection
    post = await db_connection.fetch_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    metrics = json.loads(post["engagement_metrics"])
    assert metrics["views"] == 1000
    assert metrics["likes"] == 200


@pytest.mark.asyncio
async def test_get_scripts_by_status():
    """Test filtering scripts by status."""
    await social_dao.insert_script({"title": "S1", "topic": "T1", "script_content": "C", "status": "draft"})
    await social_dao.insert_script({"title": "S2", "topic": "T2", "script_content": "C", "status": "finalized"})
    await social_dao.insert_script({"title": "S3", "topic": "T3", "script_content": "C", "status": "draft"})

    drafts = await social_dao.get_scripts_by_status("draft")
    assert len(drafts) >= 2
    assert all(s["status"] == "draft" for s in drafts)


@pytest.mark.asyncio
async def test_get_nonexistent():
    """Test that getting non-existent records returns None."""
    assert await social_dao.get_trend(99999) is None
    assert await social_dao.get_script(99999) is None
    assert await social_dao.get_video(99999) is None
    assert await social_dao.get_post(99999) is None
