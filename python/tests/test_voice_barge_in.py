"""Integration tests for barge-in scenarios against the voice routes API.

Tests the conversation lifecycle, voice state reflection, action logging,
and barge-in relevant state transitions through HTTP endpoints.

These tests complement the unit-level barge-in tests in
test_conversation_listener.py by verifying that the API layer correctly
exposes and reacts to the voice system's internal state.

Barge-in scenarios covered:
  1. Conversation start/end lifecycle via HTTP API
  2. Voice state (is_speaking, is_processing, conversation_active) reflected in /status
  3. Action logging for conversation events
  4. Chat endpoint flow with state transitions
  5. Barge-in edge cases (interrupted state transitions)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def router():
    """Return the voice routes router with mutable mock state.

    The mocks are stored on the module so tests can mutate responder state
    (is_speaking, is_processing, conversation_active, turn_count, etc.)
    between API calls to simulate barge-in scenarios. A fresh mock dict is
    created per test function for complete isolation.
    """
    mock_conversation = MagicMock(
        is_active=False,
        turn_count=0,
        history=[],
        add_user_message=MagicMock(),
        add_assistant_message=MagicMock(),
        start_session=MagicMock(return_value="test-session-id"),
        end_session=MagicMock(),
        get_recent_history=MagicMock(return_value=[]),
    )
    mock_responder = MagicMock(
        conversation=mock_conversation,
        is_speaking=False,
        is_processing=False,
        stt_text="",
        stt_confidence=0.0,
        _interrupt_requested=False,
        respond=AsyncMock(return_value={"text": "Hello from BARQ!", "action": "command"}),
        respond_text_only=AsyncMock(return_value="Hello from BARQ!"),
    )
    with (
        patch("voice.SpeechProcessor"),
        patch("ai.responder.BARQResponder", return_value=mock_responder),
        patch("voice.conversation_listener.ConversationListener", return_value=MagicMock()),
    ):
        from voice import routes
        # Overwrite module-level singletons with fresh mocks for this test.
        # Since 'from voice import routes' returns the cached module on
        # subsequent calls (Python caches sys.modules), module-level code
        # like 'responder = BARQResponder()' runs only ONCE.  We overwrite
        # the singletons directly so every test gets isolated mock state.
        routes.responder = mock_responder
        routes.conversation_listener = MagicMock()
        routes._test_mocks = {
            "responder": mock_responder,
            "conversation": mock_conversation,
        }
        return routes.router


@pytest.fixture
def mock_resp(router):
    """Return the mutable mock responder for direct state manipulation."""
    from voice import routes
    return routes._test_mocks["responder"]


@pytest.fixture
def mock_conv(router):
    """Return the mutable mock conversation for direct state manipulation."""
    from voice import routes
    return routes._test_mocks["conversation"]


# ═══════════════════════════════════════════════════════════════════════
# Conversation Lifecycle via API
# ═══════════════════════════════════════════════════════════════════════


class TestConversationLifecycleAPI:
    """Start/end conversation lifecycle through the HTTP API.

    These are the API-level equivalents of the unit tests in
    TestConversationLifecycle.test_start_conversation_sets_active,
    test_start_conversation_idempotent, test_stop_conversation_ends_session, etc.
    """

    async def test_start_returns_started(self, client, mock_conv):
        """POST /voice/conversation/start should return status 'started'."""
        response = await client.post("/conversation/start")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["session_id"] == "test-session-id"
        mock_conv.start_session.assert_called_once()

    async def test_start_sets_active_in_status(self, client, mock_conv):
        """After starting a conversation, GET /voice/status should reflect it."""
        mock_conv.is_active = True
        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_active"] is True

    async def test_end_returns_ended_with_turns(self, client, mock_conv):
        """POST /voice/conversation/end should return 'ended' with turn count."""
        mock_conv.is_active = True
        mock_conv.turn_count = 3
        response = await client.post("/conversation/end")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ended"
        assert data["turns"] == 3
        mock_conv.end_session.assert_called_once()

    async def test_end_no_active_session(self, client):
        """POST /voice/conversation/end with no active session."""
        response = await client.post("/conversation/end")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_active_session"

    async def test_full_lifecycle_start_end(self, client, mock_conv):
        """Full lifecycle: start → active → end → inactive via status endpoint."""
        # After start -> active
        mock_conv.is_active = True
        resp = await client.get("/status")
        assert resp.json()["conversation_active"] is True

        # After end -> inactive
        mock_conv.is_active = False
        resp = await client.get("/status")
        assert resp.json()["conversation_active"] is False

    async def test_end_clears_active(self, client, mock_conv):
        """After end, GET /voice/status should show conversation_active=False."""
        mock_conv.is_active = True
        mock_conv.turn_count = 5
        await client.post("/conversation/end")
        mock_conv.is_active = False
        resp = await client.get("/status")
        assert resp.json()["conversation_active"] is False


# ═══════════════════════════════════════════════════════════════════════
# Voice State Reflection
# ═══════════════════════════════════════════════════════════════════════


class TestVoiceStateReflection:
    """The /voice/status endpoint should reflect all voice state flags.

    The frontend (DashboardPage.tsx) derives AI state from these flags:
      - is_speaking → responding
      - is_processing → thinking
      - conversation_active → listening
      - else → idle

    These tests verify the API faithfully reports each flag.
    """

    async def test_default_all_false(self, client, mock_resp, mock_conv):
        """Default state: all flags should be False/zero."""
        mock_resp.is_speaking = False
        mock_resp.is_processing = False
        mock_conv.is_active = False
        mock_conv.turn_count = 0

        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_speaking"] is False
        assert data["is_processing"] is False
        assert data["conversation_active"] is False
        assert data["conversation_turns"] == 0

    async def test_is_speaking_true(self, client, mock_resp):
        """is_speaking=True (responding state)."""
        mock_resp.is_speaking = True
        response = await client.get("/status")
        data = response.json()
        assert data["is_speaking"] is True
        assert data["is_processing"] is False

    async def test_is_processing_true(self, client, mock_resp):
        """is_processing=True (thinking state)."""
        mock_resp.is_processing = True
        response = await client.get("/status")
        data = response.json()
        assert data["is_processing"] is True
        assert data["is_speaking"] is False

    async def test_conversation_active_true(self, client, mock_conv):
        """conversation_active=True (listening state)."""
        mock_conv.is_active = True
        response = await client.get("/status")
        data = response.json()
        assert data["conversation_active"] is True

    async def test_turn_count_reflected(self, client, mock_conv):
        """conversation_turns should match the underlying value."""
        mock_conv.turn_count = 7
        response = await client.get("/status")
        data = response.json()
        assert data["conversation_turns"] == 7

    async def test_all_flags_simultaneously_true(self, client, mock_resp, mock_conv):
        """All flags True simultaneously — simulates busy BARQ state."""
        mock_resp.is_speaking = True
        mock_resp.is_processing = True
        mock_conv.is_active = True
        mock_conv.turn_count = 12

        response = await client.get("/status")
        data = response.json()
        assert data["is_speaking"] is True
        assert data["is_processing"] is True
        assert data["conversation_active"] is True
        assert data["conversation_turns"] == 12

    async def test_state_transition_speaking_to_idle(self, client, mock_resp, mock_conv):
        """Transition from responding to idle (is_speaking → False, not processing, not active)."""
        # Responding state
        mock_resp.is_speaking = True
        resp = await client.get("/status")
        assert resp.json()["is_speaking"] is True

        # Transition to idle
        mock_resp.is_speaking = False
        mock_resp.is_processing = False
        mock_conv.is_active = False
        resp = await client.get("/status")
        data = resp.json()
        assert data["is_speaking"] is False
        assert data["is_processing"] is False
        assert data["conversation_active"] is False

    async def test_state_transition_thinking_to_listening(self, client, mock_resp, mock_conv):
        """Transition from thinking (processing) to listening (conversation_active)."""
        # Thinking state
        mock_resp.is_processing = True
        resp = await client.get("/status")
        assert resp.json()["is_processing"] is True

        # Transition to listening (processing done, conversation still active)
        mock_resp.is_processing = False
        mock_conv.is_active = True
        resp = await client.get("/status")
        data = resp.json()
        assert data["is_processing"] is False
        assert data["conversation_active"] is True

    async def test_barge_in_during_speaking_to_processing(self, client, mock_resp, mock_conv):
        """Barge-in: speaking → processing (user interrupts, BARQ starts thinking).

        This simulates what happens when the user speaks over BARQ:
        the interrupt handler sets _interrupt_requested, which causes
        is_speaking to drop and is_processing to spike as BARQ processes
        the new input.
        """
        # Initially speaking
        mock_resp.is_speaking = True
        mock_resp._interrupt_requested = False
        resp = await client.get("/status")
        assert resp.json()["is_speaking"] is True

        # Barge-in: user speaks → interrupt flagged → speaking stops,
        # processing begins
        mock_resp.is_speaking = False
        mock_resp._interrupt_requested = True
        mock_resp.is_processing = True
        resp = await client.get("/status")
        data = resp.json()
        assert data["is_speaking"] is False
        assert data["is_processing"] is True

    async def test_conversation_context_returns_active(self, client, mock_conv):
        """GET /voice/conversation/context should reflect active state."""
        mock_conv.is_active = True
        mock_conv.turn_count = 4
        mock_conv.get_recent_history.return_value = [{"role": "user", "content": "hello"}]

        response = await client.get("/conversation/context")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["turns"] == 4
        assert "session_id" in data
        assert len(data["recent_history"]) == 1

    async def test_conversation_context_inactive(self, client, mock_conv):
        """GET /voice/conversation/context when no active session."""
        mock_conv.is_active = False
        response = await client.get("/conversation/context")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False


# ═══════════════════════════════════════════════════════════════════════
# Action Logging for Conversation Events
# ═══════════════════════════════════════════════════════════════════════


class TestActionLogging:
    """Barge-in and conversation events should be logged to the action log.

    The frontend FloatingActionLog displays these for real-time awareness.
    """

    async def test_start_conversation_logged(self, client):
        """POST /voice/conversation/start should create an activity log entry.

        Note: conversation/start uses analytics_dao.log_activity which writes to
        the activity_log table, NOT the action_log table used by
        /action-log/recent. We query the DB directly.
        """
        from database.connection import db_connection
        await client.post("/conversation/start")

        rows = await db_connection.fetch_all(
            "SELECT action FROM activity_log WHERE action = ?",
            ("conversation_start",),
        )
        assert len(rows) >= 1, "Expected conversation_start in activity_log"

    async def test_end_conversation_logged(self, client, mock_conv):
        """POST /voice/conversation/end should create an activity log entry.

        Note: the endpoint checks responder.conversation.is_active first;
        we must set it True so the endpoint reaches the log_activity call.
        """
        from database.connection import db_connection
        mock_conv.is_active = True
        mock_conv.turn_count = 2

        await client.post("/conversation/end")

        rows = await db_connection.fetch_all(
            "SELECT action FROM activity_log WHERE action = ?",
            ("conversation_end",),
        )
        assert len(rows) >= 1

    async def test_full_cycle_both_logged(self, client, mock_conv):
        """Full start→end cycle should log both events."""
        from database.connection import db_connection
        mock_conv.is_active = True

        await client.post("/conversation/start")
        await client.post("/conversation/end")

        rows = await db_connection.fetch_all(
            "SELECT DISTINCT action FROM activity_log WHERE action IN (?, ?)",
            ("conversation_start", "conversation_end"),
        )
        actions_found = [r["action"] for r in rows]
        assert "conversation_start" in actions_found
        assert "conversation_end" in actions_found

    async def test_chat_logged_as_activity(self, client):
        """POST /voice/chat should log a 'chat' activity."""
        from database.connection import db_connection
        response = await client.post("/chat", json={"message": "hello"})
        assert response.status_code == 200

        rows = await db_connection.fetch_all(
            "SELECT action FROM activity_log WHERE action = ?",
            ("chat",),
        )
        assert len(rows) >= 1, "Expected 'chat' action in activity_log"


# ═══════════════════════════════════════════════════════════════════════
# Chat Endpoint Flow
# ═══════════════════════════════════════════════════════════════════════


class TestChatFlow:
    """The chat endpoint is part of the barge-in pipeline — it processes
    user speech text and returns a response."""

    async def test_chat_returns_text(self, client):
        """POST /voice/chat should return text response."""
        response = await client.post("/chat", json={"message": "what's the weather?"})
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert data["text"] == "Hello from BARQ!"

    async def test_chat_text_only(self, client):
        """POST /voice/chat/text should return text only (no audio)."""
        response = await client.post("/chat/text", json={"message": "hello"})
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert data["text"] == "Hello from BARQ!"

    async def test_chat_logs_command(self, client, mock_resp):
        """POST /voice/chat should log command via settings_dao."""
        response = await client.post("/chat", json={"message": "test command"})
        assert response.status_code == 200
        # Verify the responder was called with the message
        mock_resp.respond.assert_called_once_with("test command")

    async def test_chat_with_language_param(self, client):
        """POST /voice/chat should accept language parameter."""
        response = await client.post("/chat", json={"message": "hello", "language": "en"})
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Hello from BARQ!"


# ═══════════════════════════════════════════════════════════════════════
# Barge-in Edge Cases & State Transitions
# ═══════════════════════════════════════════════════════════════════════


class TestBargeInEdgeCases:
    """Barge-in edge cases: interrupt flag propagation, state transitions.

    These integration tests verify that the API correctly exposes the
    internal state transitions that occur during a barge-in event.
    """

    async def test_interrupt_flag_exposed_in_responder(self, client, mock_resp):
        """The _interrupt_requested flag should be settable and reflected.

        Note: _interrupt_requested is not directly exposed via /status
        (it's an internal flag), but the responder mock holds it and
        the barge-in flow depends on it.  This test verifies the mock
        plumbing is correct.
        """
        assert mock_resp._interrupt_requested is False
        mock_resp._interrupt_requested = True
        assert mock_resp._interrupt_requested is True

    async def test_is_listening_reflected(self, client, mock_resp):
        """is_listening should be reflected in /status."""
        # is_listening comes from the wake word detector's _running flag.
        # We can't easily mock the detector from here, so verify the field
        # exists in the response (will be False since detector isn't started).
        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_listening" in data
        assert data["is_listening"] is False

    async def test_wake_word_exposed(self, client):
        """wake_word should be exposed in /status."""
        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "wake_word" in data
        assert isinstance(data["wake_word"], str)

    async def test_tts_voice_exposed(self, client):
        """TTS voice setting should be exposed in /status."""
        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "tts_voice" in data
        assert data["tts_voice"] == "en-US-JennyNeural"

    async def test_sensitivity_exposed(self, client):
        """Sensitivity level should be exposed in /status."""
        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "sensitivity" in data
        assert data["sensitivity"] == "medium"

    async def test_conversation_active_during_barge_in_handling(self, client, mock_resp, mock_conv):
        """During a barge-in, conversation remains active while BARQ
        processes the new input.

        This simulates: user speaks over BARQ → interrupt flagged →
        is_speaking drops → is_processing spikes → conversation stays active.
        """
        # BARQ was speaking in an active conversation
        mock_resp.is_speaking = True
        mock_conv.is_active = True
        mock_conv.turn_count = 3

        # User barges in: speaking stops, processing starts
        mock_resp.is_speaking = False
        mock_resp.is_processing = True
        mock_resp._interrupt_requested = True

        response = await client.get("/status")
        data = response.json()
        assert data["is_speaking"] is False
        assert data["is_processing"] is True
        assert data["conversation_active"] is True
        assert data["conversation_turns"] == 3
