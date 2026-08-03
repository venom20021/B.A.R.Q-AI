"""
Tests for the mic RMS energy threshold (voice-activity gate).

Covers:
1. DeepgramVoiceAgent._load_energy_threshold() — DB → env → default resolution
2. DeepgramVoiceAgent.set_energy_threshold() — clamping to [50, 2000]
3. DeepgramVoiceAgent._audio_capture_callback() — drops low-RMS chunks, passes loud ones
4. PipecatVoiceAgent equivalents
5. routes._apply_energy_threshold() — pushes threshold to the live voice agent
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ─── Helpers ──────────────────────────────────────────────────────────────


def _silent_chunk(samples: int = 2400, channels: int = 1) -> np.ndarray:
    """Return a silent int16 audio chunk (RMS ≈ 0)."""
    return np.zeros((samples, channels), dtype=np.int16)


def _loud_chunk(amplitude: int = 8000, samples: int = 2400, channels: int = 1) -> np.ndarray:
    """Return a loud int16 audio chunk (RMS ≈ amplitude)."""
    return np.full((samples, channels), amplitude, dtype=np.int16)


def _quiet_chunk(amplitude: int = 100, samples: int = 2400, channels: int = 1) -> np.ndarray:
    """Return a quiet int16 audio chunk (RMS ≈ amplitude, below typical thresholds)."""
    return np.full((samples, channels), amplitude, dtype=np.int16)


def _patch_get_setting(return_value=None, side_effect=None):
    """Patch SettingsDAO.get_setting (class method) for threshold resolution tests.

    NOTE: patching ``database.settings_dao.get_setting`` fails because
    unittest.mock resolves ``database.settings_dao`` to the *module*
    ``python/database/settings_dao.py`` (via importlib), and the module has
    no ``get_setting`` attribute — it's a method on the SettingsDAO class.
    We patch the class method instead, which the singleton instance inherits.
    """
    target = "database.settings_dao.SettingsDAO.get_setting"
    return patch(target, new=AsyncMock(return_value=return_value, side_effect=side_effect))


# ─── DeepgramVoiceAgent ───────────────────────────────────────────────────


class TestDeepgramEnergyThreshold:
    """Test threshold loading, clamping, and audio gating in DeepgramVoiceAgent."""

    @pytest.fixture
    def agent(self):
        from voice.deepgram_agent import DeepgramVoiceAgent
        return DeepgramVoiceAgent(api_key="test-key")

    @pytest.mark.asyncio
    async def test_default_threshold_when_no_setting(self, agent, monkeypatch):
        """No DB setting and no env var → default 250."""
        monkeypatch.delenv("VAD_ENERGY_THRESHOLD", raising=False)
        with _patch_get_setting(return_value=None):
            await agent._load_energy_threshold()
        assert agent._energy_threshold == 250

    @pytest.mark.asyncio
    async def test_threshold_loaded_from_db(self, agent):
        """DB setting takes priority over env var."""
        with _patch_get_setting(return_value="850"):
            await agent._load_energy_threshold()
        assert agent._energy_threshold == 850

    @pytest.mark.asyncio
    async def test_threshold_env_fallback(self, agent, monkeypatch):
        """No DB setting but env var set → env value used."""
        monkeypatch.setenv("VAD_ENERGY_THRESHOLD", "600")
        with _patch_get_setting(return_value=None):
            await agent._load_energy_threshold()
        assert agent._energy_threshold == 600

    @pytest.mark.asyncio
    async def test_threshold_invalid_db_value_ignored(self, agent):
        """Non-numeric DB value is ignored, keeping default."""
        with _patch_get_setting(return_value="not-a-number"):
            await agent._load_energy_threshold()
        assert agent._energy_threshold == 250

    @pytest.mark.asyncio
    async def test_threshold_db_error_falls_back(self, agent, monkeypatch):
        """DB read exception falls back to env, then default."""
        monkeypatch.delenv("VAD_ENERGY_THRESHOLD", raising=False)
        with _patch_get_setting(side_effect=RuntimeError("db down")):
            await agent._load_energy_threshold()
        assert agent._energy_threshold == 250

    def test_set_threshold_clamps_low(self, agent):
        """Values below 50 clamp to 50."""
        agent.set_energy_threshold(10)
        assert agent._energy_threshold == 50

    def test_set_threshold_clamps_high(self, agent):
        """Values above 2000 clamp to 2000."""
        agent.set_energy_threshold(9999)
        assert agent._energy_threshold == 2000

    def test_set_threshold_in_range(self, agent):
        """In-range value applied unchanged."""
        agent.set_energy_threshold(450)
        assert agent._energy_threshold == 450

    def test_callback_drops_silence(self, agent):
        """Silent chunk (RMS 0) is dropped — queue stays empty."""
        agent._energy_threshold = 250
        agent._agent_is_speaking = False
        agent._audio_capture_callback(_silent_chunk(), 2400, None, None)
        assert agent._audio_queue.empty()

    def test_callback_passes_loud_audio(self, agent):
        """Loud chunk (RMS 8000) passes the gate and enters the queue."""
        agent._energy_threshold = 250
        agent._agent_is_speaking = False
        agent._audio_capture_callback(_loud_chunk(), 2400, None, None)
        assert agent._audio_queue.qsize() == 1

    def test_callback_drops_quiet_below_threshold(self, agent):
        """Quiet chunk below threshold is dropped."""
        agent._energy_threshold = 300
        agent._agent_is_speaking = False
        # RMS of constant 100 amplitude ≈ 100 < 300 → dropped
        agent._audio_capture_callback(_quiet_chunk(100), 2400, None, None)
        assert agent._audio_queue.empty()

    def test_callback_drops_when_agent_speaking(self, agent):
        """No audio is queued while the agent is speaking (echo guard)."""
        agent._energy_threshold = 250
        agent._agent_is_speaking = True
        agent._audio_capture_callback(_loud_chunk(), 2400, None, None)
        assert agent._audio_queue.empty()


# ─── PipecatVoiceAgent ────────────────────────────────────────────────────


class TestPipecatEnergyThreshold:
    """Test threshold loading, clamping, and audio gating in PipecatVoiceAgent."""

    @pytest.fixture
    def agent(self):
        from voice.pipecat_agent import PipecatVoiceAgent
        return PipecatVoiceAgent()

    @pytest.mark.asyncio
    async def test_default_threshold_when_no_setting(self, agent, monkeypatch):
        """No DB setting and no env var → default 250."""
        monkeypatch.delenv("VAD_ENERGY_THRESHOLD", raising=False)
        with _patch_get_setting(return_value=None):
            await agent._load_energy_threshold()
        assert agent._energy_threshold == 250

    @pytest.mark.asyncio
    async def test_threshold_loaded_from_db(self, agent):
        """DB setting takes priority."""
        with _patch_get_setting(return_value="1200"):
            await agent._load_energy_threshold()
        assert agent._energy_threshold == 1200

    def test_set_threshold_clamps(self, agent):
        """Clamping works for Pipecat too."""
        agent.set_energy_threshold(5)
        assert agent._energy_threshold == 50
        agent.set_energy_threshold(50000)
        assert agent._energy_threshold == 2000

    def test_callback_drops_silence(self, agent):
        """Silent chunk is dropped."""
        agent._energy_threshold = 250
        agent._agent_is_speaking = False
        agent._audio_callback(_silent_chunk(1600), 1600, None, None)
        assert agent._audio_queue.empty()

    def test_callback_passes_loud_audio(self, agent):
        """Loud chunk passes the gate."""
        agent._energy_threshold = 250
        agent._agent_is_speaking = False
        agent._audio_callback(_loud_chunk(8000, samples=1600), 1600, None, None)
        assert agent._audio_queue.qsize() == 1

    def test_callback_drops_when_agent_speaking(self, agent):
        """No audio queued while agent speaking."""
        agent._energy_threshold = 250
        agent._agent_is_speaking = True
        agent._audio_callback(_loud_chunk(8000, samples=1600), 1600, None, None)
        assert agent._audio_queue.empty()


# ─── routes._apply_energy_threshold ───────────────────────────────────────


class TestApplyEnergyThreshold:
    """Test that the settings helper pushes the threshold to the live agent."""

    @pytest.mark.asyncio
    async def test_pushes_to_live_agent(self, monkeypatch):
        """The live voice agent receives the threshold via set_energy_threshold."""
        from voice import routes

        fake_agent = MagicMock()
        monkeypatch.setattr(
            "voice.agent_factory.get_cached_voice_agent",
            lambda: fake_agent,
        )
        await routes._apply_energy_threshold(700)
        fake_agent.set_energy_threshold.assert_called_once_with(700)

    @pytest.mark.asyncio
    async def test_noop_when_no_agent_cached(self, monkeypatch):
        """No cached agent → no creation, no crash (agents self-load on connect)."""
        from voice import routes

        monkeypatch.setattr(
            "voice.agent_factory.get_cached_voice_agent",
            lambda: None,
        )
        # Should not raise and should not create any agent
        await routes._apply_energy_threshold(500)

    @pytest.mark.asyncio
    async def test_noop_when_agent_has_no_setter(self, monkeypatch):
        """Agents without set_energy_threshold (e.g. Gemini) are left untouched."""
        from voice import routes

        class _NoSetterAgent:
            """Real object without set_energy_threshold — unlike MagicMock,
            getattr() won't auto-create a mock attribute."""

        fake_agent = _NoSetterAgent()
        monkeypatch.setattr(
            "voice.agent_factory.get_cached_voice_agent",
            lambda: fake_agent,
        )
        # Should not raise
        await routes._apply_energy_threshold(500)

    @pytest.mark.asyncio
    async def test_errors_are_non_fatal(self, monkeypatch):
        """Factory failure must not raise — settings flow continues."""
        from voice import routes

        def _boom():
            raise RuntimeError("agent factory broken")

        monkeypatch.setattr(
            "voice.agent_factory.get_cached_voice_agent",
            _boom,
        )
        # Should not raise
        await routes._apply_energy_threshold(500)
