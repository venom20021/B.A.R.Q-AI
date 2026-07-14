"""
Tests for the streaming responder pipeline:
- _split_sentences() sentence-boundary detection
- stream_respond() token-buffering and TTS chunking
- _interrupt_requested abort behaviour
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterable
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from ai.conversation import ConversationManager

# Module under test
from ai.responder import BARQResponder, _split_sentences

# Helper: create a fake return value for _text_to_speech_both
_NP_ZERO = np.array([0.0], dtype=np.float32)


def _fake_tts_both(path: str = "/tmp/test.mp3") -> tuple:
    """Return a fake (Path, (pcm_array, sr)) for _text_to_speech_both mocks."""
    return Path(path), (_NP_ZERO, 24000)


# ═══════════════════════════════════════════════════════════════════════
# _split_sentences
# ═══════════════════════════════════════════════════════════════════════


class TestSplitSentences:
    """Unit tests for the _split_sentences helper."""

    def test_single_sentence_no_punctuation(self):
        """No punctuation → single chunk."""
        assert _split_sentences("Hello world") == ["Hello world"]

    def test_single_sentence_with_period(self):
        """One sentence ending with '.' → single chunk."""
        assert _split_sentences("Hello world.") == ["Hello world."]

    def test_split_on_period(self):
        """'.' followed by whitespace splits."""
        result = _split_sentences("First sentence. Second sentence.")
        assert result == ["First sentence.", "Second sentence."]

    def test_split_on_exclamation(self):
        """'!' followed by whitespace splits."""
        result = _split_sentences("Great! Amazing!")
        assert result == ["Great!", "Amazing!"]

    def test_split_on_question_mark(self):
        """'?' followed by whitespace splits."""
        result = _split_sentences("How are you? I am fine.")
        assert result == ["How are you?", "I am fine."]

    def test_split_on_colon(self):
        """':' followed by whitespace splits."""
        result = _split_sentences("Note: this is important.")
        assert result == ["Note:", "this is important."]

    def test_split_on_semicolon(self):
        """';' followed by whitespace splits."""
        result = _split_sentences("First part; second part.")
        assert result == ["First part;", "second part."]

    def test_split_on_comma(self):
        """',' followed by whitespace splits — user explicitly requested this."""
        result = _split_sentences("By the way, the answer is 42.")
        assert result == ["By the way,", "the answer is 42."]

    def test_multiple_commas(self):
        """Multiple commas each produce a split."""
        result = _split_sentences("First, second, and third.")
        assert result == ["First,", "second,", "and third."]

    def test_mixed_punctuation(self):
        """All punctuation types work together — commas split too."""
        text = "Hello! How are you? I'm fine, thanks. Note: check this; see?"
        result = _split_sentences(text)
        assert result == [
            "Hello!",
            "How are you?",
            "I'm fine,",
            "thanks.",
            "Note:",
            "check this;",
            "see?",
        ]

    def test_no_trailing_space(self):
        """Punctuation at end without trailing space stays with chunk."""
        result = _split_sentences("Hello.World")
        # No whitespace after '.', so no split
        assert result == ["Hello.World"]

    def test_empty_string(self):
        """Empty string → empty list."""
        assert _split_sentences("") == []

    def test_whitespace_only(self):
        """Whitespace-only → empty list."""
        assert _split_sentences("   ") == []

    def test_only_punctuation(self):
        """Just punctuation characters → kept as-is."""
        result = _split_sentences("...")
        assert result == ["..."]

    def test_trailing_whitespace_removed(self):
        """Chunks are stripped of leading/trailing whitespace."""
        result = _split_sentences("Hello.   World.  ")
        assert result == ["Hello.", "World."]

    def test_newline_as_whitespace(self):
        """Newlines after punctuation also count as whitespace split."""
        result = _split_sentences("Line one.\nLine two.\nLine three.")
        assert result == ["Line one.", "Line two.", "Line three."]


# ═══════════════════════════════════════════════════════════════════════
# stream_respond — mock helpers
# ═══════════════════════════════════════════════════════════════════════

# Use a plain MagicMock (not AsyncMock) for the LLM because stream_chat
# returns an async generator directly — AsyncMock would wrap it in a
# coroutine, causing "'async for' requires __aiter__, got coroutine".
#
# The mock's stream_chat is replaced per-test with a real async generator
# via a lambda side_effect.


def _async_gen(*tokens: str) -> AsyncIterable[str]:
    """Build a simple async generator from literal tokens."""
    async def gen():
        for t in tokens:
            yield t
    return gen()


@pytest.fixture
def responder() -> BARQResponder:
    """Return a bare responder with real ConversationManager and a
    plain MagicMock LLM (no network I/O).  stream_chat is set per-test
    via responder.llm.stream_chat.side_effect so that calling it returns
    a real async generator, not a coroutine."""
    r = BARQResponder()
    # Use MagicMock instead of AsyncMock — we need stream_chat to return
    # the raw async generator when called, not a coroutine.
    r.llm = MagicMock()
    r.speech = MagicMock()
    r.conversation = ConversationManager()
    r.conversation.start_session()
    return r


def _set_stream(responder: BARQResponder, *tokens: str) -> None:
    """Configure the mock LLM to yield the given tokens."""
    responder.llm.stream_chat.side_effect = lambda *a, **kw: _async_gen(*tokens)


# ── stream_respond: happy path ──────────────────────────────────────────


class TestStreamRespondBasic:
    """stream_respond should yield TTS chunks per sentence."""

    @patch.object(BARQResponder, "_text_to_speech_both")
    async def test_conversation_returns_chunks(self, mock_tts: AsyncMock, responder: BARQResponder):
        """LLM yields tokens → chunks are flushed per-sentence."""
        mock_tts.return_value = _fake_tts_both("/tmp/test_chunk.mp3")
        _set_stream(responder,
            "Hello", " ", "there,", " ", "world", "! ", "How", " ", "are", " ", "you", "?"
        )

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("Hello there"):
            chunks.append(chunk)

        # Tokens assemble into: "Hello there, world! How are you?"
        # Splits as: ["Hello there,", "world!", "How are you?"] → 3 chunks
        assert len(chunks) == 3
        assert chunks[0]["text"] == "Hello there,"
        assert chunks[1]["text"] == "world!"
        assert chunks[2]["text"] == "How are you?"
        assert all("audio_path" in c for c in chunks)
        assert all("audio_pcm" in c for c in chunks)
        assert mock_tts.call_count == 3

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_single_sentence_no_split(self, mock_tts: AsyncMock, responder: BARQResponder):
        """Single sentence with no punctuation → one chunk."""
        mock_tts.return_value = Path("/tmp/single.mp3")
        _set_stream(responder, "Hello there world")

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("hi"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["text"] == "Hello there world"

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_conversation_history_stored(self, mock_tts: AsyncMock, responder: BARQResponder):
        """Full response text is stored in conversation history."""
        mock_tts.return_value = Path("/tmp/history.mp3")
        _set_stream(responder, "Yes, ", "that's correct.")

        async for _ in responder.stream_respond("Is this right?"):
            pass

        # History should have user message + assistant response
        assert len(responder.conversation.history) >= 2
        assert responder.conversation.history[-1]["role"] == "assistant"
        # Tokens "Yes, " + "that's correct." → "Yes, that's correct."
        assert "Yes, that's correct." in responder.conversation.history[-1]["content"]

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_empty_llm_response_handled(self, mock_tts: AsyncMock, responder: BARQResponder):
        """Empty LLM response (no tokens) → no chunks yielded."""
        mock_tts.return_value = Path("/tmp/empty.mp3")
        _set_stream(responder)  # no tokens

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("hello"):
            chunks.append(chunk)

        assert len(chunks) == 0


# ── stream_respond: command path ─────────────────────────────────────────


class TestStreamRespondCommands:
    """Commands should use the non-streaming respond() path."""

    @patch.object(BARQResponder, "_text_to_speech")
    @patch.object(BARQResponder, "_handle_command")
    @patch.object(BARQResponder, "_classify_intent", return_value="command")
    async def test_command_uses_non_streaming_path(
        self, mock_classify: MagicMock, mock_handle: AsyncMock, mock_tts: AsyncMock,
        responder: BARQResponder,
    ):
        """Command intent → respond() called, not stream_chat."""
        mock_handle.return_value = "Opening Chrome."
        mock_tts.return_value = Path("/tmp/cmd.mp3")

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("open chrome"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Chrome" in chunks[0]["text"]
        responder.llm.stream_chat.assert_not_called()

    def test_classify_intent(self):
        """_classify_intent returns correct values."""
        r = BARQResponder()
        assert r._classify_intent("open chrome") == "command"
        assert r._classify_intent("what's the weather") == "conversation"
        assert r._classify_intent("shut up") == "command"


# ── stream_respond: interrupt abort ───────────────────────────────────────


class TestStreamRespondInterrupt:
    """Setting _interrupt_requested should abort the stream."""

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_interrupt_aborts_stream_immediately(self, mock_tts: AsyncMock, responder: BARQResponder):
        """Interrupt flag set mid-stream → stops yielding and resets."""
        mock_tts.return_value = Path("/tmp/int.mp3")
        _set_stream(responder, "First sentence. ", "Second sentence. ", "Third sentence.")

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("hello"):
            chunks.append(chunk)
            if len(chunks) == 1:
                responder._interrupt_requested = True  # abort after first chunk

        # Should only have gotten the first sentence
        assert len(chunks) == 1
        assert chunks[0]["text"] == "First sentence."
        # Flag should be reset after stream exits
        assert responder._interrupt_requested is False

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_interrupt_flag_reset_on_entry(self, mock_tts: AsyncMock, responder: BARQResponder):
        """stream_respond resets _interrupt_requested to False on entry."""
        mock_tts.return_value = Path("/tmp/int2.mp3")
        _set_stream(responder, "Some text.")
        responder._interrupt_requested = True  # Set stale flag

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("hello"):
            chunks.append(chunk)

        # stream_respond resets the flag → stream proceeds normally
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Some text."
        assert responder._interrupt_requested is False

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_interrupt_resets_flags_on_exit(self, mock_tts: AsyncMock, responder: BARQResponder):
        """After stream_respond completes (normally or interrupted), flags are reset."""
        mock_tts.return_value = Path("/tmp/int3.mp3")
        _set_stream(responder, "Hello world.")

        assert responder.is_processing is False
        assert responder._interrupt_requested is False

        async for chunk in responder.stream_respond("hi"):
            assert responder.is_processing is True

        assert responder.is_processing is False
        assert responder._interrupt_requested is False


# ── stream_respond: error handling ────────────────────────────────────────


class TestStreamRespondErrors:
    """Error resilience of the streaming pipeline."""

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_llm_stream_error_fallback(self, mock_tts: AsyncMock, responder: BARQResponder):
        """If LLM raises, a fallback text is yielded."""
        mock_tts.return_value = Path("/tmp/err.mp3")

        async def broken_stream():
            raise RuntimeError("LLM unreachable")
            yield  # pragma: no cover

        responder.llm.stream_chat.side_effect = lambda *a, **kw: broken_stream()

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("hello"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "error" in chunks[0]["text"].lower() or "sorry" in chunks[0]["text"].lower()

    @patch.object(BARQResponder, "_text_to_speech_both")
    async def test_tts_error_handled_gracefully(self, mock_tts: AsyncMock, responder: BARQResponder):
        """When TTS fails mid-stream, the error is caught and flags reset.
        (The broad except Exception in stream_respond catches TTS errors.)"""
        call_count = 0

        async def tts_side_effect(text: str) -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("TTS failure")
            return _fake_tts_both("/tmp/ok.mp3")

        mock_tts.side_effect = tts_side_effect
        _set_stream(responder, "First chunk. ", "Second chunk.")

        # TTS raises on first call — stream_respond catches it gracefully.
        # The stream completes without propagating the error.
        chunks: list[dict] = []
        async for chunk in responder.stream_respond("hello"):
            chunks.append(chunk)

        # The except handler catches the TTS error on "First chunk." but
        # does NOT return (full_text is non-empty). Execution continues
        # to flush the remaining buffer "Second chunk." which succeeds.
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Second chunk."

        # Flags reset even though TTS failed mid-stream
        assert responder.is_processing is False
        assert responder._interrupt_requested is False

    @patch.object(BARQResponder, "_text_to_speech")
    async def test_partial_tokens_on_llm_error(self, mock_tts: AsyncMock, responder: BARQResponder):
        """If LLM errors mid-stream with partial output, the partial is preserved."""
        mock_tts.return_value = Path("/tmp/partial.mp3")

        async def partial_then_error():
            yield "This is partial "
            yield "output"
            raise RuntimeError("Connection lost")

        responder.llm.stream_chat.side_effect = lambda *a, **kw: partial_then_error()

        chunks: list[dict] = []
        async for chunk in responder.stream_respond("hello"):
            chunks.append(chunk)

        # The partial "This is partial output" should be flushed since
        # full_text is non-empty — the except handler won't override it,
        # and execution continues to the flush-remaining-buffer step.
        assert len(chunks) >= 1
        assert any("partial" in c["text"] for c in chunks)


# ── _handle_command: agent_task paths ──────────────────────────────────────


class TestHandleCommandAgentTask:
    """Tests for the agent_task path in _handle_command.

    The _handle_command method in responder.py routes complex goals to
    AgentExecutor. When agent execution fails, it falls back to the LLM
    for a conversational response, and finally to a static message.
    """

    @patch("voice.routes._parse_and_route")
    @patch("agent.agent_executor.AgentExecutor")
    async def test_agent_task_executes_via_executor(
        self, mock_executor_cls: MagicMock, mock_parse: AsyncMock, responder: BARQResponder,
    ):
        """agent_task action should execute AgentExecutor and return its result."""
        # _parse_and_route returns agent_task action
        mock_parse.return_value = {
            "action": "agent_task",
            "goal": "research quantum computing and save to file",
            "status": "triggered",
        }
        # AgentExecutor returns a successful result
        mock_executor_instance = AsyncMock()
        mock_executor_instance.execute.return_value = "I researched quantum computing and saved the results."
        mock_executor_cls.return_value = mock_executor_instance

        result = await responder._handle_command("research quantum computing and save to file")

        assert "quantum computing" in result
        assert "saved" in result.lower()
        mock_parse.assert_awaited_once()
        mock_executor_instance.execute.assert_awaited_once_with(
            goal="research quantum computing and save to file"
        )

    @patch("voice.routes._parse_and_route")
    @patch("agent.agent_executor.AgentExecutor")
    async def test_agent_task_falls_back_to_llm_on_executor_error(
        self, mock_executor_cls: MagicMock, mock_parse: AsyncMock, responder: BARQResponder,
    ):
        """When AgentExecutor raises, _handle_command falls back to the LLM."""
        mock_parse.return_value = {
            "action": "agent_task",
            "goal": "analyze this data and create a report",
            "status": "triggered",
        }
        # AgentExecutor raises
        mock_executor_instance = AsyncMock()
        mock_executor_instance.execute.side_effect = RuntimeError("LLM backend unavailable")
        mock_executor_cls.return_value = mock_executor_instance

        # Configure the LLM chat to return a fallback response
        responder.llm.chat = AsyncMock(return_value="Let me analyze that data for you now.")

        result = await responder._handle_command("analyze this data and create a report")

        assert "analyze" in result.lower() or "data" in result.lower()
        # LLM should have been called as the fallback
        responder.llm.chat.assert_awaited_once()

    @patch("voice.routes._parse_and_route")
    @patch("agent.agent_executor.AgentExecutor")
    async def test_agent_task_static_fallback_when_both_fail(
        self, mock_executor_cls: MagicMock, mock_parse: AsyncMock, responder: BARQResponder,
    ):
        """When both AgentExecutor and LLM fail, return the static fallback message."""
        mock_parse.return_value = {
            "action": "agent_task",
            "goal": "plan a trip to Paris",
            "status": "triggered",
        }
        # AgentExecutor raises
        mock_executor_instance = AsyncMock()
        mock_executor_instance.execute.side_effect = RuntimeError("Agent timeout")
        mock_executor_cls.return_value = mock_executor_instance

        # LLM also raises
        responder.llm.chat = AsyncMock(side_effect=RuntimeError("LLM also down"))

        result = await responder._handle_command("plan a trip to Paris")

        # Static fallback message
        assert "work on that" in result.lower() or "let you know" in result.lower()

    @patch("voice.routes._parse_and_route")
    @patch("agent.agent_executor.AgentExecutor")
    async def test_agent_task_goal_uses_command_as_fallback(
        self, mock_executor_cls: MagicMock, mock_parse: AsyncMock, responder: BARQResponder,
    ):
        """When _parse_and_route returns agent_task without a 'goal' key
        (edge case), _handle_command should use the original text as the goal."""
        # Simulate parse returning agent_task without a 'goal' key
        mock_parse.return_value = {
            "action": "agent_task",
            "status": "triggered",
            # No 'goal' key — _handle_command should fall back to command text
        }
        mock_executor_instance = AsyncMock()
        mock_executor_instance.execute.return_value = "Done."
        mock_executor_cls.return_value = mock_executor_instance

        await responder._handle_command("find the best laptop deals and compare them")

        # When goal is missing from parse result, _handle_command uses
        # result.get("goal", text) — falls back to the original command text
        mock_executor_instance.execute.assert_awaited_once_with(
            goal="find the best laptop deals and compare them"
        )

    @patch("voice.routes._parse_and_route")
    @patch("agent.agent_executor.AgentExecutor")
    async def test_agent_task_non_agent_command_not_routed(
        self, mock_executor_cls: MagicMock, mock_parse: AsyncMock, responder: BARQResponder,
    ):
        """Non-agent_task actions should NOT call AgentExecutor."""
        mock_parse.return_value = {
            "action": "web_search",
            "query": "quantum computing",
            "status": "parsed",
        }

        _ = await responder._handle_command("search for quantum computing")

        # AgentExecutor should NOT have been created for non-agent_task actions
        mock_executor_cls.assert_not_called()


# ── _handle_command: exit phrases ──────────────────────────────────────────


class TestHandleCommandExitPhrases:
    """Exit phrases should end the conversation and return a goodbye message."""

    async def test_exit_phrase_goodbye(self, responder: BARQResponder):
        """'goodbye' should end the session and return a goodbye message."""
        assert responder.conversation.is_active
        result = await responder._handle_command("goodbye")
        assert "goodbye" in result.lower()
        assert "computer" in result.lower()
        # Session should be ended
        assert not responder.conversation.is_active

    async def test_exit_phrase_nothing(self, responder: BARQResponder):
        """'nothing' should end the session."""
        result = await responder._handle_command("nothing")
        assert "goodbye" in result.lower()

    async def test_exit_phrase_go_to_sleep(self, responder: BARQResponder):
        """'go to sleep' should end the session."""
        result = await responder._handle_command("go to sleep")
        assert "goodbye" in result.lower()

    async def test_exit_phrase_not_in_normal_command(self, responder: BARQResponder):
        """A normal command that doesn't contain any exit phrase should not trigger exits.

        Uses 'what is the weather' which contains no exit phrase substrings
        (nothing, goodbye, bye, exit, end, stop, that's, we're, go to, that's it)."""
        result = await responder._handle_command("what is the weather")
        assert result is not None
        # Session should still be active since no exit phrase was triggered
        assert responder.conversation.is_active
