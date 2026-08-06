"""
Tests for voice -> agent_chat_history persistence (voice/agent_history_sync.py).

Verifies that spoken commands are written into the ``agent_chat_history``
setting under the ``voice_commands`` key with the exact shape the brain
re-import reads (role='user', content, timestamp), with dedupe, other-key
preservation, and a merge-safe remote mirror.
"""

import json

import pytest

from database import settings_dao
from voice.agent_history_sync import (
    VOICE_COMMANDS_KEY,
    _mirror_voice_commands,
    _remote_url,
    persist_voice_utterance,
)


@pytest.fixture(autouse=True)
def _no_mirror(monkeypatch):
    """Prevent the fire-and-forget mirror from hitting the network in tests."""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("voice.agent_history_sync._mirror_voice_commands", _noop)


async def _get_history() -> dict:
    raw = await settings_dao.get_setting("agent_chat_history")
    return json.loads(raw) if raw else {}


@pytest.mark.asyncio
async def test_persist_adds_user_message():
    """A spoken command is stored as a user message with a timestamp."""
    await persist_voice_utterance("open chrome")
    data = await _get_history()
    items = data[VOICE_COMMANDS_KEY]
    assert len(items) == 1
    assert items[0]["role"] == "user"
    assert items[0]["content"] == "open chrome"
    assert isinstance(items[0]["timestamp"], (int, float))


@pytest.mark.asyncio
async def test_persist_appends_distinct_commands():
    """Different commands accumulate in order."""
    await persist_voice_utterance("scan jobs")
    await persist_voice_utterance("what is the weather")
    data = await _get_history()
    items = data[VOICE_COMMANDS_KEY]
    assert [m["content"] for m in items] == ["scan jobs", "what is the weather"]


@pytest.mark.asyncio
async def test_persist_dedupes_immediate_repeat():
    """The same utterance right after itself (agent re-transcription) is skipped."""
    await persist_voice_utterance("open chrome")
    await persist_voice_utterance("open chrome")
    data = await _get_history()
    assert len(data[VOICE_COMMANDS_KEY]) == 1


@pytest.mark.asyncio
async def test_persist_ignores_empty_text():
    """Blank utterances never create the key."""
    await persist_voice_utterance("   ")
    await persist_voice_utterance("")
    raw = await settings_dao.get_setting("agent_chat_history")
    assert raw is None


@pytest.mark.asyncio
async def test_persist_preserves_other_agent_keys():
    """Writing voice commands must not clobber other agents' history keys."""
    await settings_dao.set_setting(
        "agent_chat_history",
        json.dumps({"chat_page": [{"role": "user", "content": "hi", "timestamp": 1}]}),
        category="memory",
    )
    await persist_voice_utterance("scan jobs")
    data = await _get_history()
    assert "chat_page" in data
    assert len(data[VOICE_COMMANDS_KEY]) == 1


@pytest.mark.asyncio
async def test_mirror_merges_only_voice_key_into_remote(monkeypatch):
    """The mirror preserves remote keys and only injects the voice key."""
    remote_history = {"TestAgent": [{"role": "user", "content": "hello"}]}
    local_data = {
        VOICE_COMMANDS_KEY: [{"role": "user", "content": "scan jobs", "timestamp": 123.0}],
        "chat_page": [{"role": "user", "content": "hi", "timestamp": 1}],
    }
    posted = {}

    class FakeResponse:
        def __init__(self, status_code=200, json_data=None):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            return FakeResponse(200, {"history": remote_history})

        async def post(self, url, json=None, **kwargs):
            posted["json"] = json

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())

    await _mirror_voice_commands(local_data)

    merged = posted["json"]["history"]
    # Remote keys preserved
    assert merged["TestAgent"] == remote_history["TestAgent"]
    # Voice key injected from local
    assert merged[VOICE_COMMANDS_KEY] == local_data[VOICE_COMMANDS_KEY]
    # Non-voice local keys are NOT pushed (avoids clobbering remote state)
    assert "chat_page" not in merged


def test_remote_url_env_override(monkeypatch):
    """BARQ_REMOTE_URL env var overrides the default remote URL."""
    monkeypatch.setenv("BARQ_REMOTE_URL", "http://example.test")
    assert _remote_url() == "http://example.test"


def test_remote_url_default():
    """Without env, the app's default remote URL is used."""
    import os
    old = os.environ.pop("BARQ_REMOTE_URL", None)
    try:
        assert _remote_url() == "http://155.248.247.224"
    finally:
        if old is not None:
            os.environ["BARQ_REMOTE_URL"] = old
