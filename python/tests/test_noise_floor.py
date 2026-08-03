"""
Tests for adaptive RMS noise-floor thresholding.

Covers:
1. noise_floor.compute_rms() — int16 RMS computation
2. noise_floor.adaptive_threshold() — 3x multiplier + [50, 2000] clamping
3. noise_floor.AmbientNoiseTracker() — rolling history, percentile floor, reset
4. noise_floor pending-threshold staging (set/consume/peek)
5. WakeWordDetector integration — RMS fed to tracker, threshold staged on wake
6. Deepgram/Pipecat agent _load_energy_threshold() — adaptive value consumed first
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ─── Fixtures / helpers ───────────────────────────────────────────────────


def _reset_pending():
    """Reset the module-level pending threshold so tests don't leak."""
    from voice import noise_floor
    noise_floor.set_pending_adaptive_threshold(None)


@pytest.fixture(autouse=True)
def _clean_pending():
    _reset_pending()
    yield
    _reset_pending()


def _chunk(amplitude: int = 0, samples: int = 4000) -> np.ndarray:
    """int16 mono chunk with constant amplitude (RMS ≈ amplitude)."""
    return np.full((samples, 1), amplitude, dtype=np.int16)


def _patch_get_setting(return_value=None, side_effect=None):
    target = "database.settings_dao.SettingsDAO.get_setting"
    return patch(target, new=AsyncMock(return_value=return_value, side_effect=side_effect))


# ─── compute_rms ──────────────────────────────────────────────────────────


class TestComputeRms:
    def test_silence_is_zero(self):
        from voice.noise_floor import compute_rms
        assert compute_rms(_chunk(0)) == 0.0

    def test_constant_amplitude_matches(self):
        from voice.noise_floor import compute_rms
        rms = compute_rms(_chunk(500))
        assert abs(rms - 500.0) < 1.0

    def test_handles_flat_array_shape(self):
        from voice.noise_floor import compute_rms
        flat = np.full(4000, 300, dtype=np.int16)
        rms = compute_rms(flat)
        assert abs(rms - 300.0) < 1.0


# ─── adaptive_threshold ───────────────────────────────────────────────────


class TestAdaptiveThreshold:
    def test_three_times_floor(self):
        from voice.noise_floor import adaptive_threshold
        assert adaptive_threshold(100.0) == 300
        assert adaptive_threshold(200.0) == 600

    def test_clamps_to_min(self):
        from voice.noise_floor import adaptive_threshold
        # floor ~10 → 30 → clamped to 50
        assert adaptive_threshold(10.0) == 50

    def test_clamps_to_max(self):
        from voice.noise_floor import adaptive_threshold
        assert adaptive_threshold(9000.0) == 2000

    def test_floor_zero_gives_min(self):
        from voice.noise_floor import adaptive_threshold
        assert adaptive_threshold(0.0) == 50

    def test_custom_multiplier(self):
        from voice.noise_floor import adaptive_threshold
        assert adaptive_threshold(100.0, multiplier=2.0) == 200


# ─── AmbientNoiseTracker ──────────────────────────────────────────────────


class TestAmbientNoiseTracker:
    def test_empty_tracker_floor_zero(self):
        from voice.noise_floor import AmbientNoiseTracker
        t = AmbientNoiseTracker(window=8)
        assert t.noise_floor() == 0.0
        assert t.suggested_threshold() == 50  # clamped from 0*3

    def test_floor_is_percentile(self):
        from voice.noise_floor import AmbientNoiseTracker
        t = AmbientNoiseTracker(window=16)
        # Mostly quiet (~100) with a few loud spikes (~900)
        for _ in range(14):
            t.add(100.0)
        for _ in range(2):
            t.add(900.0)
        # 25th percentile should be ~100, not pulled up by spikes
        assert t.noise_floor() == pytest.approx(100.0, abs=10.0)

    def test_rolling_window_drops_old(self):
        from voice.noise_floor import AmbientNoiseTracker
        t = AmbientNoiseTracker(window=4)
        for _ in range(4):
            t.add(100.0)
        for _ in range(4):
            t.add(1000.0)
        # Old quiet samples rolled out — floor now reflects loud window
        assert t.noise_floor() > 500.0

    def test_count_and_full(self):
        from voice.noise_floor import AmbientNoiseTracker
        t = AmbientNoiseTracker(window=4)
        assert t.count == 0
        assert not t.full
        for _ in range(4):
            t.add(100.0)
        assert t.count == 4
        assert t.full

    def test_reset_clears_history(self):
        from voice.noise_floor import AmbientNoiseTracker
        t = AmbientNoiseTracker(window=4)
        t.add(100.0)
        t.reset()
        assert t.count == 0
        assert t.noise_floor() == 0.0

    def test_suggested_threshold_tracks_floor(self):
        from voice.noise_floor import AmbientNoiseTracker
        t = AmbientNoiseTracker(window=4)
        for _ in range(4):
            t.add(150.0)
        assert t.suggested_threshold() == 450  # 150 * 3


# ─── Pending staging ──────────────────────────────────────────────────────


