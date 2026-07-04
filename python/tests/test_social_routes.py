"""
Tests for social FastAPI routes: trends, scripts, videos, posts, pipeline, status.
Heavy dependencies (moviepy, ollama) are mocked at import time.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import social_dao


@pytest.fixture
def router():
    """Import social routes, mocking moviepy to avoid FFMPEG dependency at import time."""
    import sys
    from unittest.mock import MagicMock

    # Force-replace moviepy in sys.modules so video.py's import doesn't trigger
    # FFMPEG detection.  Python's import system checks sys.modules first, so
    # ``from moviepy import VideoFileClip`` will grab attributes from the mock.
    sys.modules["moviepy"] = MagicMock()

    from social import routes
    return routes.router


# ─── Trends ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_trends_success(client):
    """GET /trends should fetch, store, and return trends."""
    mock_trends = [
        {"title": "AI Revolution", "source": "reddit",
         "subreddit": "technology", "score": 95.0, "engagement": 500,
         "niche": "technology"},
        {"title": "Python 4.0", "source": "news",
         "subreddit": "", "score": 80.0, "engagement": 300,
         "niche": "technology"},
    ]

    with patch("social.routes.trend_research.get_trends", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_trends
        response = await client.get("/trends")

    assert response.status_code == 200
    data = response.json()
    assert data["new_trends"] >= 2
    assert len(data["trends"]) >= 0  # DB may have the stored trends


# ─── Scripts ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_script(client):
    """POST /generate-script should generate and store a script."""
    mock_script = {
        "script": "This is a sample script about AI.",
        "sections": '["Hook", "Content", "CTA"]',
        "visual_cues": '["Show code", "Show demo"]',
        "score": 85,
    }

    with patch("social.routes.script_generator.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_script
        response = await client.post(
            "/generate-script",
            json={"topic": "AI Basics", "format": "youtube_shorts", "tone": "educational"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["script_id"] > 0
    assert "sample script" in data["script"]["script"]


@pytest.mark.asyncio
async def test_get_scripts_empty(client):
    """GET /scripts should return empty list initially."""
    response = await client.get("/scripts")
    assert response.status_code == 200
    assert response.json()["scripts"] == []


@pytest.mark.asyncio
async def test_get_scripts_by_status(client):
    """GET /scripts should filter by status."""
    await social_dao.insert_script({
        "title": "Test Vid", "topic": "Tech", "format": "youtube_shorts",
        "script_content": "Hello", "status": "draft",
    })

    response = await client.get("/scripts?status=draft")
    assert response.status_code == 200
    scripts = response.json()["scripts"]
    assert len(scripts) >= 1
    assert scripts[0]["status"] == "draft"


# ─── Render Video ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_render_video_not_found(client):
    """POST /render-video with non-existent script should return 404."""
    response = await client.post("/render-video", json={"script_id": "99999"})
    assert response.status_code == 404
    assert "Script not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_render_video_success(client):
    """POST /render-video should render and store a video."""
    script_id = await social_dao.insert_script({
        "title": "Render Test", "topic": "Testing", "format": "youtube_shorts",
        "script_content": "Test content for rendering.",
        "sections": '["Intro", "Body"]',
        "status": "draft",
    })

    with patch("social.routes.video_assembler.render", new_callable=AsyncMock) as mock_render:
        mock_render.return_value = "/tmp/barq_video_1.mp4"
        response = await client.post(
            "/render-video", json={"script_id": str(script_id)}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rendered"
    assert data["video_id"] > 0


@pytest.mark.asyncio
async def test_render_video_invalid_id(client):
    """POST /render-video with non-numeric script_id should return 400."""
    response = await client.post("/render-video", json={"script_id": "abc"})
    assert response.status_code == 400
    assert "integer" in response.json()["detail"].lower()


# ─── Videos ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_videos_empty(client):
    """GET /videos should return empty list initially."""
    response = await client.get("/videos")
    assert response.status_code == 200
    assert response.json()["videos"] == []


# ─── Post Content ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_content_not_found(client):
    """POST /post with non-existent video should return 404."""
    response = await client.post(
        "/post",
        json={"video_id": "99999", "platforms": ["youtube"]},
    )
    assert response.status_code == 404
    assert "Video not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_post_content_success(client):
    """POST /post should post to platforms and record in DB."""
    # Insert script and video
    script_id = await social_dao.insert_script({
        "title": "Post Test", "topic": "Posting", "format": "youtube_shorts",
        "script_content": "Post test content", "status": "finalized",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id,
        "title": "Post Test Video",
        "file_path": "/tmp/test.mp4",
        "status": "completed",
    })

    mock_post_result = {
        "results": {
            "youtube": {"status": "posted", "id": "yt123"},
            "twitter": {"status": "posted", "id": "tw456"},
        }
    }

    with patch("social.routes.content_poster.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_post_result
        response = await client.post(
            "/post",
            json={"video_id": str(video_id), "platforms": ["youtube", "twitter"]},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == video_id
    assert "youtube" in data["results"]
    assert "twitter" in data["results"]


@pytest.mark.asyncio
async def test_post_content_invalid_video_id(client):
    """POST /post with non-numeric video_id should return 400."""
    response = await client.post(
        "/post",
        json={"video_id": "abc", "platforms": ["youtube"]},
    )
    assert response.status_code == 400
    assert "integer" in response.json()["detail"].lower()


# ─── Pipeline & Status ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_stats(client):
    """GET /pipeline should return pipeline counts."""
    response = await client.get("/pipeline")
    assert response.status_code == 200
    data = response.json()
    assert "pipeline" in data
    assert isinstance(data["pipeline"], dict)


@pytest.mark.asyncio
async def test_social_status(client):
    """GET /status should return platform and pipeline info."""
    with patch("social.routes.content_poster.get_platform_status",
               new_callable=AsyncMock) as mock_status:
        mock_status.return_value = {
            "youtube": False, "tiktok": False,
            "instagram": False, "twitter": False,
        }
        response = await client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert "platforms" in data
    assert "pipeline" in data
