"""
BARQ Voice Pipeline — a lightweight, pipecat-inspired frame-based architecture.

Inspired by pipecat (https://github.com/pipecat-ai/pipecat), this module
provides:

- **Frames**: typed data units (audio, text, control signals) flowing
  through the pipeline.
- **FrameProcessors**: modular stages (STT → LLM → TTS) that can be
  composed into pipelines.
- **Pipeline**: chains processors together, routing frames between them.
- **Priority interrupt**: ``InterruptFrame`` is a high-priority signal
  that flushes pending output queues immediately — no need to poll
  boolean flags.

Usage::

    pipeline = VoicePipeline()
    pipeline.add_stage(stt_processor)
    pipeline.add_stage(llm_processor)
    pipeline.add_stage(tts_processor)

    async for frame in pipeline.run(audio_stream):
        if isinstance(frame, TTSAudioFrame):
            await play_audio(frame.pcm, frame.sample_rate)
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import AsyncIterable, Callable, Optional

import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# Frame Types — standalone dataclasses (no inheritance) to avoid Python
# MRO field ordering issues with defaults.
# ═══════════════════════════════════════════════════════════════════════

class FrameType(Enum):
    """High-level classification for routing and debugging."""
    SYSTEM = auto()
    AUDIO_INPUT = auto()
    AUDIO_OUTPUT = auto()
    TEXT_INPUT = auto()
    TEXT_OUTPUT = auto()
    CONTROL = auto()


# ── System frames (high-priority, bypass normal queue) ───────────────

@dataclass
class InterruptFrame:
    """High-priority signal to cancel pending output and reset.

    Inspired by pipecat's ``InterruptionFrame``.  When emitted, all
    downstream processors should flush their buffers and prepare for
    new input immediately.
    """
    source: str = ""
    type: FrameType = FrameType.SYSTEM
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class StartFrame:
    """Signals the start of a new conversation turn."""
    type: FrameType = FrameType.SYSTEM
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class EndFrame:
    """Signals the end of a conversation turn (clean shutdown)."""
    type: FrameType = FrameType.SYSTEM
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


# ── Audio frames ─────────────────────────────────────────────────────

@dataclass
class AudioFrame:
    """Raw audio data flowing through the pipeline."""
    data: np.ndarray = field(repr=False)
    sample_rate: int = 16000
    channels: int = 1
    type: FrameType = FrameType.AUDIO_INPUT
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class TTSAudioFrame:
    """Synthesised speech audio ready for playback."""
    pcm: np.ndarray = field(repr=False)
    sample_rate: int = 24000
    text: str = ""
    type: FrameType = FrameType.AUDIO_OUTPUT
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


# ── Text / transcription frames ──────────────────────────────────────

@dataclass
class TranscriptionFrame:
    """STT output: transcribed text with confidence."""
    text: str
    confidence: float = 0.0
    is_final: bool = True
    type: FrameType = FrameType.TEXT_INPUT
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class LLMResponseFrame:
    """LLM output: generated text (may be a partial sentence)."""
    text: str
    is_final: bool = False  # False = partial / mid-stream
    type: FrameType = FrameType.TEXT_OUTPUT
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


# ── Mic level frame ──────────────────────────────────────────────────

@dataclass
class MicLevelFrame:
    """Live microphone level for visualisation (0.0–1.0)."""
    level: float = 0.0
    type: FrameType = FrameType.CONTROL
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# FrameProcessors
# ═══════════════════════════════════════════════════════════════════════

# Type alias used in processor method signatures
AnyFrame = AudioFrame | TTSAudioFrame | TranscriptionFrame | LLMResponseFrame \
           | InterruptFrame | StartFrame | EndFrame | MicLevelFrame


class FrameProcessor(ABC):
    """Base class for a pipeline stage.

    Subclasses implement ``process_stream()`` to receive frames and
    yield output frames.
    """

    @abstractmethod
    async def process_stream(
        self, stream: AsyncIterable[AnyFrame]
    ) -> AsyncIterable[AnyFrame]:
        """Process an incoming stream of frames.

        Args:
            stream: Incoming frame stream.

        Yields:
            Output frames (may be zero, one, or many per input frame).
        """
        ...


class STTProcessor(FrameProcessor):
    """Speech-to-text frame processor.

    Supports two modes:

    **Accumulation mode** (default, when only ``transcribe_fn`` is given):
    Receives ``AudioFrame`` → buffers raw audio → periodically writes temp
    WAV files and calls ``transcribe_fn`` for final transcription.
    Yields ``TranscriptionFrame`` and ``MicLevelFrame``.

    **VAD streaming mode** (when ``transcribe_streaming_fn`` is given):
    Spawns ``transcribe_streaming_fn()`` as a background task — the function
    handles its own microphone stream and VAD-based silence endpointing.
    Input ``AudioFrame``s are used only for mic-level visualisation;
    transcription comes from the streaming function.
    ``InterruptFrame`` cancels the streaming worker immediately.
    """

    def __init__(
        self,
        transcribe_fn: Optional[Callable] = None,
        transcribe_streaming_fn: Optional[Callable] = None,
        silence_timeout: float = 0.4,
        energy_threshold: float = 300.0,
        max_duration: float = 15.0,
        interim_interval: float = 1.0,
    ):
        """
        Args:
            transcribe_fn: Sync callable that takes a file path and returns
                           transcribed text.  Used in accumulation mode.
                           Typically ``speech_processor.transcribe``.
            transcribe_streaming_fn: Async generator that yields
                           ``{"type": "interim"|"final", "text": ..., "confidence": ...}``
                           dicts with VAD-based endpointing.
                           Typically ``speech_processor.transcribe_streaming``.
            silence_timeout: Seconds of silence before endpointing (VAD mode).
            energy_threshold: RMS energy floor for silence detection.
            max_duration: Maximum recording duration in seconds.
            interim_interval: How often to yield interim results (seconds).
        """
        self._transcribe_fn = transcribe_fn
        self._transcribe_streaming_fn = transcribe_streaming_fn
        self._silence_timeout = silence_timeout
        self._energy_threshold = energy_threshold
        self._max_duration = max_duration
        self._interim_interval = interim_interval

    async def process_stream(
        self, stream: AsyncIterable[AnyFrame]
    ) -> AsyncIterable[AnyFrame]:
        if self._transcribe_streaming_fn is not None:
            async for frame in self._use_streaming(stream):
                yield frame
        else:
            async for frame in self._use_accumulation(stream):
                yield frame

    # ── VAD streaming path ──────────────────────────────────────────

    async def _use_streaming(
        self, stream: AsyncIterable[AnyFrame]
    ) -> AsyncIterable[AnyFrame]:
        """VAD-based streaming transcription via transcribe_streaming_fn.

        Runs the streaming function as a background task and merges its
        ``TranscriptionFrame`` output with ``MicLevelFrame`` from the
        input audio stream and ``InterruptFrame`` passthrough.
        """
        import asyncio

        queue: asyncio.Queue = asyncio.Queue()
        interrupted = asyncio.Event()

        # ── Streaming worker ────────────────────────────────────────
        async def streaming_worker():
            try:
                async for result in self._transcribe_streaming_fn(
                    max_duration=self._max_duration,
                    silence_timeout=self._silence_timeout,
                    energy_threshold=self._energy_threshold,
                    interim_interval=self._interim_interval,
                ):
                    if interrupted.is_set():
                        break
                    if result["type"] == "interim":
                        await queue.put(TranscriptionFrame(
                            text=result.get("text", ""),
                            confidence=result.get("confidence", 0.0),
                            is_final=False,
                        ))
                    elif result["type"] == "final":
                        text = result.get("text", "").strip()
                        if text:
                            await queue.put(TranscriptionFrame(
                                text=text,
                                confidence=result.get("confidence", 0.0),
                                is_final=True,
                            ))
            except asyncio.CancelledError:
                pass
            finally:
                await queue.put(None)  # sentinel — worker finished

        # ── Input stream consumer ────────────────────────────────────
        async def input_consumer():
            async for frame in stream:
                if isinstance(frame, InterruptFrame):
                    interrupted.set()
                    await queue.put(frame)
                    break
                elif isinstance(frame, AudioFrame):
                    rms = float(np.sqrt(np.mean(
                        frame.data.astype(np.float64) ** 2
                    )))
                    await queue.put(MicLevelFrame(
                        level=min(1.0, rms / 10000.0),
                    ))

        # ── Run both tasks concurrently ─────────────────────────────
        streaming_task = asyncio.create_task(streaming_worker())
        input_task = asyncio.create_task(input_consumer())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break  # streaming finished
                if isinstance(item, InterruptFrame):
                    streaming_task.cancel()
                    yield item
                    break
                yield item
        finally:
            streaming_task.cancel()
            input_task.cancel()
            for t in (streaming_task, input_task):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

    # ── Accumulation path (legacy) ──────────────────────────────────

    async def _use_accumulation(
        self, stream: AsyncIterable[AnyFrame]
    ) -> AsyncIterable[AnyFrame]:
        import tempfile
        import wave
        from pathlib import Path

        audio_frames: list[np.ndarray] = []

        async for frame in stream:
            # Pass InterruptFrame through immediately
            if isinstance(frame, InterruptFrame):
                yield frame
                continue

            if not isinstance(frame, AudioFrame):
                yield frame
                continue

            audio_frames.append(frame.data)

            # Emit live mic level
            rms = float(np.sqrt(np.mean(frame.data.astype(np.float64) ** 2)))
            yield MicLevelFrame(level=min(1.0, rms / 10000.0))

            # Transcribe after accumulating enough audio (~1 second)
            total_samples = sum(len(a) for a in audio_frames)
            if total_samples >= frame.sample_rate:
                # Write accumulated audio to temp WAV
                audio_data = np.concatenate(audio_frames)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    with wave.open(f, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(frame.sample_rate)
                        wf.writeframes(audio_data.tobytes())
                    temp_path = f.name

                try:
                    text = self._transcribe_fn(temp_path)
                    if text.strip():
                        yield TranscriptionFrame(text=text.strip())
                finally:
                    Path(temp_path).unlink(missing_ok=True)

                audio_frames = []

        # Final transcription of remaining audio
        if audio_frames:
            audio_data = np.concatenate(audio_frames)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                with wave.open(f, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(audio_data.tobytes())
                temp_path = f.name

            try:
                text = self._transcribe_fn(temp_path)
                if text.strip():
                    yield TranscriptionFrame(text=text.strip())
            finally:
                Path(temp_path).unlink(missing_ok=True)


class LLMProcessor(FrameProcessor):
    """LLM frame processor.

    Receives ``TranscriptionFrame`` → yields ``LLMResponseFrame``(s)
    via a streaming Ollama-style ``stream_chat_fn``.

    Passes through ``InterruptFrame`` to flush the LLM stream.
    """

    def __init__(
        self,
        stream_chat_fn: Callable[[list[dict]], AsyncIterable[str]],
        get_context_fn: Callable[[], list[dict]],
        add_message_fn: Callable[[str], None],
    ):
        """
        Args:
            stream_chat_fn: Async generator that takes context messages
                            and yields text tokens. Typically
                            ``ollama_client.stream_chat``.
            get_context_fn: Returns the conversation context list.
                            Typically ``conversation.get_context``.
            add_message_fn: Stores assistant response in history.
                            Typically ``conversation.add_assistant_message``.
        """
        self._stream_chat = stream_chat_fn
        self._get_context = get_context_fn
        self._add_message = add_message_fn
        self._interrupted = False

    async def process_stream(
        self, stream: AsyncIterable[AnyFrame]
    ) -> AsyncIterable[AnyFrame]:
        self._interrupted = False

        async for frame in stream:
            # Handle interrupt signals immediately — propagate downstream
            if isinstance(frame, InterruptFrame):
                self._interrupted = True
                yield frame
                continue

            if not isinstance(frame, TranscriptionFrame):
                yield frame
                continue

            if not frame.text.strip():
                continue

            # Stream LLM response
            context = self._get_context()
            from ai.responder import _split_sentences

            buffer = ""
            full_text = ""
            try:
                async for token in self._stream_chat(context):
                    if self._interrupted:
                        break
                    buffer += token
                    full_text += token

                    # Flush at sentence boundaries
                    parts = _split_sentences(buffer)
                    if len(parts) > 1:
                        for sentence in parts[:-1]:
                            if sentence.strip():
                                yield LLMResponseFrame(
                                    text=sentence.strip(),
                                )
                        buffer = parts[-1]

                # Flush remaining buffer
                if buffer.strip() and not self._interrupted:
                    yield LLMResponseFrame(text=buffer.strip(), is_final=True)

                # Store in conversation history
                if full_text.strip():
                    self._add_message(full_text)

            except Exception as e:
                print(f"[LLMProcessor] Error: {e}")
                if not full_text.strip():
                    yield LLMResponseFrame(
                        text="Sorry, I encountered an error.",
                        is_final=True,
                    )


class TTSProcessor(FrameProcessor):
    """Text-to-speech frame processor.

    Receives ``LLMResponseFrame`` → yields ``TTSAudioFrame`` with
    in-memory PCM audio for immediate playback.
    """

    def __init__(self, synthesize_pcm_fn: Callable[[str], tuple[np.ndarray, int]]):
        """
        Args:
            synthesize_pcm_fn: Async callable that takes text and returns
                               ``(pcm_array, sample_rate)``.
                               Typically ``speech_processor.synthesize_pcm``.
        """
        self._synthesize = synthesize_pcm_fn
        self._interrupted = False

    async def process_stream(
        self, stream: AsyncIterable[AnyFrame]
    ) -> AsyncIterable[AnyFrame]:
        self._interrupted = False

        async for frame in stream:
            # Handle interrupt — propagate and stop generating
            if isinstance(frame, InterruptFrame):
                self._interrupted = True
                yield frame
                # Keep consuming & forwarding non-output frames (e.g. MicLevelFrame)
                continue

            if self._interrupted and isinstance(frame, LLMResponseFrame):
                continue

            if not isinstance(frame, LLMResponseFrame):
                yield frame
                continue

            if not frame.text.strip():
                continue

            try:
                pcm, sr = await self._synthesize(frame.text)
                yield TTSAudioFrame(
                    pcm=pcm,
                    sample_rate=sr,
                    text=frame.text,
                )
            except Exception as e:
                print(f"[TTSProcessor] Error: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════

class VoicePipeline:
    """Orchestrates frame processors in sequence.

    ``VoicePipeline`` can be used as an async context manager::

        async with VoicePipeline() as pipeline:
            pipeline.add_stage(stt)
            pipeline.add_stage(llm)
            pipeline.add_stage(tts)
            async for frame in pipeline.run(input_stream):
                if isinstance(frame, TTSAudioFrame):
                    await speaker.play(frame)
    """

    def __init__(self):
        self._stages: list[FrameProcessor] = []
        self._running = False

    def add_stage(self, processor: FrameProcessor):
        """Append a processing stage to the pipeline."""
        self._stages.append(processor)

    async def run(self, input_stream: AsyncIterable[AnyFrame]) -> AsyncIterable[AnyFrame]:
        """Push frames through all stages and yield results.

        Args:
            input_stream: Source frames (e.g. ``AudioFrame`` from mic).
                          May include ``InterruptFrame`` for barge-in.

        Yields:
            Output frames from the final stage(s).
        """
        if not self._stages:
            async for f in input_stream:
                yield f
            return

        self._running = True
        try:
            current: AsyncIterable[AnyFrame] = input_stream
            for stage in self._stages:
                current = stage.process_stream(current)
            async for frame in current:
                yield frame
        finally:
            self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self._running = False


# ═══════════════════════════════════════════════════════════════════════
# Convenience: build a standard pipeline from existing components
# ═══════════════════════════════════════════════════════════════════════

def build_conversation_pipeline(responder, include_stt: bool = True) -> VoicePipeline:
    """Build a standard (STT →) LLM → TTS pipeline from a BARQResponder.

    When ``include_stt=False``, the STT stage is omitted — useful when
    the caller handles STT externally (e.g. ``ConversationListener``
    uses ``transcribe_streaming()`` for VAD-based endpointing and feeds
    ``TranscriptionFrame`` directly into the LLM → TTS stages).

    Args:
        responder: A ``BARQResponder`` instance with ``.speech``,
                   ``.llm``, and ``.conversation`` attributes.
        include_stt: Whether to include the STT processing stage.
                     Defaults to ``True``.

    Returns:
        Configured ``VoicePipeline``.
    """
    pipeline = VoicePipeline()

    if include_stt:
        pipeline.add_stage(STTProcessor(
            transcribe_fn=responder.speech.transcribe,
            transcribe_streaming_fn=responder.speech.transcribe_streaming,
        ))

    pipeline.add_stage(LLMProcessor(
        stream_chat_fn=responder.llm.stream_chat,
        get_context_fn=responder.conversation.get_context,
        add_message_fn=responder.conversation.add_assistant_message,
    ))

    pipeline.add_stage(TTSProcessor(
        synthesize_pcm_fn=responder.speech.synthesize_pcm,
    ))

    return pipeline
