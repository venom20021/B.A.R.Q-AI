"""
FastAPI routes for web & media: Playwright browsing, Spotify control,
stock market, weather, maps, and image generation.
"""

import asyncio
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import analytics_dao

router = APIRouter()


# ─── Models ───────────────────────────────────────────────────────────────────

class BrowseRequest(BaseModel):
    url: str
    action: str = "navigate"  # navigate, click, screenshot, scrape
    selector: Optional[str] = None

class SpotifyAction(BaseModel):
    action: str  # play, pause, skip, search
    query: Optional[str] = None

class StockRequest(BaseModel):
    ticker: str
    period: str = "1d"  # 1d, 5d, 1mo, 3mo, 1y

class WeatherRequest(BaseModel):
    city: str
    country_code: Optional[str] = None

class ImagePrompt(BaseModel):
    prompt: str
    style: str = "auto"


# ─── Web Agent (Playwright) ───────────────────────────────────────────────────

@router.post("/browse")
async def browse_web(request: BrowseRequest):
    """Control a Playwright browser session."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            if request.action == "navigate":
                await page.goto(request.url, wait_until="domcontentloaded", timeout=30000)
                title = await page.title()
                content = await page.content()
                text = await page.inner_text("body") if await page.query_selector("body") else ""

                await analytics_dao.log_activity(
                    "web", "browse", f"Navigated to: {request.url}"
                )
                return {
                    "status": "navigated",
                    "url": request.url,
                    "title": title,
                    "body_text": text[:2000],
                }

            elif request.action == "screenshot":
                await page.goto(request.url, wait_until="domcontentloaded", timeout=30000)
                screenshot_bytes = await page.screenshot(full_page=True)
                return {"status": "captured", "url": request.url, "size_bytes": len(screenshot_bytes)}

            elif request.action == "scrape":
                await page.goto(request.url, wait_until="domcontentloaded", timeout=30000)
                text = await page.inner_text("body") if await page.query_selector("body") else ""
                links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")

                await analytics_dao.log_activity(
                    "web", "scrape", f"Scraped: {request.url}"
                )
                return {
                    "status": "scraped",
                    "url": request.url,
                    "text": text[:5000],
                    "links": links[:50],
                }

            await browser.close()

    except ImportError:
        return {"status": "unavailable", "message": "Playwright not installed. Run: pip install playwright && playwright install chromium"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/browse/search")
async def web_search(query: str):
    """Perform a web search."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Extract search results
            results = []
            items = await page.query_selector_all("div.g")
            for item in items[:10]:
                try:
                    title_el = await item.query_selector("h3")
                    link_el = await item.query_selector("a")
                    snippet_el = await item.query_selector("div.VwiC3b")

                    title = await title_el.inner_text() if title_el else ""
                    link = await link_el.get_attribute("href") if link_el else ""
                    snippet = await snippet_el.inner_text() if snippet_el else ""

                    if title:
                        results.append({"title": title, "link": link, "snippet": snippet})
                except Exception:
                    continue

            await browser.close()

            return {"results": results, "query": query, "count": len(results)}
    except ImportError:
        return {"status": "unavailable", "message": "Playwright not installed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Spotify Control ──────────────────────────────────────────────────────────

@router.post("/spotify")
async def spotify_control(request: SpotifyAction):
    """Control Spotify playback."""
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        # Expect credentials from env or settings
        from config import get_settings
        settings = get_settings()

        client_id = os_getenv("SPOTIFY_CLIENT_ID", "")
        client_secret = os_getenv("SPOTIFY_CLIENT_SECRET", "")
        redirect_uri = "http://127.0.0.1:8956/callback"

        if not client_id:
            return {"status": "unconfigured", "message": "Spotify credentials not set. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env"}

        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-modify-playback-state user-read-playback-state",
        ))

        if request.action == "play":
            if request.query:
                results = sp.search(q=request.query, type="track", limit=1)
                if results["tracks"]["items"]:
                    sp.start_playback(uris=[results["tracks"]["items"][0]["uri"]])
            else:
                sp.start_playback()
        elif request.action == "pause":
            sp.pause_playback()
        elif request.action == "skip":
            sp.next_track()
        elif request.action == "search":
            results = sp.search(q=request.query or "", type="track", limit=5)
            tracks = [
                {"name": t["name"], "artist": t["artists"][0]["name"],
                 "uri": t["uri"], "album": t["album"]["name"]}
                for t in results["tracks"]["items"]
            ]
            return {"tracks": tracks}

        await analytics_dao.log_activity(
            "web", "spotify", f"Spotify action: {request.action}"
        )
        return {"status": "ok", "action": request.action}
    except ImportError:
        return {"status": "unavailable", "message": "spotipy not installed. Run: pip install spotipy"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Stock Market ─────────────────────────────────────────────────────────────

@router.get("/stocks/{ticker}")
async def get_stock(ticker: str, period: str = "1d"):
    """Get stock price data using Yahoo Finance."""
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.info

        price_data = stock.history(period=period)
        history = []
        for date, row in price_data.iterrows():
            history.append({
                "date": str(date.date()),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })

        await analytics_dao.log_activity(
            "web", "stock", f"Fetched {ticker} stock data"
        )
        return {
            "ticker": ticker.upper(),
            "company": info.get("longName", ticker),
            "current_price": info.get("currentPrice", 0),
            "change_percent": info.get("regularMarketChangePercent", 0),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "dividend_yield": info.get("dividendYield", 0),
            "52_week_high": info.get("fiftyTwoWeekHigh", 0),
            "52_week_low": info.get("fiftyTwoWeekLow", 0),
            "history": history[-30:],  # Last 30 data points
        }
    except ImportError:
        return {"status": "unavailable", "message": "yfinance not installed. Run: pip install yfinance"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks/compare")
async def compare_stocks(tickers: str):
    """Compare multiple stock tickers."""
    try:
        import yfinance as yf

        symbols = [s.strip().upper() for s in tickers.split(",")]
        results = []

        for symbol in symbols:
            stock = yf.Ticker(symbol)
            info = stock.info
            results.append({
                "ticker": symbol,
                "company": info.get("longName", symbol),
                "price": info.get("currentPrice", 0),
                "change": info.get("regularMarketChangePercent", 0),
                "market_cap": info.get("marketCap", 0),
            })

        return {"tickers": results, "count": len(results)}
    except ImportError:
        return {"status": "unavailable", "message": "yfinance not installed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Weather ──────────────────────────────────────────────────────────────────

# WMO weather code → human-readable description
WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


@router.get("/weather")
async def get_weather(city: str):
    """Get current weather for a city using Open-Meteo (free, no API key required)."""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            # 1. Geocode the city name → lat/lon
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "en", "format": "json"},
                timeout=10,
            )
            geo_data = geo_resp.json()
            results = geo_data.get("results")
            if not results:
                raise HTTPException(status_code=404, detail=f"City not found: {city}")

            loc = results[0]
            lat, lon = loc["latitude"], loc["longitude"]
            city_name = loc.get("name", city)
            country = loc.get("country", "")

            # 2. Fetch current weather at those coordinates
            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,visibility",
                },
                timeout=10,
            )
            w = weather_resp.json()
            current = w.get("current", {})

            weather_code = current.get("weather_code", 0)
            description = WMO_CODES.get(weather_code, f"Code {weather_code}")

            await analytics_dao.log_activity(
                "web", "weather", f"Checked weather for {city_name}"
            )
            return {
                "city": city_name,
                "country": country,
                "temperature_c": current.get("temperature_2m", 0),
                "feels_like_c": current.get("apparent_temperature", 0),
                "humidity": current.get("relative_humidity_2m", 0),
                "description": description,
                "wind_speed": current.get("wind_speed_10m", 0),
                "visibility": current.get("visibility", 0),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Maps ─────────────────────────────────────────────────────────────────────

@router.get("/maps/place")
async def search_place(query: str):
    """Search for a place and return map coordinates."""
    try:
        import httpx

        api_key = os_getenv("OPENCAGE_API_KEY", "")

        if not api_key:
            return {"status": "unconfigured", "message": "OpenCage API key not set. Add OPENCAGE_API_KEY to .env"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.opencagedata.com/geocode/v1/json",
                params={"q": query, "key": api_key, "limit": 1},
            )
            data = resp.json()

        if data.get("results"):
            result = data["results"][0]
            geometry = result["geometry"]
            return {
                "query": query,
                "formatted": result.get("formatted", ""),
                "lat": geometry["lat"],
                "lng": geometry["lng"],
                "map_url": f"https://www.openstreetmap.org/?mlat={geometry['lat']}&mlon={geometry['lng']}#map=12/{geometry['lat']}/{geometry['lng']}",
            }
        else:
            raise HTTPException(status_code=404, detail=f"Place not found: {query}")
    except ImportError:
        return {"status": "unavailable", "message": "httpx not installed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/maps/directions")
async def get_directions(origin: str, destination: str):
    """Get directions between two locations."""
    try:
        import httpx
        api_key = os_getenv("OPENCAGE_API_KEY", "")

        if not api_key:
            return {"status": "unconfigured", "message": "OpenCage API key not set"}

        async with httpx.AsyncClient() as client:
            # Geocode origin
            orig_resp = await client.get(
                "https://api.opencagedata.com/geocode/v1/json",
                params={"q": origin, "key": api_key, "limit": 1},
            )
            orig_data = orig_resp.json()
            if not orig_data.get("results"):
                raise HTTPException(status_code=404, detail=f"Origin not found: {origin}")

            # Geocode destination
            dest_resp = await client.get(
                "https://api.opencagedata.com/geocode/v1/json",
                params={"q": destination, "key": api_key, "limit": 1},
            )
            dest_data = dest_resp.json()
            if not dest_data.get("results"):
                raise HTTPException(status_code=404, detail=f"Destination not found: {destination}")

        o = orig_data["results"][0]["geometry"]
        d = dest_data["results"][0]["geometry"]

        await analytics_dao.log_activity(
            "web", "directions", f"Directions: {origin} → {destination}"
        )
        return {
            "origin": {"query": origin, "lat": o["lat"], "lng": o["lng"]},
            "destination": {"query": destination, "lat": d["lat"], "lng": d["lng"]},
            "directions_url": f"https://www.openstreetmap.org/directions?from={o['lat']},{o['lng']}&to={d['lat']},{d['lng']}",
        }
    except ImportError:
        return {"status": "unavailable", "message": "httpx not installed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Image Generation ─────────────────────────────────────────────────────────

@router.post("/images/generate")
async def generate_image(request: ImagePrompt):
    """Generate an image from a text prompt using Pollinations.ai."""
    try:
        import httpx

        # Pollinations.ai - free, no API key needed
        encoded_prompt = request.prompt.replace(" ", "%20")
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

        async with httpx.AsyncClient() as client:
            resp = await client.head(image_url, follow_redirects=True)
            if resp.status_code == 200:
                await analytics_dao.log_activity(
                    "web", "generate_image", f"Generated image: {request.prompt[:50]}"
                )
                return {
                    "status": "generated",
                    "prompt": request.prompt,
                    "image_url": image_url,
                    "style": request.style,
                }

        return {"status": "failed", "message": "Image generation failed"}
    except ImportError:
        return {"status": "unavailable", "message": "httpx not installed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helper(s) ────────────────────────────────────────────────────────────────

def os_getenv(key: str, default: str = "") -> str:
    import os
    return os.getenv(key, default)
