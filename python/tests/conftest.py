"""
Shared pytest fixtures for database and route tests.
Creates a fresh in-memory SQLite database per test with defaults seeded,
provides an event loop for async test execution,
and creates a FastAPI app + HTTP client for route testing.

Each test file that needs an HTTP client provides a simple `router` fixture
returning its router, and the shared `app`/`client` fixtures below wire it up.

Memory Management
-----------------
- ``tracemalloc`` is enabled during the session to track allocations.
- A per-test ``memory_warning`` hook warns if a test allocates more than
  ``MEMORY_WARN_MB`` (default 200 MB) between setup and teardown.
- ``--tb=short`` and ``-p no:cacheprovider`` are set via ``pytest.ini``
  to keep peak memory low.
"""

import os
import sys
import tracemalloc
import warnings

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Ensure the python directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.connection import db_connection
from database.schema import initialize_schema, seed_defaults


# ── Memory limit configuration ────────────────────────────────────
# Soft warning threshold (local dev feedback)
MEMORY_WARN_MB = 400
# Hard failure threshold — CI will fail if a test exceeds this
MEMORY_FAIL_MB = 1000


def pytest_configure(config):
    """Enable tracemalloc at session start."""
    tracemalloc.start()


def pytest_unconfigure(config):
    """Stop tracemalloc and report total peak memory."""
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")
    if top_stats:
        total_mib = sum(stat.size for stat in top_stats) / 1024 / 1024
        print(f"\n[Memory] Total tracemalloc peak: {total_mib:.1f} MiB")
    tracemalloc.stop()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item):
    """Snapshot memory before and after each test, fail on excessive use."""
    before = tracemalloc.take_snapshot()
    yield
    after = tracemalloc.take_snapshot()

    # Compute net allocation during this test using compare_to (correct API)
    diff_stats = after.compare_to(before, "lineno")
    diff_size = sum(
        stat.size_diff for stat in diff_stats if stat.size_diff > 0
    ) / 1024 / 1024

    if diff_size > MEMORY_FAIL_MB:
        pytest.fail(
            f"Test '{item.nodeid}' allocated ~{diff_size:.0f} MiB - "
            f"exceeds hard limit of {MEMORY_FAIL_MB} MiB. "
            f"Optimize memory usage or raise the threshold in conftest.py."
        )
    elif diff_size > MEMORY_WARN_MB:
        warnings.warn(
            f"Test '{item.nodeid}' allocated ~{diff_size:.0f} MiB "
            f"(warning threshold: {MEMORY_WARN_MB} MiB). Consider optimizing.",
            ResourceWarning,
        )


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the test session."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """
    Set up a fresh in-memory database for each test.
    All tables and default seed data are created before each test.
    """
    db_connection._db_path = ":memory:"
    db = await db_connection.connect()
    await initialize_schema(db)
    await seed_defaults(db)
    yield
    await db_connection.close()


@pytest.fixture
def app(router):
    """
    Create a fresh FastAPI app with the router provided by the test file.
    Each test file defines a `router` fixture returning its own router.
    """
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
async def client(app):
    """Async HTTP client using ASGI transport (no server needed)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
