"""
Tests for the "mic stays muted after greeting" fix.

Root cause: after the agent finishes its greeting, ``_agent_is_speaking``
(Deepgram) / ``_is_speaking`` (Gemini) could remain True indefinitely when
the turn-end signal (AgentAudioDone / turn_complete) never arrives, so the
mic audio gate stays shut and BARQ stops listening.

Fix covered here:
1. Deepgram: a tail-timer restarts on every audio chunk and reopens the mic
   ~1.2s after agent audio stops, even without AgentAudioDone.
2. Deepgram: UserStartedSpeaking (server-side VAD) reopens the mic instantly.
3. Deepgram: AgentAudioDone uses the short tail delay instead of 6s.
4. Gemini: idle safety net reopens the mic when no audio for >1.2s even
   without turn_complete.
"""

import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 480 int16 samples (960 bytes) at 24kHz — a normal agent audio chunk
AUDIO_CHUNK = b"\x00\x00" * 480


# ─── DeepgramVoiceAgent ───────────────────────────────────────────────────


class TestDeepgramMicReopen:
    """Tail-timer + instant-reopen behavior in DeepgramVoiceAgent."""

    @pytest.fixture
    def agent(self):
        from voice.deepgram_agent import DeepgramVoiceAgent
        return DeepgramVoiceAgent(api_key="test-key")

    @pytest.mark.asyncio
    async def test_audio_chunk_starts_tail_timer(self, agent):
        """Incoming agent audio sets _agent_is_speaking and starts a tail timer."""
        agent._agent_is_speaking = False
        await agent._handle_audio_bytes(AUDIO_CHUNK)
        assert agent._agent_is_speaking is True
        assert agent._mic_cooldown_task is not None

    @pytest.mark.asyncio
    async def test_tail_timer_reopens_mic_without_agent_audio_done(self, agent):
        """Mic reopens ~delay after audio stops even if AgentAudioDone never fires.

        This is the primary fix: previously a missing AgentAudioDone would
        leave the mic muted forever.
        """
        agent._mic_tail_delay = 0.05
        await agent._handle_audio_bytes(AUDIO_CHUNK)
        assert agent._agent_is_speaking is True
        await asyncio.sleep(0.2)
        assert agent._agent_is_speaking is False

    @pytest.mark.asyncio
    async def test_new_audio_restarts_tail_timer(self, agent):
        """Each new audio chunk extends the mute window (timer restarts)."""
        agent._mic_tail_delay = 0.1
        await agent._handle_audio_bytes(AUDIO_CHUNK)
        # Second chunk arrives mid-window — timer restarts
        await asyncio.sleep(0.05)
        await agent._handle_audio_bytes(AUDIO_CHUNK)
        # Still muted shortly after the 2nd chunk
        await asyncio.sleep(0.05)
        assert agent._agent_is_speaking is True
        # Then reopens after the restarted timer elapses
        await asyncio.sleep(0.15)
        assert agent._agent_is_speaking is False

    @pytest.mark.asyncio
    async def test_user_started_speaking_reopens_mic_instantly(self, agent):
        """Deepgram's server-side VAD (UserStartedSpeaking) un-mutes immediately."""
        agent._mic_tail_delay = 60.0  # long window; must be overridden
        await agent._handle_audio_bytes(AUDIO_CHUNK)
        assert agent._agent_is_speaking is True

        await agent._handle_json_message({"type": "UserStartedSpeaking"})
        assert agent._agent_is_speaking is False

    @pytest.mark.asyncio
    async def test_agent_audio_done_uses_short_tail(self, agent):
        """AgentAudioDone triggers the short tail timer, not a 6s mute."""
        agent._mic_tail_delay = 0.05
        await agent._handle_audio_bytes(AUDIO_CHUNK)
        assert agent._agent_is_speaking is True

        await agent._handle_json_message({"type": "AgentAudioDone"})
        await asyncio.sleep(0.2)
        assert agent._agent_is_speaking is False

    @pytest.mark.asyncio
    async def test_tail_timer_cancelled_on_stop(self, agent):
        """stop() cancels the pending tail timer so no zombie reopen happens."""
        await agent._handle_audio_bytes(AUDIO_CHUNK)
        assert agent._mic_cooldown_task is not None
        await agent.stop()
        assert agent._mic_cooldown_task is None or agent._mic_cooldown_task.done()


# ─── GeminiVoiceAgent ─────────────────────────────────────────────────────


class TestGeminiMicReopen:
    """Idle safety net in GeminiVoiceAgent."""

    @pytest.fixture
    def agent(self):
        pytest.importorskip("google.genai")
        from voice.gemini_agent import GeminiVoiceAgent
        return GeminiVoiceAgent(api_key="test-key")

    def test_reopen_needed_when_idle_and_speaking(self, agent):
        """No audio for >delay while speaking + empty queue → reopen needed."""
        agent._is_speaking = True
        agent._last_audio_at = time.time() - 2.0
        agent._mic_reopen_delay = 1.2
        assert agent._mic_reopen_needed() is True

    def test_no_reopen_when_recent_audio(self, agent):
        """Fresh audio means the agent is still speaking → no reopen."""
        agent._is_speaking = True
        agent._last_audio_at = time.time()
        agent._mic_reopen_delay = 1.2
        assert agent._mic_reopen_needed() is False

    def test_no_reopen_when_not_speaking(self, agent):
        """Not speaking → nothing to reopen."""
        agent._is_speaking = False
        agent._last_audio_at = time.time() - 5.0
        agent._mic_reopen_delay = 1.2
        assert agent._mic_reopen_needed() is False

    def test_no_reopen_when_queue_has_pending_audio(self, agent):
        """Queue not empty → audio still pending → don't reopen."""
        agent._is_speaking = True
        agent._last_audio_at = time.time() - 5.0
        agent._mic_reopen_delay = 1.2
        agent._audio_in_queue.put_nowait(b"\x00" * 480)
        try:
            assert agent._mic_reopen_needed() is False
        finally:
            agent._audio_in_queue.get_nowait()