class TestPendingStaging:
    def test_set_and_consume(self):
        from voice import noise_floor
        noise_floor.set_pending_adaptive_threshold(420)
        assert noise_floor.consume_pending_adaptive_threshold() == 420
        assert noise_floor.consume_pending_adaptive_threshold() is None  # consumed once

    def test_consume_empty_returns_none(self):
        from voice import noise_floor
        assert noise_floor.consume_pending_adaptive_threshold() is None

    def test_peek_does_not_consume(self):
        from voice import noise_floor
        noise_floor.set_pending_adaptive_threshold(777)
        assert noise_floor.peek_pending_adaptive_threshold() == 777
        assert noise_floor.consume_pending_adaptive_threshold() == 777

    def test_clear_with_none(self):
        from voice import noise_floor
        noise_floor.set_pending_adaptive_threshold(300)
        noise_floor.set_pending_adaptive_threshold(None)
        assert noise_floor.consume_pending_adaptive_threshold() is None


# ─── WakeWordDetector integration ─────────────────────────────────────────


class TestWakeWordAdaptive:
    @pytest.fixture
    def detector(self):
        """Construct a WakeWordDetector shell without loading Vosk models.

        Uses __new__ to skip __init__ (which loads Vosk models and config),
        then attaches a real AmbientNoiseTracker.
        """
        from voice.noise_floor import AmbientNoiseTracker
        from voice.wake_word import WakeWordDetector

        d = WakeWordDetector.__new__(WakeWordDetector)
        d._noise_tracker = AmbientNoiseTracker(window=8)
        return d

    def test_stage_with_insufficient_history(self, detector):
        """First wake with < MIN_STAGING_SAMPLES stages nothing (no floor-0 clamp)."""
        from voice import noise_floor
        detector._noise_tracker.add(200.0)  # only 1 sample
        detector._stage_adaptive_threshold()
        assert noise_floor.peek_pending_adaptive_threshold() is None

    def test_stage_with_enough_history(self, detector):
        """With enough ambient samples, stages ~3x the percentile floor."""
        from voice import noise_floor
        # 1s of quiet ambient (4 × 250ms) at ~200 RMS
        for _ in range(4):
            detector._noise_tracker.add(200.0)
        detector._stage_adaptive_threshold()
        assert noise_floor.consume_pending_adaptive_threshold() == 600  # 200 * 3

    def test_stage_robust_to_speech_spikes(self, detector):
        """A few loud spikes don't inflate the 25th-percentile floor."""
        from voice import noise_floor
        # 6 quiet chunks + 2 loud speech chunks
        for _ in range(6):
            detector._noise_tracker.add(150.0)
        for _ in range(2):
            detector._noise_tracker.add(2000.0)
        detector._stage_adaptive_threshold()
        threshold = noise_floor.consume_pending_adaptive_threshold()
        assert threshold == pytest.approx(450, abs=50)  # ~150 * 3, not pulled up


# ─── Agent consumption ────────────────────────────────────────────────────


class TestAgentConsumption:
    @pytest.fixture
    def deepgram(self):
        from voice.deepgram_agent import DeepgramVoiceAgent
        return DeepgramVoiceAgent(api_key="test-key")

    @pytest.fixture
    def pipecat(self):
        from voice.pipecat_agent import PipecatVoiceAgent
        return PipecatVoiceAgent()

    @pytest.mark.asyncio
    async def test_deepgram_consumes_pending_first(self, deepgram, monkeypatch):
        """Staged adaptive threshold wins over DB/env."""
        from voice import noise_floor
        noise_floor.set_pending_adaptive_threshold(900)
        # DB would say 200 — must be ignored because pending wins
        with _patch_get_setting(return_value="200"):
            await deepgram._load_energy_threshold()
        assert deepgram._energy_threshold == 900
        # Pending was consumed (cleared)
        assert noise_floor.consume_pending_adaptive_threshold() is None

    @pytest.mark.asyncio
    async def test_deepgram_falls_back_when_no_pending(self, deepgram, monkeypatch):
        monkeypatch.delenv("VAD_ENERGY_THRESHOLD", raising=False)
        with _patch_get_setting(return_value=None):
            await deepgram._load_energy_threshold()
        assert deepgram._energy_threshold == 250

    @pytest.mark.asyncio
    async def test_deepgram_pending_above_max_clamped(self, deepgram):
        from voice import noise_floor
        noise_floor.set_pending_adaptive_threshold(99999)
        with _patch_get_setting(return_value="200"):
            await deepgram._load_energy_threshold()
        assert deepgram._energy_threshold == 2000  # clamped by set_energy_threshold

    @pytest.mark.asyncio
    async def test_pipecat_consumes_pending_first(self, pipecat):
        from voice import noise_floor
        noise_floor.set_pending_adaptive_threshold(480)
        with _patch_get_setting(return_value="200"):
            await pipecat._load_energy_threshold()
        assert pipecat._energy_threshold == 480
        assert noise_floor.consume_pending_adaptive_threshold() is None

    @pytest.mark.asyncio
    async def test_pipecat_falls_back_when_no_pending(self, pipecat, monkeypatch):
        monkeypatch.delenv("VAD_ENERGY_THRESHOLD", raising=False)
        with _patch_get_setting(return_value=None):
            await pipecat._load_energy_threshold()
        assert pipecat._energy_threshold == 250

    @pytest.mark.asyncio
    async def test_pending_does_not_leak_between_agents(self, deepgram, pipecat):
        """Consumed by Deepgram → Pipecat sees no pending and uses a distinct DB value."""
        from voice import noise_floor
        noise_floor.set_pending_adaptive_threshold(650)
        with _patch_get_setting(return_value="900"):  # distinct from pending
            await deepgram._load_energy_threshold()
            await pipecat._load_energy_threshold()
        # Deepgram got the pending 650; Pipecat (pending consumed) got DB 900
        assert deepgram._energy_threshold == 650
        assert pipecat._energy_threshold == 900
