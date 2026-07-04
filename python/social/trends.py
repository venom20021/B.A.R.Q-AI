"""
Trend research pulling from Twitter/X, Reddit, Google Trends, etc.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
import httpx

from config import get_settings


TREND_SOURCES = [
    "twitter",
    "reddit",
    "google_trends",
    "news_api",
]


class TrendResearch:
    """Researches trending topics across multiple platforms."""

    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=15.0)

    async def get_trends(self, niche: str = "technology") -> list[dict[str, Any]]:
        """
        Fetch current trending topics relevant to the specified niche.

        Args:
            niche: Content niche/industry to focus on

        Returns:
            List of trending topics with metadata
        """
        tasks = [self._fetch_source(source, niche) for source in TREND_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        trends = []
        for result in results:
            if isinstance(result, list):
                trends.extend(result)

        # Sort by relevance score and return top trends
        trends.sort(key=lambda x: x.get("score", 0), reverse=True)
        return trends[:20]

    async def _fetch_source(self, source: str, niche: str) -> list[dict[str, Any]]:
        """Fetch trends from a specific source."""
        try:
            if source == "reddit":
                return await self._fetch_reddit_trends(niche)
            elif source == "news_api":
                return await self._fetch_news_trends(niche)
            else:
                return await self._fetch_generic_trends(source, niche)
        except Exception as e:
            print(f"[Trends] {source} fetch failed: {e}")
            return []

    async def _fetch_reddit_trends(self, niche: str) -> list[dict[str, Any]]:
        """Fetch trending posts from Reddit."""
        # Using Reddit's public JSON API
        subreddits = {
            "technology": ["technology", "programming", "artificial", "startups"],
            "gaming": ["gaming", "pcgaming"],
            "business": ["business", "entrepreneur"],
        }

        subs = subreddits.get(niche.lower(), ["all"])
        trends = []

        for sub in subs:
            url = f"https://www.reddit.com/r/{sub}/hot.json"
            response = await self.client.get(
                url,
                headers={"User-Agent": "BARQ/1.0"},
                params={"limit": 25},
            )
            response.raise_for_status()
            data = response.json()

            for post in data.get("data", {}).get("children", [])[:10]:
                post_data = post.get("data", {})
                trends.append({
                    "title": post_data.get("title", ""),
                    "source": "reddit",
                    "subreddit": sub,
                    "url": f"https://reddit.com{post_data.get('permalink', '')}",
                    "score": post_data.get("score", 0) / 100,
                    "engagement": post_data.get("num_comments", 0),
                    "timestamp": datetime.fromtimestamp(
                        post_data.get("created_utc", 0), tz=timezone.utc
                    ).isoformat(),
                })

        return trends

    async def _fetch_news_trends(self, niche: str) -> list[dict[str, Any]]:
        """Fetch trending news articles."""
        # Using NewsAPI (requires free API key)
        api_key = self.settings.__dict__.get("news_api_key", "")
        if not api_key:
            return []

        url = "https://newsapi.org/v2/everything"
        response = await self.client.get(
            url,
            params={
                "q": niche,
                "sortBy": "popularity",
                "pageSize": 20,
                "apiKey": api_key,
            },
        )
        response.raise_for_status()
        data = response.json()

        return [
            {
                "title": article.get("title", ""),
                "source": "news",
                "url": article.get("url", ""),
                "score": 5.0 - (i * 0.25),
                "engagement": 0,
                "timestamp": article.get("publishedAt", ""),
            }
            for i, article in enumerate(data.get("articles", [])[:10])
        ]

    async def _fetch_generic_trends(self, source: str, niche: str) -> list[dict[str, Any]]:
        """Generic trend fetcher for sources without specific APIs."""
        # Placeholder - would implement Twitter/X API, Google Trends, etc.
        return []

    async def close(self):
        await self.client.aclose()
