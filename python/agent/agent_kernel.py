"""
BARQ Agent Kernel — centralized mediation between agents and LLM resources.

Inspired by AIOS (agiresearch/AIOS) kernel architecture. Prevents agent
resource contention by mediating all LLM requests through a single
kernel layer with:

- LLM request queuing (semaphore-based concurrency control)
- Context-window tracking (estimate tokens across conversations)
- Rate limiting (prevent runaway agent loops)
- Health monitoring (track resource usage per agent)

Usage:
    kernel = get_agent_kernel()
    result = await kernel.execute_llm(messages, agent_name="planner")
    status = kernel.get_status()
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from utils.ollama_client import OllamaClient

# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_MAX_CONCURRENT_LLM = 2       # Max simultaneous LLM calls
DEFAULT_RATE_LIMIT_CALLS = 10         # Max LLM calls per agent per window
DEFAULT_RATE_LIMIT_WINDOW = 60        # Rate limit window in seconds
DEFAULT_MAX_CONTEXT_TOKENS = 4096     # Approximate context window limit
DEFAULT_CHARS_PER_TOKEN = 4           # Rough estimate: 1 token ≈ 4 chars
LLM_TIMEOUT_SECONDS = 90              # Per-LLM-call timeout


@dataclass
class AgentLLMUsage:
    """Tracks LLM usage per agent for rate limiting and monitoring."""
    agent_name: str
    total_calls: int = 0
    total_tokens_estimated: int = 0
    total_duration_seconds: float = 0.0
    errors: int = 0
    last_call_at: float = 0.0
    call_timestamps: list[float] = field(default_factory=list)

    @property
    def avg_duration(self) -> float:
        return self.total_duration_seconds / max(self.total_calls, 1)


@dataclass
class ContextWindow:
    """Tracks an active context window (conversation) for token estimation."""
    conversation_id: str
    agent_name: str
    tokens_used: int = 0
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    started_at: float = 0.0
    last_updated_at: float = 0.0
    message_count: int = 0


class AgentKernel:
    """Central kernel that mediates all agent↔LLM interactions.

    All agents (Planner, Executor, Responder) route their LLM calls
    through this kernel to prevent resource contention and provide
    observability.

    Usage:
        kernel = get_agent_kernel()
        response = await kernel.chat(messages, agent_name="planner")
        stats = kernel.get_agent_stats("planner")
    """

    def __init__(
        self,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT_LLM,
        rate_limit_calls: int = DEFAULT_RATE_LIMIT_CALLS,
        rate_limit_window: int = DEFAULT_RATE_LIMIT_WINDOW,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        self._rate_limit_calls = rate_limit_calls
        self._rate_limit_window = rate_limit_window
        self._max_context_tokens = max_context_tokens

        # Per-agent usage tracking
        self._agent_usage: dict[str, AgentLLMUsage] = {}
        self._agent_usage_lock = asyncio.Lock()

        # Active context windows (conversation sessions)
        self._context_windows: dict[str, ContextWindow] = {}
        self._context_lock = asyncio.Lock()

        # Lazy-loaded OllamaClient (created on first use)
        self._llm: Optional[OllamaClient] = None

        # Start background pruning for expired context windows
        self._prune_task: Optional[asyncio.Task] = None
        self._running = False

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the kernel's background pruning loop.

        Safe to call with or without a running event loop (tests,
        production). If no loop is running, pruning is skipped until
        ``start()`` is called again from an async context.
        """
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._prune_task = loop.create_task(self._prune_loop())
        except RuntimeError:
            # No running event loop — pruning will start on first chat call
            pass
        print("[AgentKernel] OK Started")

    async def stop(self) -> None:
        """Stop the kernel gracefully."""
        self._running = False
        if self._prune_task:
            self._prune_task.cancel()
            try:
                await self._prune_task
            except asyncio.CancelledError:
                pass
            self._prune_task = None
        print("[AgentKernel] OK Stopped")

    # ── LLM Request Execution ────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        agent_name: str = "unknown",
        conversation_id: Optional[str] = None,
    ) -> str:
        """Send a conversation to the LLM through the kernel.

        Handles: rate limiting, concurrency control, context tracking,
        and health monitoring.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            agent_name: Name of the calling agent (for monitoring).
            conversation_id: Optional conversation ID for context tracking.

        Returns:
            Generated response text.

        Raises:
            RuntimeError: If rate limited or LLM unavailable.
        """
        # 1. Rate limit check
        if not await self._check_rate_limit(agent_name):
            wait = self._rate_limit_window
            raise RuntimeError(
                f"Agent '{agent_name}' rate limited — max {self._rate_limit_calls} "
                f"calls per {wait}s. Try again later."
            )

        # 2. Track context window
        if conversation_id:
            await self._update_context_window(conversation_id, agent_name, messages)

        # 3. Acquire concurrency slot
        async with self._semaphore:
            start_time = time.monotonic()
            try:
                llm = self._get_llm()
                response = await asyncio.wait_for(
                    llm.chat(messages),
                    timeout=LLM_TIMEOUT_SECONDS,
                )
                duration = time.monotonic() - start_time

                # Update agent usage stats
                await self._record_success(agent_name, messages, response, duration)

                return response

            except asyncio.TimeoutError:
                await self._record_error(agent_name, "timeout")
                raise RuntimeError(
                    f"LLM call timed out after {LLM_TIMEOUT_SECONDS}s for agent '{agent_name}'"
                )
            except Exception as e:
                await self._record_error(agent_name, str(e)[:100])
                raise

    async def stream_chat(
        self,
        messages: list[dict],
        agent_name: str = "unknown",
        conversation_id: Optional[str] = None,
    ):
        """Stream a conversation response through the kernel.

        Yields tokens as they arrive from the LLM.
        """
        if not await self._check_rate_limit(agent_name):
            raise RuntimeError(
                f"Agent '{agent_name}' rate limited — max {self._rate_limit_calls} "
                f"calls per {self._rate_limit_window}s."
            )

        if conversation_id:
            await self._update_context_window(conversation_id, agent_name, messages)

        async with self._semaphore:
            start_time = time.monotonic()
            try:
                llm = self._get_llm()
                full_response = ""
                async for token in llm.stream_chat(messages):
                    full_response += token
                    yield token

                duration = time.monotonic() - start_time
                await self._record_success(agent_name, messages, full_response, duration)

            except Exception as e:
                await self._record_error(agent_name, str(e)[:100])
                raise

    # ── Context Window Management ────────────────────────────────────

    async def open_context(
        self,
        conversation_id: str,
        agent_name: str,
        max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> ContextWindow:
        """Open a new context window for a conversation."""
        async with self._context_lock:
            window = ContextWindow(
                conversation_id=conversation_id,
                agent_name=agent_name,
                max_tokens=max_tokens,
                started_at=time.time(),
                last_updated_at=time.time(),
            )
            self._context_windows[conversation_id] = window
            return window

    async def close_context(self, conversation_id: str) -> None:
        """Close and remove a context window."""
        async with self._context_lock:
            self._context_windows.pop(conversation_id, None)

    async def get_context_usage(self, conversation_id: str) -> Optional[dict]:
        """Get context window usage info."""
        async with self._context_lock:
            cw = self._context_windows.get(conversation_id)
            if not cw:
                return None
            return {
                "conversation_id": cw.conversation_id,
                "agent": cw.agent_name,
                "tokens_used": cw.tokens_used,
                "max_tokens": cw.max_tokens,
                "usage_pct": round(cw.tokens_used / max(cw.max_tokens, 1) * 100, 1),
                "message_count": cw.message_count,
                "duration_seconds": round(time.time() - cw.started_at, 1),
            }

    # ── Monitoring & Status ──────────────────────────────────────────

    async def get_agent_stats(self, agent_name: str) -> Optional[dict]:
        """Get usage statistics for a specific agent."""
        async with self._agent_usage_lock:
            usage = self._agent_usage.get(agent_name)
            if not usage:
                return None
            return {
                "agent": usage.agent_name,
                "total_calls": usage.total_calls,
                "total_tokens_estimated": usage.total_tokens_estimated,
                "total_duration_seconds": round(usage.total_duration_seconds, 2),
                "avg_duration_seconds": round(usage.avg_duration, 2),
                "errors": usage.errors,
                "last_call_at": usage.last_call_at,
            }

    async def get_all_stats(self) -> list[dict]:
        """Get usage statistics for all agents."""
        async with self._agent_usage_lock:
            return [
                {
                    "agent": u.agent_name,
                    "total_calls": u.total_calls,
                    "total_tokens_estimated": u.total_tokens_estimated,
                    "total_duration_seconds": round(u.total_duration_seconds, 2),
                    "avg_duration_seconds": round(u.avg_duration, 2),
                    "errors": u.errors,
                }
                for u in self._agent_usage.values()
            ]

    async def get_status(self) -> dict:
        """Get kernel health status."""
        async with self._agent_usage_lock:
            total_calls = sum(u.total_calls for u in self._agent_usage.values())
            total_errors = sum(u.errors for u in self._agent_usage.values())
            active_agents = len(self._agent_usage)

        async with self._context_lock:
            active_contexts = len(self._context_windows)

        return {
            "status": "running" if self._running else "stopped",
            "max_concurrent": self._max_concurrent,
            "semaphore_available": self._semaphore._value,  # type: ignore
            "active_agents": active_agents,
            "total_llm_calls": total_calls,
            "total_errors": total_errors,
            "error_rate_pct": round(total_errors / max(total_calls, 1) * 100, 1),
            "active_context_windows": active_contexts,
            "rate_limit": {
                "max_calls_per_window": self._rate_limit_calls,
                "window_seconds": self._rate_limit_window,
            },
        }

    # ── Internal Methods ─────────────────────────────────────────────

    def _get_llm(self) -> OllamaClient:
        """Get or create the shared OllamaClient."""
        if self._llm is None:
            self._llm = OllamaClient()
        return self._llm

    async def _check_rate_limit(self, agent_name: str) -> bool:
        """Check if an agent has exceeded its rate limit.

        Uses a sliding window of timestamps.
        """
        async with self._agent_usage_lock:
            usage = self._agent_usage.get(agent_name)
            if not usage:
                return True  # First call from this agent — always allowed

            now = time.time()
            window_start = now - self._rate_limit_window

            # Prune timestamps outside the window
            usage.call_timestamps = [
                t for t in usage.call_timestamps if t > window_start
            ]

            if len(usage.call_timestamps) >= self._rate_limit_calls:
                return False  # Rate limited

            usage.call_timestamps.append(now)
            return True

    async def _update_context_window(
        self,
        conversation_id: str,
        agent_name: str,
        messages: list[dict],
    ) -> None:
        """Update token estimation for a context window."""
        async with self._context_lock:
            cw = self._context_windows.get(conversation_id)
            if not cw:
                cw = ContextWindow(
                    conversation_id=conversation_id,
                    agent_name=agent_name,
                    started_at=time.time(),
                    last_updated_at=time.time(),
                )
                self._context_windows[conversation_id] = cw

            # Estimate tokens from message content
            total_chars = sum(len(m.get("content", "")) for m in messages)
            estimated_tokens = total_chars // DEFAULT_CHARS_PER_TOKEN

            cw.tokens_used = estimated_tokens
            cw.message_count = len(messages)
            cw.last_updated_at = time.time()

    async def _record_success(
        self,
        agent_name: str,
        messages: list[dict],
        response: str,
        duration: float,
    ) -> None:
        """Record a successful LLM call."""
        total_chars = sum(len(m.get("content", "")) for m in messages) + len(response)
        estimated_tokens = total_chars // DEFAULT_CHARS_PER_TOKEN

        async with self._agent_usage_lock:
            usage = self._agent_usage.setdefault(
                agent_name,
                AgentLLMUsage(agent_name=agent_name),
            )
            usage.total_calls += 1
            usage.total_tokens_estimated += estimated_tokens
            usage.total_duration_seconds += duration
            usage.last_call_at = time.time()

    async def _record_error(self, agent_name: str, error_info: str) -> None:
        """Record a failed LLM call."""
        async with self._agent_usage_lock:
            usage = self._agent_usage.setdefault(
                agent_name,
                AgentLLMUsage(agent_name=agent_name),
            )
            usage.total_calls += 1
            usage.errors += 1
            usage.last_call_at = time.time()

    async def _prune_loop(self) -> None:
        """Background loop that prunes expired context windows."""
        CONTEXT_TTL = 1800  # 30 minutes without activity

        while self._running:
            await asyncio.sleep(300)  # Check every 5 minutes
            now = time.time()
            async with self._context_lock:
                expired = [
                    cid for cid, cw in self._context_windows.items()
                    if now - cw.last_updated_at > CONTEXT_TTL
                ]
                for cid in expired:
                    del self._context_windows[cid]
                if expired:
                    print(f"[AgentKernel] Pruned {len(expired)} stale context windows")


# ─── Singleton ──────────────────────────────────────────────────────────────

_kernel: Optional[AgentKernel] = None


def get_agent_kernel() -> AgentKernel:
    """Get or create the global AgentKernel singleton."""
    global _kernel
    if _kernel is None:
        _kernel = AgentKernel()
        _kernel.start()
    return _kernel
