"""
YouTube Control — search, play, get info, transcript, summarize, trending.

All functions are async and return dicts with 'status' and result data.
Uses no-auth YouTube HTML scraping and youtube-transcript-api for transcripts.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger("barq.youtube")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"  # Filters out Shorts


def _get_api_key() -> Optional[str]:
    """Get Gemini API key from config."""
    try:
        from config import get_settings
        return get_settings().gemini_api_key
    except Exception:
        return None


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    match = re.search(
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url
    )
    return match.group(1) if match else None


def _is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))


def _open_in_browser(url: str) -> dict[str, Any]:
    """Open a URL in the default browser."""
    import platform
    import subprocess

    try:
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
        elif system == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        return {"status": "opened", "url": url}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def youtube_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search YouTube for videos matching a query.

    Args:
        query: Search query string.
        max_results: Max videos to return (default 5).

    Returns:
        Dict with list of {title, url, channel, duration} results.
    """
    try:
        search_url = (
            f"https://www.youtube.com/results"
            f"?search_query={quote_plus(query)}"
            f"&sp={_YT_VIDEO_FILTER}"
        )
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(search_url, timeout=15)
            html = resp.text

        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        titles = re.findall(r'"title":{"runs":\[\{"text":"([^"]+)"', html)
        channels = re.findall(r'"ownerChannelName":"([^"]+)"', html)
        lengths = re.findall(r'"lengthSeconds":"(\d+)"', html)

        results = []
        seen = set()
        for i, vid in enumerate(video_ids):
            if vid in seen:
                continue
            seen.add(vid)
            title = titles[len(seen) - 1] if len(seen) - 1 < len(titles) else ""
            channel = channels[len(seen) - 1] if len(seen) - 1 < len(channels) else ""
            duration_str = ""
            if len(seen) - 1 < len(lengths):
                secs = int(lengths[len(seen) - 1])
                duration_str = f"{secs // 60}:{secs % 60:02d}"

            results.append({
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "video_id": vid,
                "channel": channel,
                "duration": duration_str,
            })
            if len(results) >= max_results:
                break

        return {"status": "ok", "query": query, "count": len(results), "results": results}
    except Exception as e:
        logger.error(f"YouTube search failed: {e}")
        return {"status": "error", "detail": str(e)}


async def youtube_play(query: str) -> dict[str, Any]:
    """Search for a video and open the first non-Shorts result in the browser.

    Args:
        query: What to search for / play.

    Returns:
        Dict with open result.
    """
    try:
        search_url = (
            f"https://www.youtube.com/results"
            f"?search_query={quote_plus(query)}"
            f"&sp={_YT_VIDEO_FILTER}"
        )
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(search_url, timeout=15)
            html = resp.text

        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        for vid in video_ids:
            if f"/shorts/{vid}" in html:
                continue
            video_url = f"https://www.youtube.com/watch?v={vid}"
            _open_in_browser(video_url)
            return {"status": "ok", "url": video_url, "detail": f"Playing: {query}"}

        return {"status": "error", "detail": "No videos found"}
    except Exception as e:
        logger.error(f"YouTube play failed: {e}")
        return {"status": "error", "detail": str(e)}


async def youtube_get_info(url: str) -> dict[str, Any]:
    """Scrape metadata from a YouTube video page.

    Args:
        url: Full YouTube video URL.

    Returns:
        Dict with title, channel, views, duration, likes.
    """
    video_id = _extract_video_id(url)
    if not video_id:
        return {"status": "error", "detail": "Invalid YouTube URL"}

    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(f"https://www.youtube.com/watch?v={video_id}", timeout=15)
            html = resp.text

        info = {"video_id": video_id, "url": url}
        patterns = [
            ("title", r'"title":{"runs":\[\{"text":"([^"]+)"'),
            ("channel", r'"ownerChannelName":"([^"]+)"'),
            ("views", r'"viewCount":"(\d+)"'),
            ("duration", r'"lengthSeconds":"(\d+)"'),
            ("likes", r'"label":"([0-9,]+ likes)"'),
        ]
        for key, pattern in patterns:
            match = re.search(pattern, html)
            if match:
                raw = match.group(1)
                if key == "views":
                    info[key] = f"{int(raw):,}"
                elif key == "duration":
                    secs = int(raw)
                    info[key] = f"{secs // 60}:{secs % 60:02d}"
                else:
                    info[key] = raw

        return {"status": "ok", "info": info}
    except Exception as e:
        logger.error(f"YouTube info failed: {e}")
        return {"status": "error", "detail": str(e)}


