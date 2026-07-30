"""
Abstract base class for voice agent implementations.

Defines the common interface that both DeepgramVoiceAgent and
PipecatVoiceAgent must implement so the conversation listener
and routes can treat them interchangeably.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class VoiceAgentBase(ABC):
    """Common interface for STT → LLM → TTS voice agent pipelines.

    Subclasses must implement connect(), start_conversation(), stop(),
    and the is_running property.  Callbacks are wired by the
    ConversationListener after construction.
    """

    # ── Callbacks (set externally by ConversationListener) ────────────

    on_interim_transcript: Optional[Callable[[str], Any]] = None
    """Fired for each partial transcription chunk (real-time)."""

    on_final_transcript: Optional[Callable[[str], Any]] = None
    """Fired when a complete utterance is finalised."""

    on_agent_speaking: Optional[Callable[[], Any]] = None
    """Fired when the agent starts producing speech audio."""

    on_agent_done_speaking: Optional[Callable[[], Any]] = None
    """Fired when the agent finishes producing speech audio."""

    on_audio_chunk: Optional[Callable[[Any, int], Any]] = None
    """Fired for each PCM audio chunk from the agent.
    Args: (pcm_array: np.ndarray, sample_rate: int)."""

    on_agent_text: Optional[Callable[[str], Any]] = None
    """Fired when the agent's spoken response text is known."""

    # ── Lifecycle ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """True while the agent is actively streaming audio."""
        ...

    @abstractmethod
    async def connect(self) -> bool:
        """Establish the voice pipeline (WebSocket or local).

        Returns:
            True if the pipeline is ready for conversation.
        """
        ...

    @abstractmethod
    async def start_conversation(self, audio_device: Optional[int] = None):
        """Begin streaming mic audio and processing responses.

        Args:
            audio_device: sounddevice input device index. None = default.
        """
        ...

    @abstractmethod
    async def stop(self):
        """Gracefully shut down the pipeline, release audio devices,
        and close any network connections."""
        ...
