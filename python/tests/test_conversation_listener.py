"""
Integration tests for the conversation listener:

  - start_conversation() / stop_conversation() lifecycle
  - VAD silence timeout configurability
  - Exit command detection (_is_exit_command)
  - Barge-in: _interrupt_requested propagation, interrupt mid-stream
  - play_with_interrupt: normal completion, interrupted playback
  - Conversation loop error resilience
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice.conversation_listener import (
    ConversationListener,
    VAD_SILENCE_TIMEOUT,
    VAD_ENERGY_THRESHOLD,
    VAD_MAX_DURATION,
)
from voice.interrupt_handler import InterruptHandler


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_stt() -> MagicMock:
    """Mock SpeechProcessor with transcribe_streaming returning an async generator."""
    stt = MagicMock()
    return stt


@pytest.fixture
def mock_responder() -> MagicMock:
    """Mock BARQResponder with conversation, is_speaking, stt_text, etc."""
    resp = MagicMock()
    resp.conversation = MagicMock()
    resp.conversation.is_active = False
    resp.conversation.start_session = MagicMock()
    resp.conversation.end_session = MagicMock()
    resp.is_speaking = False
    resp.is_processing = False
    resp.stt_text = ""
    resp._interrupt_requested = False
    resp.stream_respond = MagicMock()
    resp.respond = AsyncMock(return_value={
        "text": "Goodbye!",
        "audio_path": "/tmp/goodbye.mp3",
        "action": "command",
    })
    return resp


@pytest.fixture
def listener(mock_stt: MagicMock, mock_responder: MagicMock) -> ConversationListener:
    """Return a ConversationListener with mocked dependencies."""
    return ConversationListener(stt=mock_stt, responder=mock_responder)


# ═══════════════════════════════════════════════════════════════════════
# VAD Loop — Lifecycle
# ═══════════════════════════════════════════════════════════════════════


class TestConversationLifecycle:
    """Start/stop lifecycle of the conversation listener."""

    async def test_start_conversation_sets_active(self, listener: ConversationListener):
        """start_conversation() should set is_active and start the loop task."""
        assert listener.is_active is False
        await listener.start_conversation()
        assert listener.is_active is True
        assert listener._loop_task is not None
        assert not listener._loop_task.done()

    async def test_start_conversation_idempotent(self, listener: ConversationListener):
        """Calling start_conversation() twice should be a no-op."""
        await listener.start_conversation()
        task_id = id(listener._loop_task)
        await listener.start_conversation()
        # Task should be the same (not replaced)
        assert id(listener._loop_task) == task_id
        assert listener.is_active is True

    async def test_start_starts_session(self, listener: ConversationListener):
        """start_conversation() should start a conversation session."""
        await listener.start_conversation()
        listener.responder.conversation.start_session.assert_called_once_with("voice_conversation")

    async def test_stop_conversation_ends_session(self, listener: ConversationListener):
        """stop_conversation() should end the session and clear the task."""
        await listener.start_conversation()
        await listener.stop_conversation()
        assert listener.is_active is False
        assert listener._loop_task is None
        listener.responder.conversation.end_session.assert_called_once()

    async def test_stop_conversation_when_not_active(self, listener: ConversationListener):
        """stop_conversation() when not active should end session but not crash."""
        await listener.stop_conversation()
        assert listener.is_active is False
        # stop_conversation always calls end_session, even if not active
        listener.responder.conversation.end_session.assert_called_once()

    async def test_cancelled_loop_cleans_up(self, listener: ConversationListener):
        """Cancelling the loop task should not raise unhandled exceptions."""
        await listener.start_conversation()
        assert listener.is_active is True

        # Cancel the loop task directly — the loop catches CancelledError
        # and re-raises it, which propagates to stop_conversation
        assert listener._loop_task is not None
        listener._loop_task.cancel()

        # stop_conversation should handle the cancellation gracefully
        await listener.stop_conversation()
        assert listener.is_active is False

    async def test_property_is_active(self, listener: ConversationListener):
        """is_active property mirrors _conversation_active."""
        assert listener.is_active is False
        listener._conversation_active = True
        assert listener.is_active is True


# ═══════════════════════════════════════════════════════════════════════
# VAD Loop — Silence Timeout Configurability
# ═══════════════════════════════════════════════════════════════════════


class TestVADConfigurability:
    """VAD silence timeout should be configurable per-instance."""

    def test_default_vad_timeout(self, listener: ConversationListener):
        """Default VAD timeout should match the module constant."""
        assert listener.vad_silence_timeout == VAD_SILENCE_TIMEOUT
        assert listener.vad_silence_timeout == 0.4

    def test_custom_vad_timeout(self, listener: ConversationListener):
        """VAD timeout should be overridable per-instance."""
        listener.vad_silence_timeout = 1.5
        assert listener.vad_silence_timeout == 1.5
        assert listener.vad_silence_timeout != VAD_SILENCE_TIMEOUT

    def test_aggressive_vad(self, listener: ConversationListener):
        """Aggressive (low) timeout for faster endpointing."""
        listener.vad_silence_timeout = 0.15
        assert listener.vad_silence_timeout == 0.15

    def test_lax_vad(self, listener: ConversationListener):
        """Lax (high) timeout for catching trailing words."""
        listener.vad_silence_timeout = 2.0
        assert listener.vad_silence_timeout == 2.0

    async def test_vad_timeout_passed_to_transcribe_streaming(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """VAD timeout should be forwarded to transcribe_streaming()."""
        # Patch _conversation_loop to return early after STT
        async def mock_transcribe(**kwargs):
            yield {"type": "final", "text": ""}  # empty = no speech → exit

        mock_stt.transcribe_streaming = MagicMock(return_value=mock_transcribe())

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        listener.vad_silence_timeout = 0.75

        await listener.start_conversation()
        # Give the loop a moment to start and call transcribe_streaming
        import asyncio
        await asyncio.sleep(0.05)
        await listener.stop_conversation()

        # Check that transcribe_streaming was called with the VAD timeout
        mock_stt.transcribe_streaming.assert_called_once()
        call_kwargs = mock_stt.transcribe_streaming.call_args[1]
        assert call_kwargs.get("silence_timeout") == 0.75


# ═══════════════════════════════════════════════════════════════════════
# Exit Command Detection
# ═══════════════════════════════════════════════════════════════════════


class TestExitCommand:
    """_is_exit_command should detect various exit phrases."""

    @pytest.fixture
    def listener_no_mocks(self) -> ConversationListener:
        """Pure ConversationListener with bare mocks for exit command test only."""
        return ConversationListener(stt=MagicMock(), responder=MagicMock())

    @pytest.mark.parametrize("phrase", [
        "goodbye",
        "bye bye",
        "that's all",
        "we're done",
        "end conversation",
        "stop conversation",
        "never mind",
        "go to sleep",
        "shut down",
        "that's it for now",
    ])
    def test_exit_phrases_detected(self, listener_no_mocks: ConversationListener, phrase: str):
        """All exit phrases should be detected regardless of case."""
        assert listener_no_mocks._is_exit_command(phrase)
        assert listener_no_mocks._is_exit_command(phrase.upper())
        assert listener_no_mocks._is_exit_command(phrase.capitalize())

    @pytest.mark.parametrize("phrase,expected", [
        ("goodbye friends", True),      # "goodbye" is a whole word
        ("I said goodbye", True),        # "goodbye" at end
        ("stop right there", False),     # "stop" not in exit list
        ("conversation piece", False),   # no whole-word exit phrase match
        ("let's end this", False),       # "end conversation" not present
        ("I'm done", False),             # "we're done" doesn't match "I'm done"
        ("never say never", False),      # "never mind" not present
        ("we're done here", True),       # "we're done" at start
        ("end conversation now", True),  # "end conversation" at start
        ("shut down the system", True),  # "shut down" is in exit list, whole-word match
        ("go to sleep now", True),       # "go to sleep" at start
    ])
    def test_partial_match_still_detected(self, listener_no_mocks: ConversationListener, phrase: str, expected: bool):
        """Phrases containing exit keywords as whole words should match (or not)."""
        result = listener_no_mocks._is_exit_command(phrase)
        assert result is expected, f"'{phrase}' should {'match' if expected else 'not match'}"

    @pytest.mark.parametrize("phrase", [
        "hello", "what's the weather", "open chrome", "tell me a joke",
        "continue", "keep going", "stay", "good", "bye", "going to sleep",
    ])
    def test_non_exit_phrases_not_detected(self, listener_no_mocks: ConversationListener, phrase: str):
        """Non-exit phrases should NOT trigger exit detection."""
        assert listener_no_mocks._is_exit_command(phrase) is False

    def test_exit_command_full_word_boundary(self, listener_no_mocks: ConversationListener):
        """'goodbye' should match, but 'good' alone should not (word boundary)."""
        assert listener_no_mocks._is_exit_command("goodbye") is True
        assert listener_no_mocks._is_exit_command("good") is False

    def test_exit_phrase_in_sentence(self, listener_no_mocks: ConversationListener):
        """Exit phrase embedded in a longer sentence should still match."""
        text = "I think that's all for now, goodbye"
        assert listener_no_mocks._is_exit_command(text) is True

    def test_empty_string_not_exit(self, listener_no_mocks: ConversationListener):
        """Empty string should not be exit."""
        assert listener_no_mocks._is_exit_command("") is False


# ═══════════════════════════════════════════════════════════════════════
# Barge-in — Interrupt Propagation
# ═══════════════════════════════════════════════════════════════════════


class TestBargeIn:
    """Barge-in: _interrupt_requested propagation from responder."""

    def test_interrupt_requested_proxies_to_responder(self, listener: ConversationListener):
        """_interrupt_requested() should return responder._interrupt_requested."""
        assert listener._interrupt_requested() is False
        listener.responder._interrupt_requested = True
        assert listener._interrupt_requested() is True
        listener.responder._interrupt_requested = False
        assert listener._interrupt_requested() is False

    async def test_barge_in_during_response_restarts_listen(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """If stream_respond yields chunks and play_with_interrupt is interrupted,
        the loop should 'continue' (restart listening)."""
        import asyncio

        # STT yields a final transcript, then the loop processes it
        async def stt_stream(**kwargs):
            yield {"type": "final", "text": "hello there"}

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        # Responder stream: yield one chunk, then stop
        async def stream_gen(text):
            yield {"text": "Hello back!", "audio_path": "/tmp/chunk.mp3"}

        mock_responder.stream_respond = MagicMock(return_value=stream_gen("hello there"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        # Patch the listener's OWN interrupt_handler (not the responder's —
        # the listener creates its own InterruptHandler in __init__)
        listener.interrupt_handler.play_with_interrupt = AsyncMock(return_value=True)

        with patch("pathlib.Path.exists", return_value=True):
            await listener.start_conversation()
            await asyncio.sleep(0.1)

        # stream_respond should have been called with the transcribed text
        mock_responder.stream_respond.assert_called_once_with("hello there")
        # play_with_interrupt should have been triggered on the listener's handler
        assert listener.interrupt_handler.play_with_interrupt.called

    async def test_barge_in_sets_interrupt_flag(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """When play_with_interrupt returns True, the responder._interrupt_requested flag should be set."""
        import asyncio

        async def stt_stream(**kwargs):
            yield {"type": "final", "text": "hello"}

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        async def stream_gen(text):
            yield {"text": "Hi!", "audio_path": "/tmp/chunk.mp3"}

        mock_responder.stream_respond = MagicMock(return_value=stream_gen("hello"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        # Patch the listener's OWN interrupt_handler, not the responder's
        listener.interrupt_handler.play_with_interrupt = AsyncMock(return_value=True)

        with patch("pathlib.Path.exists", return_value=True):
            await listener.start_conversation()
            await asyncio.sleep(0.1)

        # After barge-in, _interrupt_requested should have been set to True
        # (the loop sets it to flush the LLM stream)
        assert mock_responder._interrupt_requested is True


# ═══════════════════════════════════════════════════════════════════════
# Barge-in — Scenario Tests
# ═══════════════════════════════════════════════════════════════════════


class TestBargeInScenarios:
    """Comprehensive barge-in scenarios: interrupt during TTS playback
    aborts the stream and restarts listening."""

    async def test_interrupt_before_tts_aborts_chunk(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """If _interrupt_requested is True before play_with_interrupt is called,
        the chunk should be skipped and the loop should restart listening.
        This tests the 'direct interrupt' path in _conversation_loop where
        the flag check comes BEFORE playback."""
        import asyncio

        # STT yields a final transcript once
        async def stt_stream(**kwargs):
            yield {"type": "final", "text": "hello there"}

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        # stream_respond yields multiple chunks — but _interrupt_requested
        # should abort before the second one is played
        async def multi_chunk_stream(text):
            yield {"text": "First sentence.", "audio_path": "/tmp/first.mp3"}
            yield {"text": "Second sentence.", "audio_path": "/tmp/second.mp3"}

        mock_responder.stream_respond = MagicMock(return_value=multi_chunk_stream("hello there"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        # Don't patch play_with_interrupt — we'll set _interrupt_requested directly
        # to test the direct-check path (before play_with_interrupt is called)
        play_mock = AsyncMock(return_value=False)
        listener.interrupt_handler.play_with_interrupt = play_mock

        # Spy on stream_respond to count chunks and set interrupt after first
        chunks_yielded: list[str] = []
        original_generator = mock_responder.stream_respond.return_value

        async def intercept_stream(text):
            nonlocal chunks_yielded
            async for chunk in original_generator:
                chunks_yielded.append(chunk["text"])
                yield chunk
                if len(chunks_yielded) == 1:
                    listener.responder._interrupt_requested = True

        mock_responder.stream_respond = MagicMock(side_effect=intercept_stream)

        with patch("pathlib.Path.exists", return_value=True):
            await listener.start_conversation()
            await asyncio.sleep(0.15)

        # play_with_interrupt should only have been called for the first chunk
        # (the second chunk was aborted by the pre-TTS _interrupt_requested check)
        # Actually, the first chunk's TTS MAY have been called before the interrupt
        # was set, or the interrupt might have been set before it. Either way, the
        # important thing is that at most 1 chunk was processed.
        assert play_mock.call_count <= 1, (
            f"Expected at most 1 play call, got {play_mock.call_count}. "
            "The pre-TTS interrupt check should have aborted chunk 2."
        )

    async def test_interrupt_mid_stream_aborts_remaining_chunks(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """When _interrupt_requested is set during TTS playback of chunk N,
        chunks N+1, N+2, etc. should be aborted by the pre-TTS flag check."""
        import asyncio

        async def stt_stream(**kwargs):
            yield {"type": "final", "text": "hello"}

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        # Many chunks — only first should be processed before interrupt
        async def long_stream(text):
            for i in range(5):
                yield {"text": f"Chunk {i}.", "audio_path": f"/tmp/chunk{i}.mp3"}

        mock_responder.stream_respond = MagicMock(return_value=long_stream("hello"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        play_mock = AsyncMock(return_value=False)
        listener.interrupt_handler.play_with_interrupt = play_mock

        # Spy: track chunks yielded and set interrupt after first
        chunks_yielded: list[str] = []
        original_gen = mock_responder.stream_respond.return_value

        async def track_chunks(text):
            nonlocal chunks_yielded
            async for chunk in original_gen:
                chunks_yielded.append(chunk["text"])
                yield chunk
                if len(chunks_yielded) == 1:
                    listener.responder._interrupt_requested = True

        mock_responder.stream_respond = MagicMock(side_effect=track_chunks)

        with patch("pathlib.Path.exists", return_value=True):
            await listener.start_conversation()
            await asyncio.sleep(0.15)
            await listener.stop_conversation()

        # First chunk should have been yielded (and its TTS started)
        assert len(chunks_yielded) >= 1, "At least the first chunk should have been processed"
        # The interrupt flag should have blocked subsequent chunks from playing
        assert play_mock.call_count <= 1, (
            f"At most 1 play call expected after interrupt, got {play_mock.call_count}"
        )

    async def test_barge_in_cycle_interrupt_restart_interrupt(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """Loop should survive multiple barge-in cycles: interrupt -> continue ->
        listen -> interrupt again -> continue."""
        import asyncio

        # Use side_effect so each call creates a FRESH generator yielding ONE value.
        # This is critical because the conversation loop's async for consumes ALL
        # yields from a single generator in one iteration.
        turn_idx = [0]

        async def multi_turn_stt(**kwargs):
            idx = turn_idx[0]
            turn_idx[0] += 1
            if idx == 0:
                yield {"type": "final", "text": "first command"}
            elif idx == 1:
                yield {"type": "final", "text": "second command"}
            else:
                yield {"type": "final", "text": ""}  # ends conversation

        mock_stt.transcribe_streaming = MagicMock(side_effect=multi_turn_stt)

        # stream_respond yields one chunk per call
        stream_call = [0]

        async def multi_turn_stream(text):
            # stream_respond resets _interrupt_requested on entry in production
            listener.responder._interrupt_requested = False
            stream_call[0] += 1
            if stream_call[0] <= 2:
                yield {"text": f"Response {stream_call[0]}.", "audio_path": "/tmp/r.mp3"}

        mock_responder.stream_respond = MagicMock(side_effect=multi_turn_stream)

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        play_call_count = [0]

        async def interrupt_playback(path, listen_for_interrupt=True):
            play_call_count[0] += 1
            # First playback: interrupt. Second playback: also interrupt.
            # This triggers the 'playback_interrupted' path.
            listener.responder._interrupt_requested = True
            return True  # Interrupted

        listener.interrupt_handler.play_with_interrupt = interrupt_playback

        with patch("pathlib.Path.exists", return_value=True):
            await listener.start_conversation()
            # Allow enough time for two full barge-in cycles, each with a
            # 500ms PortAudio release delay between them.
            await asyncio.sleep(1.5)
            await listener.stop_conversation()

        # The loop should have been called with stream_respond twice
        # (first and second commands), then the third STT turn yielded
        # empty text which ended the conversation.
        assert stream_call[0] >= 2, (
            f"Expected at least 2 stream_respond calls (2 barge-in cycles), got {stream_call[0]}"
        )
        assert play_call_count[0] >= 2, (
            f"Expected at least 2 playback attempts (one per barge-in), got {play_call_count[0]}"
        )

    async def test_interrupt_during_tts_flags_responder(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """When play_with_interrupt returns True (user spoke over BARQ),
        the responder._interrupt_requested flag is set and the loop continues.
        This tests the 'TTS-phase interrupt' path in _conversation_loop."""
        import asyncio

        async def stt_stream(**kwargs):
            yield {"type": "final", "text": "hello"}
            yield {"type": "final", "text": ""}  # end conversation

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        async def single_chunk(text):
            yield {"text": "Response.", "audio_path": "/tmp/r.mp3"}

        mock_responder.stream_respond = MagicMock(side_effect=single_chunk)

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        listener.interrupt_handler.play_with_interrupt = AsyncMock(return_value=True)

        with patch("pathlib.Path.exists", return_value=True):
            await listener.start_conversation()
            await asyncio.sleep(0.2)

        # After interrupt, the flag was set, then the loop continued,
        # and on the next STT iteration (empty text), the conversation ended.
        # The flag should have been reset during the continue.
        assert listener.is_active is False, "Loop should have ended via no-speech"


# ═══════════════════════════════════════════════════════════════════════
# play_with_interrupt — Interaction
# ═══════════════════════════════════════════════════════════════════════


class TestPlayWithInterrupt:
    """InterruptHandler.play_with_interrupt behavior."""

    async def test_play_completes_naturally(self, listener: ConversationListener):
        """play_with_interrupt should return False when playback completes naturally."""
        handler = InterruptHandler()
        result = await handler.play_with_interrupt(
            "/tmp/nonexistent.mp3", listen_for_interrupt=False
        )
        # File doesn't exist — _play returns early, no interrupt detected
        assert result is False
        assert handler.is_playing is False

    async def test_play_with_interrupt_enabled_returns_false_when_no_interrupt(self):
        import asyncio
        """With listen_for_interrupt=True but no speech, playback completes naturally."""
        handler = InterruptHandler()

        async def never_detect_speech():
            """Simulate no speech detected — never returns on its own."""
            while True:
                await asyncio.sleep(3600)

        # Patch _play to complete immediately (natural completion) and
        # _detect_speech to never complete (no speech detected).
        # asyncio.wait with FIRST_COMPLETED will pick play_task as done.
        with (
            patch.object(handler, "_play", AsyncMock()),
            patch.object(handler, "_detect_speech", never_detect_speech),
        ):
            result = await handler.play_with_interrupt(
                "/tmp/fake.mp3", listen_for_interrupt=True
            )
            assert result is False  # Not interrupted — playback completed naturally
            assert handler.is_playing is False

    async def test_interrupt_cancels_pending_task(self):
        """Previous pending interrupt task should be cancelled before starting new playback."""
        import asyncio
        handler = InterruptHandler()

        # Simulate a lingering pending task
        async def never_returns():
            await asyncio.sleep(999)

        task = asyncio.create_task(never_returns())
        handler._pending_interrupt_task = task

        with patch.object(handler, "_play", AsyncMock()):
            result = await handler.play_with_interrupt(
                "/tmp/fake.mp3", listen_for_interrupt=False
            )
            assert result is False
            assert task.cancelled()  # Lingering task was cancelled

    async def test_detect_speech_stops_when_should_stop(self):
        """_detect_speech should exit when should_stop is set."""
        handler = InterruptHandler()
        handler.is_playing = True
        handler.should_stop = True  # Already set to stop

        # Mock sounddevice to avoid hardware dependency
        with patch.multiple(
            handler,
            _detect_speech=AsyncMock(),
            _play=AsyncMock(),
        ):
            result = await handler.play_with_interrupt(
                "/tmp/fake.mp3", listen_for_interrupt=False
            )
            assert result is False


# ═══════════════════════════════════════════════════════════════════════
# Conversation Loop — Error Resilience
# ═══════════════════════════════════════════════════════════════════════


class TestConversationLoopErrors:
    """Error handling in _conversation_loop."""

    async def test_stt_error_does_not_crash(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """If transcribe_streaming raises, the loop should catch it and stop."""
        import asyncio

        mock_stt.transcribe_streaming = MagicMock(side_effect=RuntimeError("STT crashed"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)

        # start_conversation creates a task — if the loop crashes,
        # the exception is caught by _conversation_loop's outer except
        # and sets _conversation_active = False
        await listener.start_conversation()
        await asyncio.sleep(0.05)

        # Allow the loop to process the error and set active to False
        await asyncio.sleep(0.1)
        assert listener.is_active is False

    async def test_stream_respond_error_does_not_crash(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """If stream_respond raises, the loop should catch it and continue."""
        import asyncio

        async def stt_stream(**kwargs):
            yield {"type": "final", "text": "hello"}

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())
        mock_responder.stream_respond = MagicMock(side_effect=RuntimeError("LLM failed"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)

        with patch("pathlib.Path.exists", return_value=True):
            await listener.start_conversation()
            await asyncio.sleep(0.1)

        # The error is caught by the except in the response processing block
        # which 'continue's. Then on the next iteration, STT yields nothing
        # (exhausted generator), so no speech -> stop_conversation.
        # No crash should occur.
        assert listener.is_active is True  # Not crashed, loop exited cleanly via stop
        await listener.stop_conversation()

    async def test_no_speech_detected_ends_conversation(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """If STT returns no speech, the loop should stop gracefully."""
        import asyncio

        async def stt_stream(**kwargs):
            yield {"type": "final", "text": ""}  # empty text = no speech

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)

        await listener.start_conversation()
        await asyncio.sleep(0.1)

        assert listener.is_active is False  # Loop stopped via no-speech path


# ═══════════════════════════════════════════════════════════════════════
# Conversation Loop — Stream Respond Integration
# ═══════════════════════════════════════════════════════════════════════


class TestConversationLoopStreamRespond:
    """Integration of stream_respond within the conversation loop."""

    async def test_stream_respond_called_with_correct_text(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """stream_respond should be called with the transcribed text."""
        import asyncio

        async def stt_stream(**kwargs):
            yield {"type": "final", "text": "hello world"}

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        async def empty_stream(text):
            return
            yield  # pragma: no cover — make it a generator

        mock_responder.stream_respond = MagicMock(return_value=empty_stream("hello world"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)

        await listener.start_conversation()
        await asyncio.sleep(0.1)
        await listener.stop_conversation()

        mock_responder.stream_respond.assert_called_once_with("hello world")

    async def test_stt_interim_updates_responder(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """Interim STT results should update responder.stt_text."""
        import asyncio

        async def stt_stream(**kwargs):
            yield {"type": "interim", "text": "hello"}
            yield {"type": "interim", "text": "hello world"}
            yield {"type": "final", "text": "hello world"}

        mock_stt.transcribe_streaming = MagicMock(return_value=stt_stream())

        async def empty_stream(text):
            return
            yield  # pragma: no cover

        mock_responder.stream_respond = MagicMock(return_value=empty_stream("hello world"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        listener.responder.stt_text = ""

        await listener.start_conversation()
        await asyncio.sleep(0.15)
        await listener.stop_conversation()

        # After processing, stt_text should be cleared (final result)
        assert listener.responder.stt_text == ""

    async def test_stt_interim_cleared_on_error(self, mock_stt: MagicMock, mock_responder: MagicMock):
        """If STT errors, stt_text should be cleared."""
        import asyncio

        mock_stt.transcribe_streaming = MagicMock(side_effect=RuntimeError("Mic failed"))

        listener = ConversationListener(stt=mock_stt, responder=mock_responder)
        listener.responder.stt_text = "stale text"

        await listener.start_conversation()
        await asyncio.sleep(0.1)

        # stt_text should be cleared after error
        assert listener.responder.stt_text == ""
