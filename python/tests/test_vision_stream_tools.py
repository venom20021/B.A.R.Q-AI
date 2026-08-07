"""Tests for exposing the persistent vision stream to the Gemini voice agent.

Covers:
- The four ``vision_stream_*`` tools being visible in the Gemini schemas.
- The new ``vision_stream_analyze`` tool (warm-stream path + REST fallback).
- ``VisionStreamSession.analyze_and_wait`` synchronous transcript capture.
- Console-safe printing (Windows cp1252 emoji crash regression).

No live network calls are made — all Gemini/session internals are mocked.
"""

import asyncio
import builtins
from concurrent.futures import Future
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.vision import VisionStreamSession, _safe_print
from voice.function_executor import (
    FUNCTION_REGISTRY,
    _vision_stream_analyze,
    execute_function,
    get_function_schemas,
)

STREAM_TOOLS = (
    "vision_stream_start",
    "vision_stream_stop",
    "vision_stream_status",
    "vision_stream_analyze",
)


# ─── Console-safe printing (cp1252 regression) ─────────────────────────


def _cp1252_console_print(real_print):
    """Return a fake ``builtins.print`` that mimics a Windows cp1252 console.

    Encodes the message with cp1252 first (which raises ``UnicodeEncodeError``
    for emoji / non-Latin-1 characters) and only calls the real print when the
    message is cp1252-encodable — exactly what a real Windows terminal does.
    """
    def _fake_print(*args, **kwargs):
        for a in args:
            if isinstance(a, str):
                a.encode("cp1252")
        real_print(*args, **kwargs)
    return _fake_print


def test_safe_print_survives_emoji_on_cp1252_console(monkeypatch):
    """Regression: emoji prints crashed the vision thread on Windows (charmap).

    A bare ``print("[VisionStream] ✅ Session ready")`` raises
    ``UnicodeEncodeError`` on cp1252 consoles; ``_safe_print`` must fall back
    to ASCII replacement instead of crashing.
    """
    monkeypatch.setattr(builtins, "print", _cp1252_console_print(builtins.print))
    # Must not raise despite the emoji glyphs (previously fatal).
    _safe_print("[VisionStream] ✅ Session ready")
    _safe_print("[VisionStream] 🔌 Connecting to Gemini Live...")
    _safe_print("[VisionStream] 💬 'hello'")
    _safe_print(f"[VisionStream] Thread error: {ValueError('boom')}")


def test_safe_print_preserves_plain_ascii_on_cp1252_console(monkeypatch):
    """Plain ASCII messages still print verbatim through the cp1252 gate."""
    monkeypatch.setattr(builtins, "print", _cp1252_console_print(builtins.print))
    # Pure-ASCII text encodes fine on cp1252 and must pass through unchanged.
    _safe_print("[VisionStream] Session did not connect within 25s")


def test_safe_print_no_crash_on_utf8_console(capsys):
    """On a UTF-8-capable console the emoji simply prints (no fallback)."""
    _safe_print("[VisionStream] ✅ Session ready")
    captured = capsys.readouterr()
    assert "Session ready" in captured.out


def test_no_bare_print_in_vision_stream_paths():
    """Guard: no unguarded ``print()`` may sneak back into vision.py.

    This bug class has recurred repeatedly (emoji prints crash on Windows
    cp1252 consoles).  Every log call in ``agent/vision.py`` must go through
    ``_safe_print`` — a bare ``print()`` would re-introduce the crash that
    killed the vision stream thread.  Scans the source (excluding the helper's
    own body and non-stream helpers) so the guard can't rot.
    """
    import inspect
    from agent import vision as vision_mod
    src = inspect.getsource(vision_mod)
    # Strip the helper's own body (it intentionally calls builtins.print).
    helper_start = src.find("def _safe_print")
    helper_end = src.find("def auto_detect_camera", helper_start)
    cleaned = src[:helper_start] + src[helper_end:]
    # A bare print statement would appear as "    print(" — the emoji prints
    # were the crash source; _safe_print is the only allowed logger.
    for line in cleaned.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("print("), (
            f"Bare print() found in vision.py (would crash on cp1252): {line}"
        )


