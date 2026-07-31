"""
Tests for config.ensure_ffmpeg_on_path — the ffmpeg PATH fallback.

Covers:
- ensure_ffmpeg_on_path() always returns a bool (never raises)
- The import-time result (_ffmpeg_ok) is consistent with what shutil.which
  actually resolves — so the fallback can never claim success while ffmpeg
  stays unresolvable
- The fallback deterministically discovers an ffmpeg binary that lives in a
  candidate directory but is missing from PATH (the whole point of the helper)
- When ffmpeg is genuinely installed, ensure_ffmpeg_on_path() must succeed
"""

import glob
import os
import shutil

import pytest

import config
from config import ensure_ffmpeg_on_path

# ── ffmpeg fallback (Windows .exe vs Linux/macOS) ────────────────────────


def _ffmpeg_bin_name() -> str:
    return "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Contract / Return Type
# ═══════════════════════════════════════════════════════════════════════════


class TestReturnContract:
    """ensure_ffmpeg_on_path() must return a bool and never raise."""

    def test_returns_bool(self):
        result = ensure_ffmpeg_on_path()
        assert isinstance(result, bool)

    def test_callable_from_config(self):
        """The function is exposed on the config module."""
        assert callable(config.ensure_ffmpeg_on_path)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Consistency with shutil.which
# ═══════════════════════════════════════════════════════════════════════════


class TestConsistency:
    """_ffmpeg_ok must never claim success while ffmpeg stays unresolvable.

    This holds on any machine: without ffmpeg installed both sides are False,
    with ffmpeg installed both sides are True. Safe for CI either way.
    """

    def test_ffmpeg_ok_matches_which(self):
        if config._ffmpeg_ok:
            # If the import-time fallback succeeded, ffmpeg must resolve now.
            assert shutil.which("ffmpeg") is not None
        else:
            # If it failed, ffmpeg genuinely isn't discoverable.
            assert shutil.which("ffmpeg") is None

    def test_ensure_ffmpeg_resolves_when_installed(self):
        """Document intent: on a machine with ffmpeg, the helper must succeed."""
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not installed on this machine")
        assert ensure_ffmpeg_on_path() is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. Fallback Discovery (deterministic, no real ffmpeg required)
# ═══════════════════════════════════════════════════════════════════════════


class TestFallbackDiscovery:
    """The core behavior: find ffmpeg in a candidate dir even when PATH is blind."""

    def test_discovers_ffmpeg_in_candidate_dir(self, monkeypatch, tmp_path):
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        (fake_bin / _ffmpeg_bin_name()).write_bytes(b"")  # fake binary

        old_path = os.environ.get("PATH", "")

        def fake_which(name, path=None):
            """Resolve only when asked to search a directory we planted."""
            if name == "ffmpeg" and path:
                candidate = os.path.join(path, _ffmpeg_bin_name())
                return candidate if os.path.isfile(candidate) else None
            return None

        def fake_glob(pattern, recursive=False):
            """Return our planted dir for any ffmpeg-looking candidate pattern."""
            if "ffmpeg" in pattern:
                return [str(fake_bin)]
            return []

        try:
            monkeypatch.setattr(shutil, "which", fake_which)
            monkeypatch.setattr(glob, "glob", fake_glob)

            result = ensure_ffmpeg_on_path()

            assert result is True
            assert str(fake_bin) in os.environ["PATH"]
        finally:
            os.environ["PATH"] = old_path

    def test_returns_false_when_ffmpeg_absent(self, monkeypatch):
        """No ffmpeg anywhere -> False, PATH untouched."""
        old_path = os.environ.get("PATH", "")

        def blind_which(name, path=None):
            return None

        try:
            monkeypatch.setattr(shutil, "which", blind_which)
            monkeypatch.setattr(glob, "glob", lambda pattern, recursive=False: [])

            result = ensure_ffmpeg_on_path()

            assert result is False
            assert os.environ.get("PATH", "") == old_path
        finally:
            os.environ["PATH"] = old_path
