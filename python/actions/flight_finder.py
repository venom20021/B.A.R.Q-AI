"""
Flight Finder — search flights, get results, open in browser.

Uses Playwright to load Google Flights, extracts the page text,
and parses flight data with Gemini.  All functions are async.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger("barq.flight_finder")

_CABIN_CODES: dict[str, str] = {
    "economy": "1",
    "premium": "2",
    "business": "3",
    "first": "4",
}


def _get_api_key() -> Optional[str]:
    try:
        from config import get_settings
        return get_settings().gemini_api_key
    except Exception:
        return None


def _parse_date(raw: str) -> str:
    """Parse a natural language date string to YYYY-MM-DD."""
    raw = raw.strip()
    lower = raw.lower()
    today = datetime.now()

    # Already ISO format
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    # Common formats
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Relative dates
    relative = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "day after tomorrow": today + timedelta(days=2),
    }
    for key, val in relative.items():
        if key in lower:
            return val.strftime("%Y-%m-%d")

    # Month names
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    for month_name, month_num in month_map.items():
        if month_name in lower:
            day_match = re.search(r"(\d{1,2})", raw)
            if day_match:
                day = int(day_match.group(1))
                year = today.year if month_num >= today.month else today.year + 1
                return f"{year}-{month_num:02d}-{day:02d}"

    logger.warning(f"Could not parse date '{raw}' — using today")
    return today.strftime("%Y-%m-%d")


def _build_google_flights_url(
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
    cabin: str = "economy",
) -> str:
    """Build a Google Flights search URL."""
    cabin_code = _CABIN_CODES.get(cabin.lower(), "1")
    base = "https://www.google.com/travel/flights"

    if return_date:
        trip = f"Flights+from+{origin}+to+{destination}+on+{date}+returning+{return_date}"
    else:
        trip = f"Flights+from+{origin}+to+{destination}+on+{date}"

    return (
        f"{base}?q={trip}"
        f"&curr=USD"
        f"&cabin={cabin_code}"
        f"&adults={passengers}"
    )


def _format_spoken(
    flights: list[dict],
    origin: str,
    destination: str,
    date: str,
) -> str:
    """Format flight search results into a spoken summary."""
    if not flights:
        return (
            f"I couldn't find any flights from {origin} to {destination} "
            f"on {date}. The page may not have loaded correctly."
        )

    parts = [f"Here are the top flights from {origin} to {destination} on {date}."]

    for i, f in enumerate(flights[:5], 1):
        airline = f.get("airline", "Unknown")
        departure = f.get("departure", "--:--")
        arrival = f.get("arrival", "--:--")
        duration = f.get("duration", "")
        stops = f.get("stops", 0)
        price = f.get("price", "")
        currency = f.get("currency", "")

        stop_str = "non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
        price_str = f"{price} {currency}".strip() if price else "price unavailable"
        dur_str = f", {duration}" if duration else ""

        parts.append(
            f"Option {i}: {airline}, departing {departure}, "
            f"arriving {arrival}{dur_str}, {stop_str}, {price_str}."
        )

    # Cheapest
    priced = [f for f in flights if f.get("price")]
    if priced:
        cheapest = min(
            priced,
            key=lambda x: int(re.sub(r"[^\d]", "", str(x["price"])) or "999999"),
        )
        parts.append(
            f"The cheapest option is {cheapest.get('airline')} "
            f"at {cheapest.get('price')} {cheapest.get('currency', '')}."
        )

    return " ".join(parts)


async def search_flights(
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
    cabin: str = "economy",
    open_browser: bool = True,
) -> dict[str, Any]:
    """Search for flights using Google Flights via Playwright.

    Opens Google Flights in Playwright, extracts page text,
    and parses flight data using Gemini for structured results.

    Args:
        origin: Departure airport/city code (e.g. "JFK", "New York").
        destination: Arrival airport/city code.
        date: Departure date (natural language or YYYY-MM-DD).
        return_date: Optional return date for round trips.
        passengers: Number of passengers (default 1).
        cabin: Cabin class: economy, premium, business, first.
        open_browser: If True, also open the search in the user's browser.

    Returns:
        Dict with flight results and spoken summary.
    """
    parsed_date = _parse_date(date)
    parsed_return = _parse_date(return_date) if return_date else None

    url = _build_google_flights_url(
        origin, destination, parsed_date, parsed_return, passengers, cabin
    )

    logger.info(f"Flight search: {origin} → {destination} on {parsed_date}")

    # Optionally open in the user's native browser
    if open_browser:
        try:
            import platform
            import subprocess

            system = platform.system()
            if system == "Windows":
                subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
            elif system == "Darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")

    # Try to scrape via Playwright
    raw_text = ""
    try:
        from system_control.browser_control import browser_action

        # Navigate to Google Flights
        nav_result = browser_action("go_to", {"url": url})
        if nav_result and nav_result.get("status") == "error":
            return {
                "status": "partial",
                "url": url,
                "detail": "Opened in your browser. I could not scrape the results automatically.",
            }

        import time
        time.sleep(5)  # Wait for page to load

        # Get page text
        text_result = browser_action("get_text", {})
        if text_result:
            raw_text = text_result if isinstance(text_result, str) else str(text_result)
    except ImportError:
        return {
            "status": "partial",
            "url": url,
            "detail": "Browser control not available. Opened Google Flights in your browser.",
        }
    except Exception as e:
        logger.warning(f"Playwright scrape failed: {e}")

    # Parse flights with Gemini
    flights: list[dict] = []
    if raw_text and len(raw_text) > 100:
        api_key = _get_api_key()
        if api_key:
            try:
                from google import genai as _genai

                client = _genai.Client(api_key=api_key)
                prompt = (
                    f"Extract flight options from {origin} to {destination} on {parsed_date} "
                    f"from this Google Flights page text:\n\n{raw_text[:12000]}\n\n"
                    f"Return a JSON array of up to 5 flights:\n"
                    f'[{{"airline":"...","departure":"HH:MM","arrival":"HH:MM",'
                    f'"duration":"Xh Ym","stops":0,"price":"...","currency":"USD"}}]\n'
                    f"If no flights found, return: []"
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={
                        "system_instruction": (
                            "You are a flight data extraction expert. "
                            "Extract flight information from raw webpage text. "
                            "Return ONLY valid JSON — no markdown, no explanation."
                        )
                    },
                )
                text = re.sub(r"```(?:json)?", "", response.text).strip().rstrip("`").strip()
                flights = json.loads(text)
                if not isinstance(flights, list):
                    flights = []
            except Exception as e:
                logger.warning(f"Gemini parse failed: {e}")
        else:
            logger.warning("No Gemini API key — skipping flight parsing")
    else:
        logger.warning("No page text extracted from Google Flights")

    spoken = _format_spoken(flights, origin, destination, parsed_date)

    return {
        "status": "ok" if flights else "partial",
        "url": url,
        "origin": origin,
        "destination": destination,
        "date": parsed_date,
        "return_date": parsed_return,
        "flights": flights,
        "count": len(flights),
        "summary": spoken,
    }
