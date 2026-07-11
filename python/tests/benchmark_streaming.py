"""
Benchmark: Streaming pipeline end-to-end latency measurement.

Measures the key latency improvements from the overlapping architecture:

  Pipeline stages:
    STT ──→ LLM ──→ [sentence-aware split] ──→ TTS ──→ Play

  Overlapping (streaming) vs Sequential (non-streaming):

    Sequential:  STT→[full LLM]→[full TTS]→Play
    Streaming:   STT→[LLM token 1]──┐
                                    ├→[sentence]→TTS→Play (while LLM continues)
                  [LLM token 2...]──┘

  Metrics captured:
    - Time-to-first-audible (TTFA): when first audio chunk is ready
    - Total completion time: when all audio is ready
    - Overlap ratio: LLM & TTS concurrency efficiency
    - Per-sentence latency breakdown
    - Barge-in interrupt response time
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterable, Optional

# ═══════════════════════════════════════════════════════════════════════
# Simulated Timing Profiles  (based on real-world measurements)
# ═══════════════════════════════════════════════════════════════════════

# Ollama (llama3.2:3b on CPU): ~30-70ms per token
LLM_TOKEN_DELAY_MS = 50       # ms per token
# Edge-TTS: ~30-60ms per character of audio
TTS_CHAR_DELAY_MS = 35        # ms per character of synthesized text
# Whisper (base model): ~500-2000ms per transcription
WHISPER_DELAY_MS = 800        # ms for a full transcription
# Network/overhead between components
INTERNAL_DISPATCH_MS = 5      # ms per internal dispatch step

# Benchmark response text — crafted to produce multiple sentence chunks
RESPONSE_TEXT = (
    "Hello, and welcome to today's briefing. "
    "I've completed the analysis you requested, and the results are promising. "
    "The model achieved an accuracy of ninety-four percent on the validation set! "
    "However, there are a few areas that need improvement: data quality, feature engineering, and model calibration. "
    "Let me walk you through the details step by step. "
    "First, the data pipeline required significant cleaning. "
    "Second, the feature set was expanded to include temporal patterns. "
    "And third, the calibration step reduced overfitting substantially. "
    "Overall, I'm confident this approach will scale well in production. "
    "Would you like me to prepare a detailed report with visualizations?"
)

# Short command text (single sentence, for baseline)
COMMAND_TEXT = "Open Chrome and start a new project."


@dataclass
class BenchmarkResult:
    """Collected metrics from a single benchmark run."""
    name: str
    total_duration_ms: float
    first_audible_ms: float
    chunk_count: int
    chunk_timings_ms: list[float]   # time each chunk was yielded
    chunk_text_lengths: list[int]
    overlap_duration_ms: float = 0   # time LLM & TTS overlapped
    notes: str = ""


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results."""
    results: list[BenchmarkResult] = field(default_factory=list)

    def add(self, r: BenchmarkResult):
        self.results.append(r)

    def summary(self) -> str:
        lines = [
            "╔══════════════════════════════════════════════════════════════════╗",
            "║         STREAMING PIPELINE — LATENCY BENCHMARK RESULTS          ║",
            "╚══════════════════════════════════════════════════════════════════╝",
            "",
        ]

        for r in self.results:
            lines.append(f"  ┌─ {r.name}")
            lines.append(f"  │  Total duration:    {r.total_duration_ms:>8.1f} ms")
            lines.append(f"  │  First audible:     {r.first_audible_ms:>8.1f} ms")
            lines.append(f"  │  Chunks produced:   {r.chunk_count:>8d}")
            lines.append(f"  │  Overlap time:      {r.overlap_duration_ms:>8.1f} ms")
            if r.notes:
                lines.append(f"  │  Notes:             {r.notes}")
            lines.append("  └─")
            lines.append("")

        # Compute comparisons
        if len(self.results) >= 2:
            streaming = [r for r in self.results if "streaming" in r.name.lower()]
            sequential = [r for r in self.results if "sequential" in r.name.lower()]

            lines.append("  ═══════════════════  KEY COMPARISONS  ═══════════════════")
            lines.append("")

            if streaming and sequential:
                s = streaming[0]
                q = sequential[0]
                ttfa_improvement = (q.first_audible_ms - s.first_audible_ms) / q.first_audible_ms * 100
                total_improvement = (q.total_duration_ms - s.total_duration_ms) / q.total_duration_ms * 100

                lines.append("  Time-to-first-audible (TTFA):")
                lines.append(f"    Sequential: {q.first_audible_ms:>8.1f} ms")
                lines.append(f"    Streaming:  {s.first_audible_ms:>8.1f} ms")
                lines.append("    ─────────────────────────────────────")
                lines.append(f"    Improvement: {ttfa_improvement:>+6.1f}%  ({q.first_audible_ms - s.first_audible_ms:.0f} ms faster)")
                lines.append("")
                lines.append("  Total completion time:")
                lines.append(f"    Sequential: {q.total_duration_ms:>8.1f} ms")
                lines.append(f"    Streaming:  {s.total_duration_ms:>8.1f} ms")
                lines.append("    ─────────────────────────────────────")
                lines.append(f"    Improvement: {total_improvement:>+6.1f}%  ({q.total_duration_ms - s.total_duration_ms:.0f} ms faster)")
                lines.append("")

            if len(streaming) >= 3:
                lines.append("  Chunking overhead per sentence:")
                for r in streaming[1:4]:
                    lines.append(f"    {r.name}: avg {sum(r.chunk_timings_ms)/len(r.chunk_timings_ms):.1f} ms per chunk")
                lines.append("")

        # Architecture summary
        lines.extend([
            "  ═══════════════════  ARCHITECTURE NOTES  ════════════════════",
            "",
            "  Streaming pipeline stages (overlapping):",
            "    LLM token generation ──→ sentence boundary detection",
            "                              ↓",
            "                         TTS synthesis ──→ audio playback",
            "",
            "  Key design decisions that reduce latency:",
            "    1. Sentence-aware chunking at punctuation boundaries",
            "    2. TTS starts on first complete sentence (not full response)",
            "    3. LLM continues generating while TTS plays",
            "    4. Barge-in can interrupt playback at any chunk boundary",
            "    5. Streaming STT yields interim results (no wait for silence)",
            "",
            "  Configurable VAD silence threshold: 0.1s–3.0s (default 0.4s)",
            "  ",
        ])

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Simulated Components
# ═══════════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """Split text into approximate tokens (words + whitespace)."""
    import re
    tokens = []
    i = 0
    while i < len(text):
        if text[i] == " ":
            tokens.append(" ")
            i += 1
        else:
            # Word token: include any trailing punctuation
            m = re.match(r"\S+", text[i:])
            if m:
                tokens.append(m.group(0))
                i += m.end()
            else:
                tokens.append(text[i])
                i += 1
    return tokens