# ─── Schema & registry exposure ────────────────────────────────────────


def test_vision_stream_tools_are_in_gemini_schemas():
    names = [s["name"] for s in get_function_schemas()]
    for tool in STREAM_TOOLS:
        assert tool in names


def test_vision_stream_analyze_schema_describes_parameters():
    schemas = {s["name"]: s for s in get_function_schemas()}
    schema = schemas["vision_stream_analyze"]
    props = schema["parameters"]["properties"]
    assert "prompt" in props
    assert "source" in props


def test_vision_stream_analyze_is_registered_in_executor():
    for tool in STREAM_TOOLS:
        assert tool in FUNCTION_REGISTRY


def test_execute_function_dispatches_vision_stream_start():
    with patch("agent.vision.ensure_vision_stream", return_value=True):
        result = asyncio.run(execute_function("vision_stream_start", {}))
    assert result["status"] == "connected"


# ─── vision_stream_analyze: warm-stream path ───────────────────────────


def test_vision_stream_analyze_routes_through_warm_stream():
    session = MagicMock()
    session.is_ready = True
    session.analyze_and_wait.return_value = "You're looking at a code editor."

    with patch("agent.vision.ensure_vision_stream", return_value=True), \
         patch("agent.vision.get_vision_stream_session", return_value=session), \
         patch("agent.vision.capture_screen", return_value=(b"img", "image/jpeg")):
        result = _vision_stream_analyze(prompt="What's on screen?")

    assert result["status"] == "success"
    assert result["via"] == "stream"
    assert result["analysis"] == "You're looking at a code editor."
    assert result["source"] == "screen"
    session.analyze_and_wait.assert_called_once()
    prompt = session.analyze_and_wait.call_args[0][2]
    assert prompt == "What's on screen?"


def test_vision_stream_analyze_supports_camera_source():
    session = MagicMock()
    session.is_ready = True
    session.analyze_and_wait.return_value = "I see you."

    with patch("agent.vision.ensure_vision_stream", return_value=True), \
         patch("agent.vision.get_vision_stream_session", return_value=session), \
         patch("agent.vision.capture_camera", return_value=(b"cam", "image/jpeg")):
        result = _vision_stream_analyze(source="camera")

    assert result["status"] == "success"
    assert result["source"] == "camera"
    assert result["via"] == "stream"


def test_vision_stream_analyze_falls_back_to_rest_when_stream_analyze_fails():
    session = MagicMock()
    session.is_ready = True
    session.analyze_and_wait.side_effect = TimeoutError("timed out")

    with patch("agent.vision.ensure_vision_stream", return_value=True), \
         patch("agent.vision.get_vision_stream_session", return_value=session), \
         patch("agent.vision.capture_screen", return_value=(b"img", "image/jpeg")), \
         patch(
             "agent.vision.analyze_image_with_gemini",
             new_callable=AsyncMock,
             return_value="Fallback description.",
         ):
        result = _vision_stream_analyze()

    assert result["status"] == "success"
    assert result["via"] == "rest"
    assert result["analysis"] == "Fallback description."


# ─── vision_stream_analyze: REST fallback & error paths ────────────────


def test_vision_stream_analyze_falls_back_to_rest_when_stream_unavailable():
    with patch("agent.vision.ensure_vision_stream", return_value=False), \
         patch("agent.vision.capture_screen", return_value=(b"img", "image/png")), \
         patch(
             "agent.vision.analyze_image_with_gemini",
             new_callable=AsyncMock,
             return_value="A terminal with running code.",
         ):
        result = _vision_stream_analyze()

    assert result["status"] == "success"
    assert result["via"] == "rest"
    assert "terminal" in result["analysis"]


def test_vision_stream_analyze_returns_error_when_capture_fails():
    with patch("agent.vision.ensure_vision_stream", return_value=False), \
         patch(
             "agent.vision.capture_screen",
             side_effect=RuntimeError("mss not installed"),
         ):
        result = _vision_stream_analyze()

    assert result["status"] == "error"
    assert "mss" in result["detail"]


