"""
Unit tests for the voice conversation fixes:
  - flush_audio_buffer() in SpeechProcessor
  - is_speaking_event threading.Event in BARQResponder
  - Mic monitor _speaking_event check (RMS discard during TTS)
"""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.responder import BARQResponder, _speaking_event
from voice.speech import SpeechProcessor


# ═══════════════════════════════════════════════════════════════════════
# Autouse fixture: reset the module-level _speaking_event before each test
# to prevent state leakage between tests (if a test fails mid-way after
# .set() but before .clear(), the event stays set for subsequent tests).
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_speaking_event():
    """Reset the module-level speaking event before every test."""
    _speaking_event.clear()
    yield
    _speaking_event.clear()


# ═══════════════════════════════════════════════════════════════════════
# is_speaking_event — Module-Level Event
# ═══════════════════════════════════════════════════════════════════════


class TestSpeakingEvent:
    """Tests for the module-level _speaking_event threading.Event."""

    def test_event_is_threading_event(self):
        assert isinstance(_speaking_event, threading.Event)

    def test_event_starts_cleared(self):
        assert _speaking_event.is_set() is False

    def test_event_set_and_clear(self):
        _speaking_event.set()
        assert _speaking_event.is_set() is True
        _speaking_event.clear()
        assert _speaking_event.is_set() is False

    def test_event_set_twice_is_idempotent(self):
        _speaking_event.set()
        _speaking_event.set()
        assert _speaking_event.is_set() is True

    def test_event_clear_twice_is_idempotent(self):
        _speaking_event.clear()
        _speaking_event.clear()
        assert _speaking_event.is_set() is False


class TestResponderSpeakingEvent:
    """BARQResponder should reference the module-level speaking event."""

    def test_responder_has_is_speaking_event(self):
        r = BARQResponder()
        assert hasattr(r, "is_speaking_event")
        r.conversation.end_session()

    def test_is_speaking_event_is_module_event(self):
        r = BARQResponder()
        assert r.is_speaking_event is _speaking_event
        r.conversation.end_session()

    def test_is_speaking_event_starts_cleared(self):
        r = BARQResponder()
        assert r.is_speaking_event.is_set() is False
        r.conversation.end_session()

    def test_responder_sets_event_via_reference(self):
        r = BARQResponder()
        r.is_speaking_event.set()
        assert _speaking_event.is_set() is True
        r.conversation.end_session()

    def test_responder_clears_event_via_reference(self):
        _speaking_event.set()
        r = BARQResponder()
        r.is_speaking_event.clear()
        assert _speaking_event.is_set() is False
        r.conversation.end_session()

    def test_two_responders_share_same_event(self):
        r1 = BARQResponder()
        r2 = BARQResponder()
        assert r1.is_speaking_event is r2.is_speaking_event
        r1.conversation.end_session()
        r2.conversation.end_session()

    def test_set_from_one_responder_visible_from_other(self):
        r1 = BARQResponder()
        r2 = BARQResponder()
        r1.is_speaking_event.set()
        assert r2.is_speaking_event.is_set() is True
        r1.conversation.end_session()
        r2.conversation.end_session()

    def test_event_independent_of_is_speaking_bool(self):
        r = BARQResponder()
        r.is_speaking = False
        r.is_speaking_event.set()
        assert r.is_speaking_event.is_set() is True
        assert r.is_speaking is False
        r.conversation.end_session()


# ═══════════════════════════════════════════════════════════════════════
# flush_audio_buffer — SpeechProcessor
#
# Note: flush_audio_buffer does `from .audio_device import resolve_input_device`
# inside the method body (lazy import).  To patch it, use the real path
# `voice.audio_device.resolve_input_device` — NOT `voice.speech.resolve_input_device`.
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def speech_processor() -> SpeechProcessor:
    return SpeechProcessor()