async def youtube_get_transcript(url: str) -> dict[str, Any]:
    """Fetch the transcript/subtitles of a YouTube video.

    Args:
        url: Full YouTube video URL.

    Returns:
        Dict with transcript text.
    """
    video_id = _extract_video_id(url)
    if not video_id:
        return {"status": "error", "detail": "Invalid YouTube URL"}

    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None

        lang_priority = ["en", "hi", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]
        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            pass

        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break

        if transcript is None:
            return {"status": "error", "detail": "No transcript available"}

        fetched = transcript.fetch()
        text = " ".join(entry.text for entry in fetched)

        return {"status": "ok", "transcript": text, "length": len(text), "language": transcript.language_code}
    except ImportError:
        return {"status": "error", "detail": "youtube-transcript-api not installed. Run: pip install youtube-transcript-api"}
    except Exception as e:
        logger.error(f"Transcript fetch failed: {e}")
        return {"status": "error", "detail": str(e)}


async def youtube_summarize(url: str, save: bool = False) -> dict[str, Any]:
    """Get transcript and summarize it using Gemini.

    Args:
        url: YouTube video URL.
        save: If True, save summary to Desktop.

    Returns:
        Dict with summary text and optionally saved file path.
    """
    if not _is_valid_youtube_url(url):
        return {"status": "error", "detail": "Invalid YouTube URL"}

    # Get transcript
    transcript_result = await youtube_get_transcript(url)
    if transcript_result.get("status") != "ok":
        return transcript_result

    transcript = transcript_result["transcript"]

    # Check API key
    api_key = _get_api_key()
    if not api_key:
        return {"status": "error", "detail": "Gemini API key not configured"}

    try:
        from google import genai as _genai

        client = _genai.Client(api_key=api_key)
        max_chars = 80000
        truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Please summarize this YouTube video transcript:\n\n{truncated}",
            config={
                "system_instruction": (
                    "You are BARQ, an AI assistant. "
                    "Summarize YouTube video transcripts clearly and concisely. "
                    "Structure: 1-sentence overview, then 3-5 key points. "
                    "Be direct and informative."
                )
            },
        )
        summary = response.text.strip()

        result: dict[str, Any] = {"status": "ok", "summary": summary, "url": url}

        if save:
            from pathlib import Path
            desktop = Path.home() / "Desktop"
            desktop.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = desktop / f"youtube_summary_{ts}.txt"
            header = (
                f"BARQ — YouTube Summary\n"
                f"{'─' * 50}\n"
                f"URL : {url}\n"
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"{'─' * 50}\n\n"
            )
            filepath.write_text(header + summary, encoding="utf-8")
            result["saved_path"] = str(filepath)

        return result
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return {"status": "error", "detail": str(e)}


async def youtube_trending(region: str = "US", max_results: int = 8) -> dict[str, Any]:
    """Get trending YouTube videos for a region.

    Args:
        region: ISO 3166-1 alpha-2 country code (default 'US').
        max_results: Max videos to return (default 8).

    Returns:
        Dict with list of trending videos.
    """
    try:
        url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url, timeout=15)
            html = resp.text

        titles = re.findall(r'"title":{"runs":\[\{"text":"([^"]+)"}\]', html)
        channels = re.findall(r'"ownerText":{"runs":\[\{"text":"([^"]+)"', html)
        view_counts = re.findall(r'"viewCount":"(\d+)"', html)

        results, seen = [], set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5:
                continue
            seen.add(title)
            channel = channels[len(results)] if len(results) < len(channels) else "Unknown"
            views = ""
            if len(results) < len(view_counts):
                views = f"{int(view_counts[len(results)]):,}"

            results.append({
                "rank": len(results) + 1,
                "title": title,
                "channel": channel,
                "views": views,
            })
            if len(results) >= max_results:
                break

        return {"status": "ok", "region": region.upper(), "count": len(results), "results": results}
    except Exception as e:
        logger.error(f"Trending scrape failed: {e}")
        return {"status": "error", "detail": str(e)}
