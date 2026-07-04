"""
Multi-platform content poster - queues and posts to YouTube, TikTok, Instagram, Twitter.
"""

from typing import Any
from datetime import datetime, timezone

from config import get_settings


PLATFORMS = ["youtube", "tiktok", "instagram", "twitter"]


class ContentPoster:
    """Posts content to multiple social platforms using official APIs."""

    def __init__(self):
        self.settings = get_settings()

    async def post(
        self,
        video_path: str,
        title: str,
        description: str,
        platforms: list[str] | None = None,
        schedule_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Post a video to specified platforms.

        Args:
            video_path: Path to the rendered video file
            title: Video title
            description: Video description/caption
            platforms: List of platforms to post to (default: all)
            schedule_time: Optional scheduled post time

        Returns:
            Dict with posting results per platform
        """
        targets = platforms or PLATFORMS
        results = {}

        for platform in targets:
            try:
                if platform == "youtube":
                    result = await self._post_to_youtube(video_path, title, description)
                elif platform == "tiktok":
                    result = await self._post_to_tiktok(video_path, title, description)
                elif platform == "instagram":
                    result = await self._post_to_instagram(video_path, title, description)
                elif platform == "twitter":
                    result = await self._post_to_twitter(video_path, title, description)
                else:
                    result = {"status": "error", "error": f"Unknown platform: {platform}"}

                results[platform] = result
                print(f"[Poster] Posted to {platform}: {result.get('status')}")

            except Exception as e:
                results[platform] = {"status": "error", "error": str(e)}
                print(f"[Poster] Failed to post to {platform}: {e}")

        return {
            "video_path": video_path,
            "title": title,
            "results": results,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _post_to_youtube(
        self, video_path: str, title: str, description: str
    ) -> dict[str, Any]:
        """Upload video to YouTube using YouTube Data API v3."""
        api_key = self.settings.youtube_api_key
        if not api_key:
            return {"status": "error", "error": "YouTube API key not configured"}

        # YouTube upload implementation
        # Uses google-api-python-client for OAuth2 and upload
        # Placeholder for now - requires OAuth2 flow
        return {
            "status": "simulated",
            "platform": "youtube",
            "message": "YouTube upload requires OAuth2 authentication flow",
        }

    async def _post_to_tiktok(
        self, video_path: str, title: str, description: str
    ) -> dict[str, Any]:
        """Upload video to TikTok."""
        access_token = getattr(self.settings, "tiktok_access_token", "")
        if not access_token:
            return {"status": "error", "error": "TikTok access token not configured"}

        # TikTok upload implementation
        return {
            "status": "simulated",
            "platform": "tiktok",
            "message": "TikTok upload requires OAuth2 authentication flow",
        }

    async def _post_to_instagram(
        self, video_path: str, title: str, description: str
    ) -> dict[str, Any]:
        """Upload video to Instagram (as Reel)."""
        access_token = getattr(self.settings, "instagram_access_token", "")
        if not access_token:
            return {"status": "error", "error": "Instagram access token not configured"}

        # Instagram upload implementation
        return {
            "status": "simulated",
            "platform": "instagram",
            "message": "Instagram Reel upload requires OAuth2 authentication flow",
        }

    async def _post_to_twitter(
        self, video_path: str, title: str, description: str
    ) -> dict[str, Any]:
        """Post video to Twitter/X."""
        api_key = self.settings.twitter_api_key
        if not api_key:
            return {"status": "error", "error": "Twitter API key not configured"}

        # Twitter upload implementation
        return {
            "status": "simulated",
            "platform": "twitter",
            "message": "Twitter upload requires OAuth1a authentication flow",
        }

    async def get_platform_status(self) -> dict[str, bool]:
        """Check which platforms are configured and ready."""
        return {
            "youtube": bool(self.settings.youtube_api_key),
            "tiktok": bool(getattr(self.settings, "tiktok_access_token", "")),
            "instagram": bool(getattr(self.settings, "instagram_access_token", "")),
            "twitter": bool(self.settings.twitter_api_key),
        }