def test_vision_stream_analyze_invalid_source_defaults_to_screen():
    with patch("agent.vision.ensure_vision_stream", return_value=False), \
         patch("agent.vision.capture_screen", return_value=(b"img", "image/png")), \
         patch(
             "agent.vision.analyze_image_with_gemini",
             new_callable=AsyncMock,
             return_value="text",
         ):
        result = _vision_stream_analyze(source="webcam")  # not 'screen'/'camera'

    assert result["status"] == "success"
    assert result["source"] == "screen"


# ─── VisionStreamSession.analyze_and_wait ──────────────────────────────


def test_analyze_and_wait_raises_when_stream_not_ready():
    session = VisionStreamSession()  # never started — no loop/queue/connection
    with pytest.raises(RuntimeError, match="not ready"):
        session.analyze_and_wait(b"img", "image/jpeg", "What do you see?")


def test_analyze_and_wait_clears_pending_future_on_failure():
    session = VisionStreamSession()
    session._loop = object()
    session._out_queue = object()
    session._connected = True  # analyze() will fail: queue is not an asyncio.Queue

    with pytest.raises(RuntimeError):
        session.analyze_and_wait(b"img", "image/jpeg", "hi", timeout=1)

    assert session._sync_future is None


def test_deliver_transcript_resolves_pending_sync_future():
    session = VisionStreamSession()
    fut = Future()
    session._sync_future = fut

    session._deliver_transcript("The screen shows a browser.")

    assert fut.done()
    assert fut.result(timeout=1) == "The screen shows a browser."


def test_deliver_transcript_forwards_to_callback_and_ignores_no_future():
    session = VisionStreamSession()
    captured = []
    session._transcript_callback = captured.append

    session._deliver_transcript("A document is open.")

    assert captured == ["A document is open."]
    # No pending future — must not raise.


def test_analyze_and_wait_raises_timeout_when_no_transcript_arrives():
    session = VisionStreamSession()
    loop = asyncio.new_event_loop()
    session._loop = loop
    session._out_queue = asyncio.Queue()
    session._connected = True
    try:
        with pytest.raises(TimeoutError):
            session.analyze_and_wait(b"img", "image/jpeg", "hi", timeout=0.1)
    finally:
        loop.close()
    assert session._sync_future is None


def test_deliver_transcript_enqueues_for_drain_consumers():
    session = VisionStreamSession()
    queue = asyncio.Queue()
    session._transcript_queue = queue

    session._deliver_transcript("drainable transcript")

    assert asyncio.run(queue.get()) == "drainable transcript"


def test_await_next_transcript_drains_queued_transcript():
    session = VisionStreamSession()
    queue = asyncio.Queue()
    session._transcript_queue = queue

    async def _run():
        await queue.put("hello")
        return await session.await_next_transcript(timeout=0.5)

    assert asyncio.run(_run()) == "hello"


def test_await_next_transcript_returns_none_on_timeout():
    session = VisionStreamSession()
    session._transcript_queue = asyncio.Queue()

    assert asyncio.run(session.await_next_transcript(timeout=0.05)) is None


def test_await_next_transcript_returns_none_without_queue():
    session = VisionStreamSession()  # no transcript queue (never started)

    assert asyncio.run(session.await_next_transcript(timeout=0.05)) is None


def test_vision_stream_analyze_falls_back_when_stream_returns_empty_text():
    session = MagicMock()
    session.is_ready = True
    session.analyze_and_wait.return_value = ""  # audio-only response, no transcript

    with patch("agent.vision.ensure_vision_stream", return_value=True), \
         patch("agent.vision.get_vision_stream_session", return_value=session), \
         patch("agent.vision.capture_screen", return_value=(b"img", "image/jpeg")), \
         patch(
             "agent.vision.analyze_image_with_gemini",
             new_callable=AsyncMock,
             return_value="REST description.",
         ):
        result = _vision_stream_analyze()

    assert result["status"] == "success"
    assert result["via"] == "rest"
    assert result["analysis"] == "REST description."
