"""
Tests for social FastAPI routes: trends, scripts, videos, posts, pipeline, status.
Heavy dependencies (moviepy, ollama) are mocked at import time.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import social_dao

# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_script_and_video(title: str = "Test") -> tuple[int, int]:
    """Create a script + video pair and return (script_id, video_id)."""
    script_id = await social_dao.insert_script({
        "title": title, "topic": "Test", "format": "youtube_shorts",
        "script_content": "Test content", "status": "finalized",
    })
    video_id = await social_dao.insert_video({
        "script_id": script_id, "title": f"{title} Video",
        "file_path": "/tmp/test.mp4", "status": "completed",
    })
    return script_id, video_id


@pytest.fixture
def router():
    """Import social routes, mocking moviepy to avoid FFMPEG dependency at import time."""
    import sys

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
    """POST /generate-script should generate, quality-gate, and store a script."""
    mock_script = {
        "script": "This is a sample script about AI.",
        "sections": '["Hook", "Content", "CTA"]',
        "visual_cues": '["Show code", "Show demo"]',
        "score": 85,
    }
    gate_result = {
        "final_draft": "This is a sample script about AI.",
        "passed": True,
        "final_score": 88.0,
        "iterations": 1,
        "history": [],
        "revised": False,
    }

    with patch("social.routes.script_generator.generate", new_callable=AsyncMock) as mock_gen, \
         patch("agent.workflows.content_critic.ContentCritic") as mock_critic_cls:
        mock_gen.return_value = mock_script
        mock_critic_cls.return_value.critique_and_improve = AsyncMock(return_value=gate_result)
        response = await client.post(
            "/generate-script",
            json={"topic": "AI Basics", "format": "youtube_shorts", "tone": "educational"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["script_id"] > 0
    assert "sample script" in data["script"]["script"]
    assert data["quality_gate"]["passed"] is True
    assert data["quality_gate"]["final_score"] == 88.0

    # The gate verdict is persisted so the UI can show it after refresh
    stored = await social_dao.get_script(data["script_id"])
    assert stored["score"] == 88.0
    assert stored["revised"] == 0
    assert stored["gate_iterations"] == 1


@pytest.mark.asyncio
async def test_generate_script_critic_revises_draft(client):
    """A below-threshold draft should be revised by the critic before storage."""
    original = "Original weak draft that rambles without a hook or a clear call to action."
    revised = "Revised strong draft that hooks immediately, stays on topic, and ends with a clear CTA."
    mock_script = {
        "script": original,
        "sections": '["Hook", "Content", "CTA"]',
        "visual_cues": "[]",
        "score": 0,
    }
    gate_result = {
        "final_draft": revised,
        "passed": False,
        "final_score": 72.0,
        "iterations": 2,
        "history": [],
        "revised": True,
    }

    with patch("social.routes.script_generator.generate", new_callable=AsyncMock) as mock_gen, \
         patch("agent.workflows.content_critic.ContentCritic") as mock_critic_cls:
        mock_gen.return_value = mock_script
        mock_critic_cls.return_value.critique_and_improve = AsyncMock(return_value=gate_result)
        response = await client.post(
            "/generate-script",
            json={"topic": "AI Basics", "format": "youtube_shorts", "tone": "educational"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["quality_gate"]["passed"] is False
    assert data["quality_gate"]["revised"] is True
    assert data["quality_gate"]["final_score"] == 72.0
    assert data["script"]["script"] == revised

    # The quality-gated draft (not the raw one) is what gets stored
    stored = await social_dao.get_script(data["script_id"])
    assert stored["script_content"] == revised
    assert stored["score"] == 72.0
    assert stored["revised"] == 1
    assert stored["gate_iterations"] == 2

    # GET /scripts surfaces the persisted gate flags for the list UI
    list_resp = await client.get("/scripts?status=draft")
    rows = list_resp.json()["scripts"]
    row = next(r for r in rows if r["id"] == data["script_id"])
    assert row["revised"] == 1
    assert row["gate_iterations"] == 2


@pytest.mark.asyncio
async def test_generate_script_critic_failure_does_not_block(client):
    """Critic failures must never block script generation (best-effort gate)."""
    mock_script = {
        "script": "This is a sample script about AI.",
        "sections": '["Hook", "Content", "CTA"]',
        "visual_cues": "[]",
        "score": 0,
    }

    with patch("social.routes.script_generator.generate", new_callable=AsyncMock) as mock_gen, \
         patch("agent.workflows.content_critic.ContentCritic") as mock_critic_cls:
        mock_gen.return_value = mock_script
        mock_critic_cls.return_value.critique_and_improve = AsyncMock(
            side_effect=RuntimeError("LLM down")
        )
        response = await client.post(
            "/generate-script",
            json={"topic": "AI Basics", "format": "youtube_shorts", "tone": "educational"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["script_id"] > 0
    # Raw draft is still stored, and the gate reports the error
    assert "sample script" in data["script"]["script"]
    assert data["quality_gate"]["passed"] is None
    assert "LLM down" in data["quality_gate"]["error"]

    # No gate verdict means no revision flags on the stored row
    stored = await social_dao.get_script(data["script_id"])
    assert stored["revised"] == 0
    assert stored["gate_iterations"] == 0


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


# ─── Re-run Critic ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rerun_critic_not_found(client):
    """POST /scripts/{id}/re-critic with a non-existent script should return 404."""
    response = await client.post("/scripts/99999/re-critic")
    assert response.status_code == 404
    assert "Script not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rerun_critic_revises_draft(client):
    """Re-running the critic should re-gate a stored draft and persist the verdict."""
    script_id = await social_dao.insert_script({
        "title": "ReCritic Test", "topic": "AI", "format": "youtube_shorts",
        "script_content": "Original draft that rambles without a hook.",
        "status": "draft",
    })
    gate_result = {
        "final_draft": "Tight revised draft with a hook and a clear CTA.",
        "passed": False,
        "final_score": 74.0,
        "iterations": 2,
        "history": [],
        "revised": True,
    }

    with patch("agent.workflows.content_critic.ContentCritic") as mock_critic_cls:
        mock_critic_cls.return_value.critique_and_improve = AsyncMock(return_value=gate_result)
        response = await client.post(f"/scripts/{script_id}/re-critic")

    assert response.status_code == 200
    data = response.json()
    assert data["script_id"] == script_id
    assert data["quality_gate"]["passed"] is False
    assert data["quality_gate"]["revised"] is True
    assert data["quality_gate"]["final_score"] == 74.0
    assert data["revised_draft"] == gate_result["final_draft"]

    # The upgraded draft + verdict are persisted in place (no regeneration)
    stored = await social_dao.get_script(script_id)
    assert stored["script_content"] == gate_result["final_draft"]
    assert stored["score"] == 74.0
    assert stored["revised"] == 1
    assert stored["gate_iterations"] == 2


@pytest.mark.asyncio
async def test_rerun_critic_failure_keeps_draft(client):
    """A critic failure on re-run must not clobber the stored draft."""
    original = "Original draft."
    script_id = await social_dao.insert_script({
        "title": "ReCritic Fail", "topic": "AI", "format": "youtube_shorts",
        "script_content": original,
        "status": "draft",
    })

    with patch("agent.workflows.content_critic.ContentCritic") as mock_critic_cls:
        mock_critic_cls.return_value.critique_and_improve = AsyncMock(
            side_effect=RuntimeError("LLM down")
        )
        response = await client.post(f"/scripts/{script_id}/re-critic")

    assert response.status_code == 200
    data = response.json()
    assert data["quality_gate"]["passed"] is None
    assert "LLM down" in data["quality_gate"]["error"]

    stored = await social_dao.get_script(script_id)
    assert stored["script_content"] == original
    assert stored["revised"] == 0
    assert stored["gate_iterations"] == 0


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
    """GET /pipeline should return pipeline counts including scheduled."""
    response = await client.get("/pipeline")
    assert response.status_code == 200
    data = response.json()
    assert "pipeline" in data
    assert isinstance(data["pipeline"], dict)
    # Should include the new 'posts_scheduled' key
    assert "posts_scheduled" in data["pipeline"]
    assert "scripts_draft" in data["pipeline"]
    assert "videos_ready" in data["pipeline"]


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


# ─── Content Calendar Routes ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calendar_month_default(client):
    """GET /calendar/month with defaults should return current month."""
    response = await client.get("/calendar/month")
    assert response.status_code == 200
    data = response.json()
    assert "year" in data
    assert "month" in data
    assert "days" in data
    assert isinstance(data["days"], dict)


@pytest.mark.asyncio
async def test_calendar_month_specific(client):
    """GET /calendar/month with specific year/month."""
    response = await client.get("/calendar/month?year=2026&month=7")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2026
    assert data["month"] == 7
    assert data["total_scheduled"] == 0
    assert data["total_posted"] == 0


@pytest.mark.asyncio
async def test_calendar_week_default(client):
    """GET /calendar/week with no start should return current week."""
    response = await client.get("/calendar/week")
    assert response.status_code == 200
    data = response.json()
    assert "week_start" in data
    assert "days" in data
    assert len(data["days"]) == 7


@pytest.mark.asyncio
async def test_calendar_week_specific(client):
    """GET /calendar/week with a specific start date."""
    response = await client.get("/calendar/week?start=2026-07-13")
    assert response.status_code == 200
    data = response.json()
    assert data["week_start"] == "2026-07-13"
    assert len(data["days"]) == 7


@pytest.mark.asyncio
async def test_schedule_video(client):
    """POST /calendar/schedule should schedule a video."""
    _, video_id = await _seed_script_and_video("Schedule Route")

    response = await client.post(
        "/calendar/schedule",
        json={
            "video_id": video_id,
            "platforms": ["youtube", "twitter"],
            "scheduled_date": "2026-08-15T14:00:00",
            "title": "Scheduled From Route",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "scheduled"
    assert len(data["platforms"]) == 2
    assert data["platforms"][0]["platform"] == "youtube"
    assert data["platforms"][1]["platform"] == "twitter"


@pytest.mark.asyncio
async def test_cancel_scheduled(client):
    """DELETE /calendar/schedule/{id} should cancel a scheduled post."""
    _, video_id = await _seed_script_and_video("Cancel Route")

    # Schedule
    schedule_resp = await client.post(
        "/calendar/schedule",
        json={
            "video_id": video_id,
            "platforms": ["tiktok"],
            "scheduled_date": "2026-09-01T12:00:00",
        },
    )
    post_id = schedule_resp.json()["platforms"][0]["post_id"]

    # Cancel
    cancel_resp = await client.delete(f"/calendar/schedule/{post_id}")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_upcoming_schedule(client):
    """GET /calendar/upcoming should list future scheduled posts."""
    response = await client.get("/calendar/upcoming?days=14")
    assert response.status_code == 200
    data = response.json()
    assert "upcoming" in data
    assert "total" in data
    assert isinstance(data["upcoming"], list)


@pytest.mark.asyncio
async def test_calendar_stats(client):
    """GET /calendar/stats should return calendar statistics."""
    response = await client.get("/calendar/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_scheduled" in data
    assert "total_posted" in data
    assert "scheduled_this_month" in data
    assert "platform_distribution" in data
    assert "videos_ready" in data
    assert "scripts_draft" in data