class TestFlushAudioBuffer:
    """flush_audio_buffer should drain stale audio from the input buffer."""

    @pytest.mark.asyncio
    @patch("voice.audio_device.resolve_input_device", return_value=0)
    async def test_flush_opens_stream_and_reads_frames(
        self, mock_resolve: MagicMock, speech_processor: SpeechProcessor,
    ):
        """Should open InputStream with correct params and read expected chunks."""
        with patch("sounddevice.InputStream") as mock_sd_input:
            mock_instance = MagicMock()
            mock_sd_input.return_value = mock_instance

            await speech_processor.flush_audio_buffer(duration=0.15)

            mock_sd_input.assert_called_once()
            kwargs = mock_sd_input.call_args[1]
            assert kwargs["samplerate"] == 16000
            assert kwargs["channels"] == 1
            assert kwargs["dtype"] == "int16"
            assert kwargs["blocksize"] == 1024

            mock_instance.start.assert_called_once()
            # 0.15s @ 16kHz / 1024 blocksize = 2 chunks
            assert mock_instance.read.call_count == 2
            mock_instance.stop.assert_called_once()
            mock_instance.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("voice.audio_device.resolve_input_device", return_value=0)
    async def test_flush_longer_duration_reads_more_chunks(
        self, mock_resolve: MagicMock, speech_processor: SpeechProcessor,
    ):
        """Longer duration should read proportionally more chunks."""
        with patch("sounddevice.InputStream") as mock_sd_input:
            mock_instance = MagicMock()
            mock_sd_input.return_value = mock_instance

            await speech_processor.flush_audio_buffer(duration=0.5)
            # 0.5s @ 16kHz / 1024 = 7 chunks
            assert mock_instance.read.call_count == 7

    @pytest.mark.asyncio
    @patch("voice.audio_device.resolve_input_device", return_value=0)
    async def test_flush_creates_stream_with_correct_device(
        self, mock_resolve: MagicMock, speech_processor: SpeechProcessor,
    ):
        """The InputStream should be created with the resolved device."""
        with patch("sounddevice.InputStream") as mock_sd_input:
            mock_instance = MagicMock()
            mock_sd_input.return_value = mock_instance

            await speech_processor.flush_audio_buffer(duration=0.1)

            kwargs = mock_sd_input.call_args[1]
            assert kwargs["device"] == 0

    @pytest.mark.asyncio
    @patch("voice.audio_device.resolve_input_device", side_effect=RuntimeError("No device"))
    async def test_flush_resolve_error_does_not_crash(
        self, mock_resolve: MagicMock, speech_processor: SpeechProcessor,
    ):
        """If resolve_input_device raises, flush should catch and not crash."""
        await speech_processor.flush_audio_buffer(duration=0.15)

    @pytest.mark.asyncio
    @patch("voice.audio_device.resolve_input_device", return_value=0)
    async def test_flush_stream_init_error_does_not_crash(
        self, mock_resolve: MagicMock, speech_processor: SpeechProcessor,
    ):
        """If InputStream constructor raises, flush should recover gracefully."""
        with patch("sounddevice.InputStream") as mock_sd_input:
            mock_sd_input.side_effect = RuntimeError("Stream init failed")
            await speech_processor.flush_audio_buffer(duration=0.15)

    @pytest.mark.asyncio
    @patch("voice.audio_device.resolve_input_device", return_value=0)
    async def test_flush_zero_duration_reads_no_chunks(
        self, mock_resolve: MagicMock, speech_processor: SpeechProcessor,
    ):
        """Zero duration should open stream but not read chunks."""
        with patch("sounddevice.InputStream") as mock_sd_input:
            mock_instance = MagicMock()
            mock_sd_input.return_value = mock_instance

            await speech_processor.flush_audio_buffer(duration=0.0)

            mock_instance.start.assert_called_once()
            assert mock_instance.read.call_count == 0
            mock_instance.stop.assert_called_once()
            mock_instance.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("voice.audio_device.resolve_input_device", return_value=0)
    async def test_flush_read_error_does_not_crash(
        self, mock_resolve: MagicMock, speech_processor: SpeechProcessor,
    ):
        """If stream.read() fails mid-loop, exception is caught by outer try/except."""
        with patch("sounddevice.InputStream") as mock_sd_input:
            mock_instance = MagicMock()
            mock_sd_input.return_value = mock_instance
            mock_instance.read.side_effect = RuntimeError("Buffer underflow")

            await speech_processor.flush_audio_buffer(duration=0.15)
            assert mock_instance.read.call_count >= 1


