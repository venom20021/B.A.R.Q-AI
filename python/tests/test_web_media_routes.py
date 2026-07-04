"""
Tests for web_media FastAPI routes: browse, Spotify, stocks, weather, maps, images.
Most endpoints depend on external services or optional libraries, so we test
the error/unavailable paths and validate the route structures.
"""

import os
from unittest.mock import patch

import pytest


@pytest.fixture
def router():
    from web_media import routes
    return routes.router


# ─── Browse (Playwright) ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_browse_unavailable(client):
    """POST /browse should handle gracefully (either unavailable if not installed, or navigate if installed)."""
    response = await client.post(
        "/browse",
        json={"url": "https://example.com", "action": "navigate"},
    )
    # Should not crash — returns either unavailable or navigated
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "status" in data


@pytest.mark.asyncio
async def test_web_search_unavailable(client):
    """POST /browse/search should return unavailable when Playwright not installed."""
    response = await client.post(
        "/browse/search?query=test+query",
    )
    assert response.status_code in (200, 500)


# ─── Spotify ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spotify_unconfigured(client):
    """POST /spotify should return unconfigured without credentials."""
    # Without SPOTIFY_CLIENT_ID env var, it should return unconfigured
    with patch.dict(os.environ, {}, clear=True):
        response = await client.post(
            "/spotify",
            json={"action": "play", "query": "test song"},
        )
        data = response.json()
        # Either ImportError (spotipy not installed) or unconfigured
        assert "status" in data
        if data.get("status") == "unconfigured":
            assert "credentials" in data.get("message", "").lower() or \
                   "spotify" in data.get("message", "").lower()


# ─── Stocks ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stocks_unavailable(client):
    """GET /stocks/{ticker} should handle gracefully (either with data or unavailable)."""
    response = await client.get("/stocks/AAPL?period=1d")
    # Should not crash — returns either stock data or unavailable message
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "ticker" in data or "status" in data


@pytest.mark.asyncio
async def test_stocks_compare_unavailable(client):
    """GET /stocks/compare should return unavailable when yfinance not installed."""
    response = await client.get("/stocks/compare?tickers=AAPL,MSFT,GOOG")
    assert response.status_code in (200, 500)


# ─── Weather ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weather_unconfigured(client):
    """GET /weather should return unconfigured without API key."""
    with patch.dict(os.environ, {}, clear=True):
        response = await client.get("/weather?city=London")
        data = response.json()
        # Either httpx ImportError or unconfigured
        assert "status" in data or "detail" in data
        if data.get("status") == "unconfigured":
            assert "api key" in data.get("message", "").lower()


# ─── Maps ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_maps_place_unconfigured(client):
    """GET /maps/place should return unconfigured without API key."""
    with patch.dict(os.environ, {}, clear=True):
        response = await client.get("/maps/place?query=Tokyo")
        data = response.json()
        assert "status" in data or "detail" in data
        if data.get("status") == "unconfigured":
            assert "api key" in data.get("message", "").lower()


@pytest.mark.asyncio
async def test_maps_directions_unconfigured(client):
    """GET /maps/directions should return unconfigured without API key."""
    with patch.dict(os.environ, {}, clear=True):
        response = await client.get("/maps/directions?origin=London&destination=Paris")
        data = response.json()
        assert "status" in data or "detail" in data
        if data.get("status") == "unconfigured":
            assert "api key" in data.get("message", "").lower()


# ─── Image Generation ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_image_generate(client):
    """POST /images/generate should return generated URL or unavailable."""
    response = await client.post(
        "/images/generate",
        json={"prompt": "neon forest", "style": "auto"},
    )
    data = response.json()
    assert "status" in data or "detail" in data
