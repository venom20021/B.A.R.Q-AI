"""
Integration tests for the conversation listener:

  - start_conversation() / stop_conversation() lifecycle
  - Exit command detection (_is_exit_command)
  - is_active property
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# Override the conftest.py autouse DB fixture — these tests are pure
# function tests and do not need a database connection.
@pytest.fixture(autouse=True)
def setup_db():
    """Override conftest's autouse DB fixture — no DB needed for these tests."""
    return


from voice.conversation_listener import (  # noqa: E402
    ConversationListener,
)

# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_stt() -> MagicMock:
    """Mock SpeechProcessor."""
    stt = MagicMock()
    return stt


@pytest.fixture
def mock_responder() -> MagicMock:
    """Mock BARQResponder with conversation, is_speaking, etc."""
    resp = MagicMock()
    resp.conversation = MagicMock()
    resp.conversation.is_active = False
    resp.conversation.start_session = MagicMock()
    resp.conversation.end_session = MagicMock()
    resp.is_speaking = False
    resp.is_processing = False
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
# Lifecycle
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

        # Cancel the loop task directly
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
# Exit Command Detection
# ═══════════════════════════════════════════════════════════════════════


class TestExitCommand:
    """_is_exit_command should detect various exit phrases."""

    @pytest.fixture
    def listener_no_mocks(self) -> ConversationListener:
        """Pure ConversationListener with bare mocks for exit command test only."""
        return ConversationListener(stt=MagicMock(), responder=MagicMock())

    @pytest.mark.parametrize("phrase", [
        "nothing",
        "that's all",
        "we're done",
        "end conversation",
        "stop conversation",
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
        ("nothing else matters", True),  # "nothing" is a whole word
        ("I said nothing", True),        # "nothing" at end
        ("stop right there", False),     # "stop" not in exit list
        ("conversation piece", False),   # no whole-word exit phrase match
        ("let's end this", False),       # "end conversation" not present
        ("I'm done", False),             # "we're done" doesn't match "I'm done"
        ("we're done here", True),       # "we're done" at start
        ("end conversation now", True),  # "end conversation" at start
        ("shut down the system", True),  # "shut down" is in exit list, whole-word match
        ("go to sleep now", True),       # "go to sleep" at start
        ("that's it for now thanks", True),  # "that's it for now" multi-word
    ])
    def test_partial_match_still_detected(self, listener_no_mocks: ConversationListener, phrase: str, expected: bool):
        """Phrases containing exit keywords as whole words should match (or not)."""
        result = listener_no_mocks._is_exit_command(phrase)
        assert result is expected, f"'{phrase}' should {'match' if expected else 'not match'}"

    @pytest.mark.parametrize("phrase", [
        "hello", "what's the weather", "open chrome", "tell me a joke",
        "continue", "keep going", "stay", "good", "bye", "going to sleep",
        "goodbye", "bye bye", "never mind",
    ])
    def test_non_exit_phrases_not_detected(self, listener_no_mocks: ConversationListener, phrase: str):
        """Non-exit phrases should NOT trigger exit detection."""
        assert listener_no_mocks._is_exit_command(phrase) is False

    def test_exit_command_full_word_boundary(self, listener_no_mocks: ConversationListener):
        """'nothing' should match, but 'no' alone should not (word boundary)."""
        assert listener_no_mocks._is_exit_command("nothing") is True
        assert listener_no_mocks._is_exit_command("no") is False
        assert listener_no_mocks._is_exit_command("nothing at all") is True

    def test_exit_phrase_in_sentence(self, listener_no_mocks: ConversationListener):
        """Exit phrase embedded in a longer sentence should still match."""
        text = "I think that's all for now"
        assert listener_no_mocks._is_exit_command(text) is True

    def test_empty_string_not_exit(self, listener_no_mocks: ConversationListener):
        """Empty string should not be exit."""
        assert listener_no_mocks._is_exit_command("") is False
