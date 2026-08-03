"""
Tests for the Gemini Live dead-connection recovery.

Root cause: when the Gemini WebSocket died (e.g. "sent 1011 (internal error)
keepalive ping timeout; no close frame received"), the send loop caught the
exception, printed "Send error", and kept hammering the dead socket forever
while ``is_running`` stayed True — so the ConversationListener's retry logic
never fired and BARQ hung unresponsive.

Fix: detect connection-closed errors, raise ``_ConnectionClosed`` so the
TaskGroup exits and ``start_conversation()`` sets ``_running = False``, which
lets the listener reconnect.  Note: ``LiveSession.receive()`` ends cleanly
after EVERY complete turn (the SDK breaks on ``turn_complete``), so a silent
stream end is NORMAL — the receive loop re-enters ``receive()`` per turn and
only treats raised connection errors as death.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture
def agent():
    pytest.importorskip("google.genai")
    from voice.gemini_agent import GeminiVoiceAgent
    return GeminiVoiceAgent(api_key="test-key")


# ─── _is_connection_closed_error heuristic ────────────────────────────────


class TestConnectionClosedDetection:
    """The dead-connection heuristic must match real google-genai errors."""

    def test_matches_keepalive_ping_timeout(self, agent):
        """The exact error from the log must be detected as connection-dead."""
        exc = RuntimeError(
            "sent 1011 (internal error) keepalive ping timeout; no close frame received"
        )
        assert agent._is_connection_closed_error(exc) is True

    def test_matches_connection_reset(self, agent):
        exc = ConnectionResetError("An existing connection was forcibly closed")
        assert agent._is_connection_closed_error(exc) is True

    def test_matches_broken_pipe(self, agent):
        exc = BrokenPipeError(32, "Broken pipe")
        assert agent._is_connection_closed_error(exc) is True

    def test_matches_connection_closed_class_name(self, agent):
        # Simulate websockets' ConnectionClosedError without importing it
        cls = type("ConnectionClosedError", (Exception,), {})
        exc = cls("sent 1011 (internal error) keepalive ping timeout")
        assert agent._is_connection_closed_error(exc) is True

    def test_matches_1011_code(self, agent):
        exc = RuntimeError("sent 1011 (internal error)")
        assert agent._is_connection_closed_error(exc) is True

    def test_matches_abnormal_closure_1006(self, agent):
        """APIError wraps websockets close codes (1006 etc.) as the message."""
        exc = RuntimeError("Code: 1006, message: 'Abnormal closure.'")
        assert agent._is_connection_closed_error(exc) is True

    def test_ignores_transient_send_errors(self, agent):
        """Non-connection errors (queue full, bad payload) must NOT kill the agent."""
        exc = RuntimeError("queue is full")
        assert agent._is_connection_closed_error(exc) is False

    def test_ignores_timeout_when_not_connection(self, agent):
        exc = asyncio_timeout_error()
        assert agent._is_connection_closed_error(exc) is False

    def test_none_is_false(self, agent):
        assert agent._is_connection_closed_error(None) is False


# ─── _send_mic_loop raises on dead socket ─────────────────────────────────


class TestSendLoopConnectionRecovery:
    """The send loop must stop (via _ConnectionClosed) instead of spamming."""

    @pytest.mark.asyncio
    async def test_send_loop_raises_on_dead_connection(self, agent):
        """A keepalive-timeout send error raises _ConnectionClosed."""
        from voice.gemini_agent import _ConnectionClosed

        agent._running = True
        agent._session = MagicMock()
        agent._session.send_realtime_input = AsyncMock(
            side_effect=RuntimeError(
                "sent 1011 (internal error) keepalive ping timeout; no close frame received"
            )
        )
        agent._audio_out_queue.put_nowait(
            {"data": b"\x00" * 1024, "mime_type": "audio/pcm"}
        )

        # Patch sounddevice so no real mic hardware is opened
        with patch("sounddevice.InputStream") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value = mock_stream
            with pytest.raises(_ConnectionClosed):
                await agent._send_mic_loop()
        assert agent._running is True  # task raised; start_conversation sets False

    @pytest.mark.asyncio
    async def test_send_loop_survives_transient_errors(self, agent):
        """A transient (non-connection) error is logged but does not kill the loop."""
        from voice.gemini_agent import _ConnectionClosed

        agent._running = True
        agent._session = MagicMock()
        # First call raises a transient error, second call succeeds
        agent._session.send_realtime_input = AsyncMock(
            side_effect=[RuntimeError("queue is full"), None]
        )
        agent._audio_out_queue.put_nowait({"data": b"\x00" * 1024, "mime_type": "audio/pcm"})
        agent._audio_out_queue.put_nowait({"data": b"\x01" * 1024, "mime_type": "audio/pcm"})

        with patch("sounddevice.InputStream") as mock_input:
            mock_input.return_value = MagicMock()
            # No _ConnectionClosed should be raised (transient error swallowed)
            # The loop continues until _running flips; we don't want an infinite
            # loop, so we pre-cancel by setting a short stop.
            async def _stop_after():
                import asyncio
                await asyncio.sleep(0.05)
                agent._running = False

            import asyncio
            stop_task = asyncio.create_task(_stop_after())
            try:
                await agent._send_mic_loop()
            finally:
                stop_task.cancel()
                try:
                    await stop_task
                except asyncio.CancelledError:
                    pass
        assert agent._session.send_realtime_input.await_count >= 2


# ─── _receive_loop: per-turn re-entry, dead connection detection ───────────


class TestReceiveLoopConnectionRecovery:
    """The receive loop must signal a dead connection instead of hanging.

    ``LiveSession.receive()`` returns after each complete turn (the SDK
    breaks on ``turn_complete``), so the loop re-enters it for the next
    turn.  Only raised connection errors indicate a dead socket.
    """

    @pytest.mark.asyncio
    async def test_receive_loop_raises_on_connection_error(self, agent):
        from voice.gemini_agent import _ConnectionClosed

        agent._running = True

        # Build a fake session whose receive() raises a connection error
        async def _dead_receive():
            raise RuntimeError(
                "sent 1011 (internal error) keepalive ping timeout; no close frame received"
            )
            yield  # pragma: no cover

        agent._session = MagicMock()
        agent._session.receive = _dead_receive

        with pytest.raises(_ConnectionClosed):
            await agent._receive_loop()

    @pytest.mark.asyncio
    async def test_receive_loop_reenters_after_turn_end(self, agent):
        """receive() ends after each complete turn — the loop re-enters it.

        Regression test: a clean turn end (the SDK's receive() breaks on
        turn_complete) must NOT be treated as a dead connection.
        """
        from voice.gemini_agent import _ConnectionClosed

        calls = {"n": 0}
        agent._running = True

        async def _one_turn_then_dead():
            calls["n"] += 1
            if calls["n"] == 1:
                return  # first turn ends silently — this is NORMAL
            raise RuntimeError(
                "sent 1011 (internal error) keepalive ping timeout; no close frame received"
            )
            yield  # pragma: no cover — makes this an async generator

        agent._session = MagicMock()
        agent._session.receive = _one_turn_then_dead

        # A genuinely dead connection on the SECOND turn still raises
        with pytest.raises(_ConnectionClosed):
            await agent._receive_loop()
        assert calls["n"] >= 2  # receive() was re-entered for the next turn

    @pytest.mark.asyncio
    async def test_receive_loop_ends_cleanly_when_stopped(self, agent):
        """When _running is False, a normal stream end is NOT a dead connection."""
        from voice.gemini_agent import _ConnectionClosed

        agent._running = False

        async def _silent_end():
            return
            yield  # pragma: no cover

        agent._session = MagicMock()
        agent._session.receive = _silent_end

        # Should NOT raise (already stopped)
        await agent._receive_loop()

    @pytest.mark.asyncio
    async def test_receive_loop_tolerates_transient_error(self, agent):
        """A single transient (non-connection) error is retried, not fatal."""
        from voice.gemini_agent import _ConnectionClosed

        calls = {"n": 0}
        agent._running = True

        async def _flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("bad message payload")
            raise RuntimeError(
                "sent 1011 (internal error) keepalive ping timeout; no close frame received"
            )
            yield  # pragma: no cover — makes this an async generator

        agent._session = MagicMock()
        agent._session.receive = _flaky

        with pytest.raises(_ConnectionClosed):
            await agent._receive_loop()
        assert calls["n"] == 2  # the transient error did NOT kill the loop

    @pytest.mark.asyncio
    async def test_receive_loop_escalates_repeated_errors(self, agent):
        """3 consecutive non-connection errors escalate to a reconnect."""
        from voice.gemini_agent import _ConnectionClosed

        calls = {"n": 0}
        agent._running = True

        async def _always_bad():
            calls["n"] += 1
            raise ValueError("bad message payload")
            yield  # pragma: no cover — makes this an async generator

        agent._session = MagicMock()
        agent._session.receive = _always_bad

        with pytest.raises(_ConnectionClosed):
            await agent._receive_loop()
        assert calls["n"] == 3  # tolerated 1-2, escalated on the 3rd


# ─── start_conversation sets _running = False on _ConnectionClosed ────────


class TestStartConversationRecovery:
    """start_conversation must end the TaskGroup and clear _running on death."""

    @pytest.mark.asyncio
    async def test_start_conversation_clears_running_on_connection_closed(self, agent):
        from voice.gemini_agent import _ConnectionClosed

        agent._running = True
        agent._session = MagicMock()

        # _send_mic_loop will raise _ConnectionClosed; the other loops end.
        async def _dead_send(device=None):
            raise _ConnectionClosed("keepalive ping timeout")
            yield  # pragma: no cover

        with (
            patch.object(agent, "_send_mic_loop", side_effect=_dead_send),
            patch.object(agent, "_play_audio_loop", new=AsyncMock()),
            patch.object(agent, "_receive_loop", new=AsyncMock()),
        ):
            await agent.start_conversation()
        assert agent._running is False


# ─── Helpers ──────────────────────────────────────────────────────────────


def asyncio_timeout_error():
    """Return an asyncio.TimeoutError (timeout is not a connection-closed signal)."""
    import asyncio
    return asyncio.TimeoutError("timed out")
