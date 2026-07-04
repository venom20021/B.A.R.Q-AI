"""
Shared pytest fixtures for database and route tests.
Creates a fresh in-memory SQLite database per test with defaults seeded,
provides an event loop for async test execution,
and creates a FastAPI app + HTTP client for route testing.

Each test file that needs an HTTP client provides a simple `router` fixture
returning its router, and the shared `app`/`client` fixtures below wire it up.
"""

import os
import sys
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Ensure the python directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.connection import db_connection
from database.schema import initialize_schema, seed_defaults


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
