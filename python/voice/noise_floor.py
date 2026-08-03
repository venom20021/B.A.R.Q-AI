"""
Adaptive RMS noise-floor estimation for the mic energy gate.

On wake, the WakeWordDetector passively samples the ambient noise floor
from its continuous 16kHz mic stream and stages an adaptive energy
threshold (~3x the floor).  The voice agents (Deepgram / Pipecat) consume
that staged value on ``connect()`` so the VAD gate adapts to the current
room noise instead of using a fixed constant.

Threshold resolution priority in the agents:
    1. Pending adaptive threshold staged at wake (this module)
    2. DB setting ``vad_energy_threshold``
    3. Env var ``VAD_ENERGY_THRESHOLD``
    4. Default ``250``
"""

from collections import deque
from typing import Optional

# ─── Constants ────────────────────────────────────────────────────────────

MIN_THRESHOLD = 50               # clamped lower bound (matches agents)
MAX_THRESHOLD = 2000             # clamped upper bound (matches agents)
ADAPTIVE_MULTIPLIER = 3.0        # threshold = 3x the noise floor
WINDOW_CHUNKS = 24               # ~6s of history at 250ms/chunk (16kHz/4000 samples)
MIN_STAGING_SAMPLES = 4          # require ~1s ambient before staging (~4 chunks at 250ms)

# Staged value produced at wake, consumed by the agent on connect
_pending_adaptive_threshold: Optional[int] = None


# ─── Core helpers ─────────────────────────────────────────────────────────


def compute_rms(indata) -> float:
    """Compute the RMS amplitude of an int16 audio chunk (as a float)."""
    import numpy as np

    data = np.asarray(indata, dtype=np.float32)
    return float(np.sqrt(np.mean(data ** 2)))


def adaptive_threshold(noise_floor: float, multiplier: float = ADAPTIVE_MULTIPLIER) -> int:
    """Compute the energy gate threshold from a noise floor.

    Threshold = noise_floor * multiplier (default 3x), clamped to the
    supported [MIN_THRESHOLD, MAX_THRESHOLD] range.
    """
    value = int(noise_floor * multiplier)
    return max(MIN_THRESHOLD, min(MAX_THRESHOLD, value))


# ─── Rolling ambient tracker ─────────────────────────────────────────────


class AmbientNoiseTracker:
    """Keeps a rolling window of per-chunk RMS samples.

    The wake word detector feeds one RMS value per mic chunk; the tracker
    estimates the ambient noise floor as a robust low percentile of the
    window so transient speech doesn't inflate the estimate.
    """

    def __init__(self, window: int = WINDOW_CHUNKS):
        self._window = window
        self._samples: deque[float] = deque(maxlen=window)

    def add(self, rms: float) -> None:
        """Record one per-chunk RMS sample."""
        self._samples.append(float(rms))

    @property
    def count(self) -> int:
        return len(self._samples)

    @property
    def full(self) -> bool:
        return len(self._samples) >= self._window

    def reset(self) -> None:
        self._samples.clear()

    def noise_floor(self, percentile: float = 25.0) -> float:
        """Estimate ambient noise floor as the given percentile of the window.

        Uses a low percentile (default 25th) so occasional speech or bumps
        in the window don't push the floor upward.  Falls back to 0 if no
        samples have been collected yet.
        """
        if not self._samples:
            return 0.0
        import numpy as np

        values = np.array(self._samples, dtype=np.float32)
        return float(np.percentile(values, percentile))

    def suggested_threshold(self) -> int:
        """Adaptive threshold (~3x noise floor), clamped to the safe range."""
        return adaptive_threshold(self.noise_floor())


# ─── Pending threshold staging ───────────────────────────────────────────


def set_pending_adaptive_threshold(value: Optional[int]) -> None:
    """Stage an adaptive threshold for the next agent connect().

    Called by the wake word detector when a wake word is detected.
    The value is consumed (and cleared) by the voice agent's
    ``_load_energy_threshold()`` on connect.
    """
    global _pending_adaptive_threshold
    _pending_adaptive_threshold = value


def consume_pending_adaptive_threshold() -> Optional[int]:
    """Read and clear the staged adaptive threshold.

    Returns None if no adaptive threshold has been staged (callers then
    fall through to DB/env/default resolution).
    """
    global _pending_adaptive_threshold
    value = _pending_adaptive_threshold
    _pending_adaptive_threshold = None
    return value


def peek_pending_adaptive_threshold() -> Optional[int]:
    """Return the staged threshold without consuming it (for diagnostics)."""
    return _pending_adaptive_threshold