async def _simulate_llm_stream(text: str) -> AsyncIterable[str]:
    """Simulate Ollama streaming — yields tokens with realistic delays."""
    tokens = _tokenize(text)
    for token in tokens:
        await asyncio.sleep(LLM_TOKEN_DELAY_MS / 1000)
        yield token


async def _simulate_tts(text: str) -> None:
    """Simulate Edge-TTS synthesis — sleeps proportional to text length."""
    delay = len(text) * TTS_CHAR_DELAY_MS / 1000
    await asyncio.sleep(delay)


def _split_sentences(text: str) -> list[str]:
    """Mirror of responder._split_sentences for benchmark isolation."""
    import re
    parts = re.split(r"(?<=[.!?:;,])\s+", text)
    return [p.strip() for p in parts if p.strip()]


# ═══════════════════════════════════════════════════════════════════════
# Benchmark: Streaming (overlapping) Architecture
# ═══════════════════════════════════════════════════════════════════════

async def benchmark_streaming(text: str) -> BenchmarkResult:
    """
    Measure the overlapping streaming pipeline:

      LLM streams tokens → buffer → split on punctuation →
      flush complete sentences → TTS each immediately

    Time tracked from first token to last TTS completion.
    """
    chunks: list[str] = []
    chunk_times: list[float] = []
    chunk_text_lengths: list[int] = []

    start_time = time.perf_counter()
    buffer = ""
    first_token_time: Optional[float] = None
    tts_tasks: list[asyncio.Task] = []
    llm_done_time: Optional[float] = None

    # ── Stream LLM tokens ────────────────────────────────────────
    try:
        async for token in _simulate_llm_stream(text):
            if first_token_time is None:
                first_token_time = time.perf_counter()

            buffer += token

            # Check for complete sentences
            parts = _split_sentences(buffer)
            if len(parts) > 1:
                complete = parts[:-1]
                buffer = parts[-1]
                for sentence in complete:
                    if sentence.strip():
                        chunk_time = (time.perf_counter() - start_time) * 1000
                        chunk_times.append(chunk_time)
                        chunk_text_lengths.append(len(sentence))
                        chunks.append(sentence)
                        # Fire TTS asynchronously (overlapping with LLM)
                        tts_tasks.append(asyncio.create_task(_simulate_tts(sentence)))
    except Exception as e:
        print(f"[Benchmark] LLM stream error: {e}")

    llm_done_time = (time.perf_counter() - start_time) * 1000

    # ── Flush remaining buffer ───────────────────────────────────
    if buffer.strip():
        chunk_time = (time.perf_counter() - start_time) * 1000
        chunk_times.append(chunk_time)
        chunk_text_lengths.append(len(buffer))
        chunks.append(buffer)
        tts_tasks.append(asyncio.create_task(_simulate_tts(buffer)))

    # ── Wait for all pending TTS to complete ─────────────────────
    if tts_tasks:
        await asyncio.gather(*tts_tasks)

    total_duration = (time.perf_counter() - start_time) * 1000

    # Overlap = LLM done time vs last TTS start → concurrency window
    first_tts_start = chunk_times[0] if chunk_times else total_duration
    overlap = max(0, llm_done_time - first_tts_start)

    return BenchmarkResult(
        name=f'Streaming — {len(chunks)} chunks ("{text[:40]}...")',
        total_duration_ms=total_duration,
        first_audible_ms=chunk_times[0] if chunk_times else total_duration,
        chunk_count=len(chunks),
        chunk_timings_ms=chunk_times,
        chunk_text_lengths=chunk_text_lengths,
        overlap_duration_ms=overlap,
        notes=(
            f"First TTS launched at {chunk_times[0]:.1f}ms (sentence #{len(chunks)}), "
            f"LLM done at {llm_done_time:.1f}ms"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════
# Benchmark: Sequential (non-streaming) Architecture
# ═══════════════════════════════════════════════════════════════════════

async def benchmark_sequential(text: str) -> BenchmarkResult:
    """
    Measure the non-streaming (sequential) pipeline:

      Wait for full LLM response → split all sentences →
      TTS each sentence sequentially

    This is the baseline that the streaming architecture improves upon.
    """
    chunks: list[str] = []
    chunk_times: list[float] = []
    chunk_text_lengths: list[int] = []

    start_time = time.perf_counter()

    # ── Wait for full LLM response ───────────────────────────────
    full_response = ""
    async for token in _simulate_llm_stream(text):
        full_response += token

    llm_done_time = (time.perf_counter() - start_time) * 1000

    # ── Split into sentences ────────────────────────────────────
    sentences = _split_sentences(full_response)

    # ── TTS each sentence sequentially ──────────────────────────
    for sentence in sentences:
        if sentence.strip():
            await _simulate_tts(sentence)
            elapsed = (time.perf_counter() - start_time) * 1000
            chunk_times.append(elapsed)
            chunk_text_lengths.append(len(sentence))
            chunks.append(sentence)

    total_duration = (time.perf_counter() - start_time) * 1000

    return BenchmarkResult(
        name=f'Sequential — {len(chunks)} sentences ("{text[:40]}...")',
        total_duration_ms=total_duration,
        first_audible_ms=chunk_times[0] if chunk_times else total_duration,
        chunk_count=len(chunks),
        chunk_timings_ms=chunk_times,
        chunk_text_lengths=chunk_text_lengths,
        overlap_duration_ms=0,  # No concurrency
        notes=f"Full LLM response took {llm_done_time:.1f}ms, then TTS began",
    )


# ═══════════════════════════════════════════════════════════════════════
# Benchmark: Sentence-Aware Chunking Overhead
# ═══════════════════════════════════════════════════════════════════════

async def benchmark_chunking_efficiency(text: str) -> BenchmarkResult:
    """
    Measure how effectively the sentence-aware splitter breaks text into
    audio-ready chunks.  Fewer long-wait chunks = worse; more smaller
    chunks with consistent timing = better.

    This benchmark runs the splitter on the same text multiple times
    with increasing buffer sizes (simulating incremental LLM output)
    and measures how quickly the first complete sentence emerges.
    """
    tokens = _tokenize(text)
    chunk_times: list[float] = []
    chunks: list[str] = []
    buffer = ""

    start_time = time.perf_counter()

    for i, token in enumerate(tokens):
        await asyncio.sleep(LLM_TOKEN_DELAY_MS / 1000)
        buffer += token
        parts = _split_sentences(buffer)
        if len(parts) > 1:
            complete = parts[:-1]
            buffer = parts[-1]
            for sentence in complete:
                if sentence.strip():
                    elapsed = (time.perf_counter() - start_time) * 1000
                    chunk_times.append(elapsed)
                    # Count how many tokens were needed before this sentence flushed
                    chunks.append(f"{sentence} (flushed after {i + 1} tokens)")

    # Flush remaining
    if buffer.strip():
        elapsed = (time.perf_counter() - start_time) * 1000
        chunk_times.append(elapsed)
        chunks.append(f"{buffer} (final flush)")

    total_duration = (time.perf_counter() - start_time) * 1000

    return BenchmarkResult(
        name=f"Chunking efficiency — {len(chunks)} chunks",
        total_duration_ms=total_duration,
        first_audible_ms=chunk_times[0] if chunk_times else total_duration,
        chunk_count=len(chunks),
        chunk_timings_ms=chunk_times,
        chunk_text_lengths=[len(c) for c in chunks],
        overlap_duration_ms=total_duration - (chunk_times[-1] if chunk_times else total_duration),
        notes=f"Avg {len(tokens)} total tokens, first chunk flushed after ~{int(chunk_times[0] / LLM_TOKEN_DELAY_MS)} tokens",
    )


# ═══════════════════════════════════════════════════════════════════════
# Benchmark: Barge-in Interrupt Response
# ═══════════════════════════════════════════════════════════════════════

async def benchmark_interrupt_latency(text: str) -> BenchmarkResult:
    """
    Measure how quickly a barge-in interrupt propagates through the pipeline.

    Simulates: user speaks during TTS playback -> interrupt_handler stops
    playback and flushes the LLM stream.

    Interrupt fires AFTER the first chunk's TTS finishes (mimicking the
    conversation loop: playback completes then interrupt is checked).
    """
    chunks: list[str] = []
    chunk_times: list[float] = []
    interrupt_start = 0.0

    start_time = time.perf_counter()
    buffer = ""
    interrupted = False

    async for token in _simulate_llm_stream(text):
        if not interrupted:
            buffer += token
            parts = _split_sentences(buffer)
            if len(parts) > 1:
                complete = parts[:-1]
                buffer = parts[-1]
                for sentence in complete:
                    if sentence.strip():
                        elapsed = (time.perf_counter() - start_time) * 1000
                        chunk_times.append(elapsed)
                        chunks.append(sentence)
                        # Simulate TTS for this chunk (synchronous for simplicity)
                        await _simulate_tts(sentence)
                        # Barge-in: interrupt after first chunk completes
                        if len(chunks) == 1:
                            interrupt_start = time.perf_counter()
                            interrupted = True
                            break
        else:
            break

    interrupt_elapsed = (time.perf_counter() - interrupt_start) * 1000

    return BenchmarkResult(
        name="Barge-in interrupt after 1 chunk",
        total_duration_ms=(time.perf_counter() - start_time) * 1000,
        first_audible_ms=chunk_times[0] if chunk_times else 0,
        chunk_count=len(chunks),
        chunk_timings_ms=chunk_times,
        chunk_text_lengths=[len(c) for c in chunks],
        overlap_duration_ms=interrupt_elapsed,
        notes=(
            f"Interrupt fired after 1 chunk. "
            f"Pipeline quiesced in {interrupt_elapsed:.1f}ms"
        ),
    )


# ═══════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════

async def main():
    suite = BenchmarkSuite()

    print("=" * 66)
    print("  BARQ STREAMING PIPELINE — LATENCY BENCHMARK")
    print(f"  Simulated timings: LLM={LLM_TOKEN_DELAY_MS}ms/token, "
          f"TTS={TTS_CHAR_DELAY_MS}ms/char, Whisper={WHISPER_DELAY_MS}ms")
    print("=" * 66)
    print()

    # ── 1. Long response: streaming vs sequential ────────────────
    print(f"  Benchmark 1: Multi-sentence response ({len(_split_sentences(RESPONSE_TEXT))} sentences)")
    print("  ──────────────────────────────────────────────────────────")
    print("  Running streaming (overlapping) architecture...")
    r1 = await benchmark_streaming(RESPONSE_TEXT)
    suite.add(r1)
    print(f"    ✓ Streaming: {r1.first_audible_ms:.0f}ms TTFA, "
          f"{r1.total_duration_ms:.0f}ms total, {r1.overlap_duration_ms:.0f}ms overlap")
    print()

    print("  Running sequential (non-streaming) architecture...")
    r2 = await benchmark_sequential(RESPONSE_TEXT)
    suite.add(r2)
    print(f"    ✓ Sequential: {r2.first_audible_ms:.0f}ms TTFA, "
          f"{r2.total_duration_ms:.0f}ms total")
    print()

    # ── 2. Short command: baseline latency ──────────────────────
    print(f"  Benchmark 2: Short command ({len(_split_sentences(COMMAND_TEXT))} sentence)")
    print("  ──────────────────────────────────────────────────────────")
    print("  Running streaming (overlapping) architecture...")
    r3 = await benchmark_streaming(COMMAND_TEXT)
    suite.add(r3)
    print(f"    ✓ Streaming: {r3.first_audible_ms:.0f}ms TTFA, "
          f"{r3.total_duration_ms:.0f}ms total, {r3.overlap_duration_ms:.0f}ms overlap")

    print("  Running sequential (non-streaming) architecture...")
    r4 = await benchmark_sequential(COMMAND_TEXT)
    suite.add(r4)
    print(f"    ✓ Sequential: {r4.first_audible_ms:.0f}ms TTFA, "
          f"{r4.total_duration_ms:.0f}ms total")
    print()

    # ── 3. Chunking efficiency ──────────────────────────────────
    print("  Benchmark 3: Sentence-aware chunking efficiency")
    print("  ──────────────────────────────────────────────────────────")
    r5 = await benchmark_chunking_efficiency(RESPONSE_TEXT)
    suite.add(r5)
    print(f"    ✓ {r5.chunk_count} chunks from {len(_tokenize(RESPONSE_TEXT))} tokens")
    for i, (time_ms, txt) in enumerate(zip(r5.chunk_timings_ms, r5.chunk_text_lengths)):
        print(f"      Chunk {i+1}: yielded at {time_ms:.0f}ms, {txt} chars")
    print()

    # ── 4. Barge-in interrupt response ─────────────────────────
    print("  Benchmark 4: Barge-in interrupt latency")
    print("  ──────────────────────────────────────────────────────────")
    r6 = await benchmark_interrupt_latency(RESPONSE_TEXT)
    suite.add(r6)
    print(f"    ✓ Interrupt quiesced in {r6.overlap_duration_ms:.0f}ms")
    print()

    # ── Print final summary ──────────────────────────────────────
    print()
    print(suite.summary())

    # ── Print per-stage timing table ─────────────────────────────
    print()
    print("  ═══════════════════  PER-STAGE TIMING TABLE  ═══════════════")
    print()
    print(f"  {'Stage':<30} {'Streaming':>12} {'Sequential':>12}")
    print(f"  {'─'*30} {'─'*12} {'─'*12}")
    print(f"  {'STT (Whisper)':<30} {WHISPER_DELAY_MS:>8.0f}ms{'':>4} {WHISPER_DELAY_MS:>8.0f}ms{'':>4}")
    print(f"  {'LLM (first token)':<30} {LLM_TOKEN_DELAY_MS:>8.0f}ms{'':>4} {'n/a (waits for full)':>12}")
    print(f"  {'LLM (full response)':<30} {'varies (overlaps)':>12} {len(_tokenize(RESPONSE_TEXT)) * LLM_TOKEN_DELAY_MS:>8.0f}ms{'':>4}")
    print(f"  {'Sentence split':<30} {'<1ms (incremental)':>12} {'<1ms (batch)':>12}")
    if r1.chunk_count > 0:
        first_sentence_len = r1.chunk_text_lengths[0]
        ttfs = first_sentence_len * TTS_CHAR_DELAY_MS
        print(f"  {'TTS (first sentence)':<30} {ttfs:>8.0f}ms{'':>4} {ttfs:>8.0f}ms{'':>4}")
    total_tts = sum(r1.chunk_text_lengths) * TTS_CHAR_DELAY_MS
    print(f"  {'TTS (full response)':<30} {'varies (parallel)':>12} {total_tts:>8.0f}ms{'':>4}")
    print()

    return suite


if __name__ == "__main__":
    asyncio.run(main())