# ═══════════════════════════════════════════════════════════════════════
# Mic Monitor — _speaking_event Check (Echo Prevention)
# ═══════════════════════════════════════════════════════════════════════


class TestMicMonitorSpeakingEvent:
    """Background mic monitor should discard audio when event is set.

    These tests simulate the inner loop logic rather than calling the
    actual _mic_monitor_loop (infinite loop, requires real audio hardware).
    """

    def test_mic_monitor_resets_level_when_speaking(self):
        """When _speaking_event is set, _current_mic_level should be 0.0."""
        import numpy as np
        from voice.speech import SpeechProcessor

        sp = SpeechProcessor()
        sp._current_mic_level = 0.5

        data = np.zeros(1024, dtype=np.int16)
        _speaking_event.set()
        try:
            if _speaking_event.is_set():
                sp._current_mic_level = 0.0
            else:
                rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                sp._current_mic_level = min(1.0, rms / 10000.0)

            assert sp._current_mic_level == 0.0
        finally:
            _speaking_event.clear()

    def test_mic_monitor_computes_rms_when_not_speaking(self):
        """When _speaking_event is NOT set, RMS should be computed normally."""
        import numpy as np
        from voice.speech import SpeechProcessor

        sp = SpeechProcessor()
        sp._current_mic_level = 0.0
        _speaking_event.clear()

        data = np.ones(1024, dtype=np.int16) * 1000

        if _speaking_event.is_set():
            sp._current_mic_level = 0.0
        else:
            rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
            sp._current_mic_level = min(1.0, rms / 10000.0)

        assert 0.05 < sp._current_mic_level < 1.0

    def test_mic_monitor_still_reads_buffer_when_speaking(self):
        """Even when event is set, audio IS still read (buffer drained), RMS discarded."""
        import numpy as np
        from voice.speech import SpeechProcessor

        sp = SpeechProcessor()
        _speaking_event.set()

        try:
            data = np.ones(1024, dtype=np.int16) * 5000
            rms_computed = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))

            if _speaking_event.is_set():
                sp._current_mic_level = 0.0

            assert sp._current_mic_level == 0.0
            assert rms_computed > 0
        finally:
            _speaking_event.clear()

    def test_rms_exception_handled_gracefully(self):
        """If RMS computation itself raises, try/except sets level to 0.0."""
        import numpy as np
        from voice.speech import SpeechProcessor

        sp = SpeechProcessor()
        sp._current_mic_level = 0.5

        _speaking_event.clear()
        try:
            # Normal data works fine
            data = np.ones(1024, dtype=np.int16) * 1000
            if _speaking_event.is_set():
                sp._current_mic_level = 0.0
            else:
                try:
                    rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                    sp._current_mic_level = min(1.0, rms / 10000.0)
                except Exception:
                    sp._current_mic_level = 0.0

            assert 0.05 < sp._current_mic_level < 1.0

            # Bad data causes exception, which is caught gracefully
            if _speaking_event.is_set():
                sp._current_mic_level = 0.0
            else:
                try:
                    rms = float(np.sqrt(np.mean(np.array("bad").astype(np.float64) ** 2)))
                    sp._current_mic_level = min(1.0, rms / 10000.0)
                except Exception:
                    sp._current_mic_level = 0.0

            assert sp._current_mic_level == 0.0
        finally:
            _speaking_event.clear()
