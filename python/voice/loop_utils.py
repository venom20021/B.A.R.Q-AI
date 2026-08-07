"""
Shared event-loop marshaling helpers for the voice pipeline.

The wake-word flow runs the voice conversation on a SEPARATE managed event
loop (created in the Vosk thread — see ``voice/routes.py::_on_wake_word_callback``),
while BARQ's shared aiosqlite connection (``database.connection.db_connection``)
is bound to the MAIN uvicorn loop.  Awaiting main-loop futures from the managed
loop raises "Future attached to a different loop" and corrupts the loop.

These helpers marshal coroutines onto the main loop from any thread/loop so the
voice pipeline can safely reach the backend (DB, jobs, memory, ...) regardless
of which loop the utterance callback runs on.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, Optional

# The backend's main event loop, captured at FastAPI lifespan startup.
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Record the backend's main event loop (call from the FastAPI lifespan)."""
    global _main_loop
    _main_loop = loop


def is_main_loop() -> bool:
    """True if the current thread's running loop IS the main loop.

    When no main loop has been captured (tests, pre-lifespan) this returns
    True so callers fall back to running inline on the current loop.
    """
    loop = _main_loop
    if loop is None:
        return True
    try:
        return asyncio.get_running_loop() is loop
    except RuntimeError:
        return False


# How long a marshaled call may block the calling loop while the main loop
# is busy (job scan, video render, etc.) before giving up and logging.
_MAIN_LOOP_AWAIT_TIMEOUT_S = 10.0


def run_on_main_loop(coro: Coroutine[Any, Any, Any]) -> Optional[concurrent.futures.Future]:
    """Schedule ``coro`` on the main loop (fire-and-forget).

    Safe to call from any thread or loop.  Returns None when no main loop is
    available (e.g. before lifespan startup) so callers can fall back.
    """
    loop = _main_loop
    if loop is None or loop.is_closed() or not loop.is_running():
        return None
    try:
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        # Log background failures instead of letting them vanish silently
        # ("Future exception was never retrieved").
        fut.add_done_callback(_log_background_error)
        return fut
    except RuntimeError:
        return None


def _log_background_error(fut: concurrent.futures.Future) -> None:
    try:
        fut.result()
    except Exception as e:
        print(f"[VoiceLoop] Background task error (non-fatal): {e}")


async def call_on_main_loop(coro: Coroutine[Any, Any, Any]) -> Any:
    """Await ``coro`` on the main loop and return its result (loop-safe).

    If already on the main loop (or no main loop captured), awaits inline —
    so tests and main-loop callers behave exactly as before.  Blocks the
    calling loop for at most ``_MAIN_LOOP_AWAIT_TIMEOUT_S`` while the main
    loop runs the coroutine, then returns None so callers degrade gracefully.
    """
    if is_main_loop() or _main_loop is None or _main_loop.is_closed():
        return await coro
    fut = asyncio.run_coroutine_threadsafe(coro, _main_loop)
    try:
        return fut.result(timeout=_MAIN_LOOP_AWAIT_TIMEOUT_S)
    except Exception as e:
        print(f"[VoiceLoop] Main-loop call timed out/failed (non-fatal): {e}")
        return None
