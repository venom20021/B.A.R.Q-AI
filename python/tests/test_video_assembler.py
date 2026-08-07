"""
Tests for the Phase 1b Video v2 assembler (social/video.py).

Covers the graceful-degradation contract: the renderer must never crash when
footage/TTS/ffmpeg/moviepy are unavailable — it falls back to placeholders and
styled slides. Network and media decoding are never exercised here.
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def assembler():
    from social.video import VideoAssembler
    return VideoAssembler()


# ─── Script section splitting (pure logic) ──────────────────────────────────

def test_split_into_sections_happy_path(assembler):
    script = (
        "Hook\n"
        "Grab attention with a bold question.\n"
        "Content\n"
        "The meat of the video with three key points.\n"
        "CTA\n"
        "Follow for more!\n"
    )
    sections = assembler._split_into_sections(script, ["Hook", "Content", "CTA"])
    assert len(sections) == 3
    assert sections[0][0] == "Hook"
    assert "bold question" in sections[0][1]
    assert sections[2][0] == "CTA"


def test_split_into_sections_no_headers(assembler):
    """A script with no section headers becomes a single Content section."""
    script = "Just a plain paragraph without any headers in it."
    sections = assembler._split_into_sections(script, ["Hook", "Content", "CTA"])
    assert len(sections) == 1
    assert sections[0][0] == "Content"
    assert "plain paragraph" in sections[0][1]


def test_split_into_sections_empty(assembler):
    assert assembler._split_into_sections("", ["Hook"]) == [("Content", "")]


# ─── Phase 2d: aspect-aware canvas ───────────────────────────────────────────

def test_aspect_size_defaults_vertical():
    from social.video import _aspect_size
    assert _aspect_size(None) == (1080, 1920)
    assert _aspect_size("") == (1080, 1920)


def test_aspect_size_by_aspect_string():
    from social.video import _aspect_size
    assert _aspect_size("9:16") == (1080, 1920)
    assert _aspect_size("16:9") == (1920, 1080)
    assert _aspect_size("1:1") == (1080, 1080)


def test_aspect_size_by_script_format():
    from social.video import _aspect_size
    assert _aspect_size("youtube_shorts") == (1080, 1920)
    assert _aspect_size("tiktok_short") == (1080, 1920)
    assert _aspect_size("instagram_reel") == (1080, 1920)
    assert _aspect_size("youtube_essay") == (1920, 1080)
    assert _aspect_size("twitter_thread") == (1080, 1080)


def test_aspect_size_unknown_format_falls_back_vertical():
    from social.video import _aspect_size
    assert _aspect_size("some_unknown_format") == (1080, 1920)


# ─── Phase 2d: Ken Burns on stills ───────────────────────────────────────────

def test_ken_burns_returns_modified_clip_on_success(assembler, monkeypatch):
    """On a successful animated resize the Ken Burns clip is returned."""
    class FakeClip:
        def resized(self, *a, **k):
            return "kb-clip"

    # _apply_ken_burns calls clip.resized(zoom_lambda) — FakeClip returns 'kb-clip'
    result = assembler._apply_ken_burns(FakeClip(), 8.0)
    assert result == "kb-clip"


def test_ken_burns_falls_back_on_error(assembler, monkeypatch):
    """If moviepy rejects the animated resize, the original clip is returned."""
    class BadClip:
        def resized(self, *a, **k):
            raise RuntimeError("resize failed")

    result = assembler._apply_ken_burns(BadClip(), 8.0)
    assert isinstance(result, BadClip)


# ─── Phase 2d: free topic-image fallback ───────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_topic_images_no_topic_returns_empty(assembler):
    """No topic and no cues -> empty list, never an exception."""
    result = await assembler._fetch_topic_images("", [], count=3)
    assert result == []


@pytest.mark.asyncio
async def test_fetch_topic_images_failure_non_fatal(assembler, monkeypatch):
    """A failed Pollinations request must return [] (non-fatal)."""
    class BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr("httpx.AsyncClient", BoomClient)
    result = await assembler._fetch_topic_images("remote jobs", [], count=2)
    assert result == []


# ─── Stock footage graceful fallback ────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_stock_footage_no_api_key(assembler):
    """No Pexels key -> empty list (caller falls back to text slides), never an
    exception and never a network call."""
    assembler.settings.pexels_api_key = ""
    result = await assembler._fetch_stock_footage("remote jobs")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_stock_footage_empty_query(assembler):
    assembler.settings.pexels_api_key = "fake-key"
    result = await assembler._fetch_stock_footage("")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_stock_footage_request_failure(assembler, monkeypatch):
    """A failed Pexels request must return [] (non-fatal), not raise."""
    assembler.settings.pexels_api_key = "fake-key"

    class BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("network down")

    # video.py imports httpx inside the function, so patching the real module's
    # AsyncClient (not a module attribute) is what intercepts the call.
    monkeypatch.setattr("httpx.AsyncClient", BoomClient)
    result = await assembler._fetch_stock_footage("remote jobs")
    assert result == []


# ─── Caption overlays (moviepy 2.x) ────────────────────────────────────────

def test_caption_overlays_use_text_keyword(assembler, monkeypatch):
    """Caption overlays must call moviepy 2.x TextClip with `text=` — the
    legacy `txt=` kwarg was removed in 2.x and silently dropped the caption."""
    calls = []

    class FakeCaption:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def with_position(self, *a, **k):
            return self

        def with_start(self, *a, **k):
            return self

        def with_duration(self, *a, **k):
            return self

    class FakeBase:
        duration = 24.0

    monkeypatch.setattr("social.video.TextClip", FakeCaption)
    monkeypatch.setattr(
        "social.video.concatenate_videoclips", lambda clips, **k: FakeBase()
    )
    monkeypatch.setattr("social.video.CompositeVideoClip", lambda *a, **k: FakeBase())

    assembler._composite_with_captions([FakeBase()], [("Hook", "hi there")])

    assert calls, "caption TextClip was never invoked"
    assert "text" in calls[0]
    assert "txt" not in calls[0]


# ─── Render degradation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_render_writes_placeholder_without_moviepy(assembler, tmp_path):
    """Without moviepy installed, render() writes a placeholder file so the
    pipeline + DB row still complete."""
    out = tmp_path / "out.mp4"
    with patch("social.video.MOVIEPY_AVAILABLE", False):
        result = await assembler.render(
            {"topic": "test", "script": "Some script text for the video."},
            out,
        )
    assert result == out
    assert out.exists()
    assert out.read_bytes() == b""


@pytest.mark.asyncio
async def test_render_never_raises_on_garbage_script(assembler, tmp_path):
    """Even a malformed/empty script must not raise — render always returns a
    path (placeholder or file)."""
    out = tmp_path / "garbage.mp4"
    with patch("social.video.MOVIEPY_AVAILABLE", False):
        result = await assembler.render(
            {"topic": None, "script": None, "visual_cues": None},
            out,
        )
    assert result == out
    assert out.exists()
