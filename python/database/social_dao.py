"""
Data access layer for social media module.
Handles CRUD for trends, content scripts, videos, and posts.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from .connection import db_connection


class SocialDAO:
    """DAO for social media content operations."""

    # ─── Trends ────────────────────────────────────────────────────────────

    async def insert_trend(self, trend: dict[str, Any]) -> int:
        """Record a trending topic."""
        sql = """
            INSERT INTO trends (title, source, subreddit, url, score, engagement, niche)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            trend.get("title", ""),
            trend.get("source", "manual"),
            trend.get("subreddit", ""),
            trend.get("url", ""),
            trend.get("score", 0.0),
            trend.get("engagement", 0),
            trend.get("niche", "technology"),
        ))

    async def get_recent_trends(self, limit: int = 20, niche: str = "") -> list[dict]:
        """Get the most recent trending topics."""
        if niche:
            return await db_connection.fetch_all(
                "SELECT * FROM trends WHERE niche = ? ORDER BY score DESC, fetched_at DESC LIMIT ?",
                (niche, limit),
            )
        return await db_connection.fetch_all(
            "SELECT * FROM trends ORDER BY score DESC, fetched_at DESC LIMIT ?",
            (limit,),
        )

    async def get_trend(self, trend_id: int) -> Optional[dict]:
        """Get a trend by ID."""
        return await db_connection.fetch_one(
            "SELECT * FROM trends WHERE id = ?", (trend_id,)
        )

    # ─── Content Scripts ───────────────────────────────────────────────────

    async def insert_script(self, script: dict[str, Any]) -> int:
        """Store a generated content script."""
        sql = """
            INSERT INTO content_scripts (
                trend_id, title, topic, format, tone,
                estimated_duration_seconds, script_content, sections,
                visual_cues, status, score, generated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            script.get("trend_id"),
            script.get("title", ""),
            script.get("topic", ""),
            script.get("format", "youtube_shorts"),
            script.get("tone", "professional"),
            script.get("estimated_duration_seconds", 60),
            script.get("script_content", ""),
            script.get("sections", "[]"),
            script.get("visual_cues", "[]"),
            script.get("status", "draft"),
            script.get("score", 0),
            script.get("generated_by", "llm"),
        ))

    async def get_script(self, script_id: int) -> Optional[dict]:
        """Get a script by ID."""
        return await db_connection.fetch_one(
            "SELECT * FROM content_scripts WHERE id = ?", (script_id,)
        )

    async def get_scripts_by_status(self, status: str, limit: int = 50) -> list[dict]:
        """Get scripts filtered by status."""
        return await db_connection.fetch_all(
            "SELECT * FROM content_scripts WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (status, limit),
        )

    async def update_script_status(self, script_id: int, status: str) -> int:
        """Update a script's status."""
        return await db_connection.update(
            "UPDATE content_scripts SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, script_id),
        )

    # ─── Videos ────────────────────────────────────────────────────────────

    async def insert_video(self, video: dict[str, Any]) -> int:
        """Record a rendered video."""
        sql = """
            INSERT INTO videos (
                script_id, title, description, file_path, file_size_bytes,
                duration_seconds, resolution, format, status, error_message,
                voiceover_path, stock_footage_used, render_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            video["script_id"],
            video.get("title", ""),
            video.get("description", ""),
            video.get("file_path", ""),
            video.get("file_size_bytes", 0),
            video.get("duration_seconds", 0.0),
            video.get("resolution", "1080x1920"),
            video.get("format", "mp4"),
            video.get("status", "rendering"),
            video.get("error_message", ""),
            video.get("voiceover_path", ""),
            video.get("stock_footage_used", "[]"),
            video.get("render_time_seconds", 0.0),
        ))

    async def get_video(self, video_id: int) -> Optional[dict]:
        """Get a video by ID with its script."""
        sql = """
            SELECT v.*, cs.title as script_title, cs.topic, cs.format as script_format
            FROM videos v
            JOIN content_scripts cs ON cs.id = v.script_id
            WHERE v.id = ?
        """
        return await db_connection.fetch_one(sql, (video_id,))

    async def get_videos_by_status(self, status: str, limit: int = 50) -> list[dict]:
        """Get videos filtered by rendering status."""
        return await db_connection.fetch_all(
            "SELECT v.*, cs.title as script_title FROM videos v JOIN content_scripts cs ON cs.id = v.script_id WHERE v.status = ? ORDER BY v.updated_at DESC LIMIT ?",
            (status, limit),
        )

    async def update_video_status(
        self, video_id: int, status: str, **kwargs
    ) -> int:
        """Update video status and optional fields."""
        sets = ["status = ?", "updated_at = datetime('now')"]
        params = [status]

        for field, value in kwargs.items():
            if field in ("file_path", "file_size_bytes", "duration_seconds", "error_message", "render_time_seconds"):
                sets.append(f"{field} = ?")
                params.append(value)

        params.append(video_id)
        sql = f"UPDATE videos SET {', '.join(sets)} WHERE id = ?"
        return await db_connection.update(sql, tuple(params))

    # ─── Posts ─────────────────────────────────────────────────────────────

    async def insert_post(self, post: dict[str, Any]) -> int:
        """Record a content post to a platform."""
        sql = """
            INSERT INTO posts (
                video_id, platform, title, description, status,
                scheduled_at, platform_post_id, platform_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            post["video_id"],
            post["platform"],
            post.get("title", ""),
            post.get("description", ""),
            post.get("status", "queued"),
            post.get("scheduled_at"),
            post.get("platform_post_id", ""),
            post.get("platform_url", ""),
        ))

    async def get_post(self, post_id: int) -> Optional[dict]:
        """Get a post by ID with video and script details."""
        sql = """
            SELECT p.*, v.title as video_title, v.file_path, v.duration_seconds,
                   cs.topic, cs.format as script_format
            FROM posts p
            JOIN videos v ON v.id = p.video_id
            JOIN content_scripts cs ON cs.id = v.script_id
            WHERE p.id = ?
        """
        return await db_connection.fetch_one(sql, (post_id,))

    async def get_posts_by_platform(self, platform: str, limit: int = 50) -> list[dict]:
        """Get posts for a specific platform."""
        return await db_connection.fetch_all(
            "SELECT * FROM posts WHERE platform = ? ORDER BY created_at DESC LIMIT ?",
            (platform, limit),
        )

    async def update_post_metrics(self, post_id: int, metrics: dict[str, Any]) -> int:
        """Update engagement metrics for a post."""
        import json
        return await db_connection.update(
            "UPDATE posts SET engagement_metrics = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(metrics), post_id),
        )

    async def update_post_status(self, post_id: int, status: str, **kwargs) -> int:
        """Update post status."""
        sets = ["status = ?", "updated_at = datetime('now')"]
        params = [status]

        if status == "posted":
            sets.append("posted_at = datetime('now')")

        for field, value in kwargs.items():
            if field in ("platform_post_id", "platform_url", "error_message"):
                sets.append(f"{field} = ?")
                params.append(value)

        params.append(post_id)
        sql = f"UPDATE posts SET {', '.join(sets)} WHERE id = ?"
        return await db_connection.update(sql, tuple(params))

    # ─── Pipeline Stats ────────────────────────────────────────────────────

    async def get_pipeline_counts(self) -> dict[str, int]:
        """Get counts for each stage of the content pipeline."""
        rows = await db_connection.fetch_all("""
            SELECT 'scripts_draft' as stage, COUNT(*) as count FROM content_scripts WHERE status = 'draft'
            UNION ALL SELECT 'scripts_finalized', COUNT(*) FROM content_scripts WHERE status = 'finalized'
            UNION ALL SELECT 'videos_rendering', COUNT(*) FROM videos WHERE status = 'rendering'
            UNION ALL SELECT 'videos_ready', COUNT(*) FROM videos WHERE status = 'completed'
            UNION ALL SELECT 'posts_queued', COUNT(*) FROM posts WHERE status = 'queued'
            UNION ALL SELECT 'posts_posted', COUNT(*) FROM posts WHERE status = 'posted'
        """)
        return {row["stage"]: row["count"] for row in rows}
