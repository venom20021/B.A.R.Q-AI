"""
Unified HTTP clients for free, no-auth public APIs.

All functions return dicts ready to be JSON-serialized by FastAPI.
Each API has a 'status' field: 'ok' on success, 'error' on failure.
"""

from typing import Optional

import httpx

# ─── Dictionary & Reference ────────────────────────────────────────────────


async def fetch_word_definition(word: str) -> dict:
    """Look up a word definition using the Free Dictionary API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                timeout=10,
            )
            if resp.status_code == 404:
                return {"status": "error", "message": f"Word '{word}' not found"}
            resp.raise_for_status()
            data = resp.json()
            entry = data[0] if isinstance(data, list) else data
            meanings = entry.get("meanings", [])
            definitions = []
            for m in meanings[:3]:
                part_of_speech = m.get("partOfSpeech", "")
                for d in m.get("definitions", [])[:2]:
                    definitions.append({
                        "part_of_speech": part_of_speech,
                        "definition": d.get("definition", ""),
                        "example": d.get("example", ""),
                    })
            return {
                "status": "ok",
                "word": entry.get("word", word),
                "phonetic": entry.get("phonetic", ""),
                "definitions": definitions,
            }
    except httpx.TimeoutException:
        return {"status": "error", "message": "Dictionary API timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def fetch_random_fact() -> dict:
    """Fetch a random useless fact (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://uselessfacts.jsph.pl/api/v2/facts/random?language=en",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "fact": data.get("text", ""),
                "source": data.get("source", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def fetch_chuck_norris_joke() -> dict:
    """Fetch a random Chuck Norris joke (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.chucknorris.io/jokes/random",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "joke": data.get("value", ""),
                "icon_url": data.get("icon_url", ""),
                "id": data.get("id", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Books & Poetry ────────────────────────────────────────────────────────


async def search_open_library(query: str, limit: int = 5) -> dict:
    """Search books on Open Library (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://openlibrary.org/search.json",
                params={"q": query, "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            docs = data.get("docs", [])
            books = []
            for doc in docs[:limit]:
                cover_id = doc.get("cover_i")
                books.append({
                    "title": doc.get("title", ""),
                    "author": ", ".join(doc.get("author_name", [])),
                    "year": doc.get("first_publish_year"),
                    "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
                    "key": doc.get("key", ""),
                    "isbn": doc.get("isbn", [None])[0],
                })
            return {
                "status": "ok",
                "query": query,
                "count": len(books),
                "books": books,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def fetch_random_poem() -> dict:
    """Fetch a random poem from PoetryDB (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://poetrydb.org/random/1",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            poem = data[0] if isinstance(data, list) else data
            return {
                "status": "ok",
                "title": poem.get("title", ""),
                "author": poem.get("author", ""),
                "lines": poem.get("lines", []),
                "linecount": poem.get("linecount", 0),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Finance & Currency ────────────────────────────────────────────────────


async def fetch_currency_rates(base: str = "USD") -> dict:
    """Fetch exchange rates using Frankfurter API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.frankfurter.dev/latest?from={base.upper()}",
                timeout=10,
            )
            if resp.status_code == 404:
                return {"status": "error", "message": f"Currency '{base}' not supported"}
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "base": data.get("base", base),
                "date": data.get("date", ""),
                "rates": data.get("rates", {}),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def convert_currency(amount: float, from_cur: str, to_cur: str) -> dict:
    """Convert currency using Frankfurter API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.frankfurter.dev/latest?from={from_cur.upper()}&to={to_cur.upper()}",
                timeout=10,
            )
            if resp.status_code == 404:
                return {"status": "error", "message": "Currency not supported"}
            resp.raise_for_status()
            data = resp.json()
            rate = data.get("rates", {}).get(to_cur.upper(), 0)
            converted = round(amount * rate, 2)
            return {
                "status": "ok",
                "amount": amount,
                "from": from_cur.upper(),
                "to": to_cur.upper(),
                "rate": rate,
                "converted": converted,
                "date": data.get("date", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def list_currencies() -> dict:
    """List all supported currencies from Frankfurter API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.frankfurter.dev/currencies",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            currencies = [
                {"code": code, "name": name}
                for code, name in data.items()
            ]
            return {
                "status": "ok",
                "count": len(currencies),
                "currencies": currencies,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Productivity Tools ────────────────────────────────────────────────────


async def fetch_ip_info() -> dict:
    """Get public IP and location info (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            # Get IP first
            ip_resp = await client.get("https://api.ipify.org?format=json", timeout=10)
            ip_resp.raise_for_status()
            ip_data = ip_resp.json()
            ip = ip_data.get("ip", "")

            # Then get geolocation
            geo_resp = await client.get(f"http://ip-api.com/json/{ip}?fields=status,country,region,city,zip,lat,lon,isp,org,as,query", timeout=10)
            geo_resp.raise_for_status()
            geo = geo_resp.json()

            return {
                "status": "ok",
                "ip": ip,
                "country": geo.get("country", ""),
                "region": geo.get("region", ""),
                "city": geo.get("city", ""),
                "zip": geo.get("zip", ""),
                "lat": geo.get("lat"),
                "lon": geo.get("lon"),
                "isp": geo.get("isp", ""),
                "organization": geo.get("org", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def generate_qr_code(data: str, size: int = 256) -> dict:
    """Generate a QR code image URL (no auth)."""
    try:
        import urllib.parse
        encoded = urllib.parse.quote(data)
        image_url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}"
        return {
            "status": "ok",
            "data": data,
            "size": size,
            "image_url": image_url,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def validate_email(email: str) -> dict:
    """Validate an email address using EVA API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.eva.pingutil.com/email?email={email}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "email": email,
                "valid": data.get("data", {}).get("valid", False),
                "disposable": data.get("data", {}).get("disposable", False),
                "domain": data.get("data", {}).get("domain", ""),
                "reason": data.get("data", {}).get("reason", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Reference & Demographics ──────────────────────────────────────────────


async def fetch_public_holidays(year: int, country_code: str = "US") -> dict:
    """Fetch public holidays using Nager.Date API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code.upper()}",
                timeout=10,
            )
            if resp.status_code == 404:
                return {"status": "error", "message": f"Country '{country_code}' not found"}
            resp.raise_for_status()
            data = resp.json()
            holidays = [
                {
                    "date": h.get("date", ""),
                    "name": h.get("name", ""),
                    "local_name": h.get("localName", ""),
                    "country": h.get("countryCode", ""),
                    "global": h.get("global", True),
                    "types": h.get("types", []),
                }
                for h in data
            ]
            return {
                "status": "ok",
                "year": year,
                "country": country_code.upper(),
                "count": len(holidays),
                "holidays": holidays,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def fetch_supported_holiday_countries() -> dict:
    """List countries supported by Nager.Date API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://date.nager.at/api/v3/AvailableCountries",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            countries = [
                {"code": c.get("countryCode", ""), "name": c.get("name", "")}
                for c in data
            ]
            return {
                "status": "ok",
                "count": len(countries),
                "countries": countries,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def estimate_age(name: str) -> dict:
    """Estimate age from a first name using Agify.io (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.agify.io?name={name}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "name": data.get("name", name),
                "age": data.get("age"),
                "count": data.get("count", 0),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def estimate_gender(name: str) -> dict:
    """Estimate gender from a first name using Genderize.io (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.genderize.io?name={name}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "name": data.get("name", name),
                "gender": data.get("gender"),
                "probability": data.get("probability", 0),
                "count": data.get("count", 0),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def estimate_nationality(name: str) -> dict:
    """Estimate nationality from a first name using Nationalize.io (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.nationalize.io?name={name}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            countries = [
                {
                    "country_id": c.get("country_id", ""),
                    "probability": round(c.get("probability", 0) * 100, 1),
                }
                for c in data.get("country", [])[:5]
            ]
            return {
                "status": "ok",
                "name": data.get("name", name),
                "countries": countries,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Entertainment ─────────────────────────────────────────────────────────


async def fetch_bored_activity() -> dict:
    """Fetch a random activity to fight boredom (Bored API, no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://bored-api.appbrewery.com/random",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "activity": data.get("activity", ""),
                "type": data.get("type", ""),
                "participants": data.get("participants", 1),
                "price": data.get("price", 0),
                "accessibility": data.get("accessibility", 0),
                "link": data.get("link", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def fetch_free_games() -> dict:
    """Fetch free-to-play games from FreeToGame API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.freetogame.com/api/games?sort-by=release-date",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            games = [
                {
                    "id": g.get("id"),
                    "title": g.get("title", ""),
                    "genre": g.get("genre", ""),
                    "platform": g.get("platform", ""),
                    "publisher": g.get("publisher", ""),
                    "release_date": g.get("release_date", ""),
                    "thumbnail": g.get("thumbnail", ""),
                    "short_description": g.get("short_description", ""),
                    "url": g.get("game_url", ""),
                }
                for g in data[:10]
            ]
            return {
                "status": "ok",
                "count": len(games),
                "games": games,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Steam Deals & Gaming ────────────────────────────────────────────────


async def fetch_steam_deals(limit: int = 10) -> dict:
    """Fetch Steam game deals from CheapShark API (no auth)."""
    try:
        headers = {"User-Agent": "BARQ/2.0 (https://github.com/venom20021/B.A.R.Q-AI)"}
        async with httpx.AsyncClient(headers=headers) as client:
            resp = await client.get(
                "https://www.cheapshark.com/api/1.0/deals",
                params={"upperPrice": 15, "pageSize": limit},
                timeout=10,
            )
            if resp.status_code == 400:
                return {"status": "error", "message": "CheapShark API rejected the request. Try again later or reduce page size."}
            resp.raise_for_status()
            data = resp.json()
            deals = [
                {
                    "title": d.get("title", ""),
                    "sale_price": float(d.get("salePrice", 0)),
                    "normal_price": float(d.get("normalPrice", 0)),
                    "savings": round(float(d.get("savings", 0)), 1),
                    "store_id": d.get("storeID", ""),
                    "deal_rating": d.get("dealRating", ""),
                    "thumb": d.get("thumb", ""),
                    "metacritic_score": d.get("metacriticScore"),
                }
                for d in data[:limit]
            ]
            return {
                "status": "ok",
                "count": len(deals),
                "deals": deals,
            }
    except httpx.HTTPStatusError as e:
        return {"status": "error", "message": f"CheapShark API error: {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def search_steam_deals(title: str) -> dict:
    """Search for Steam game deals by game title (no auth)."""
    try:
        headers = {"User-Agent": "BARQ/2.0 (https://github.com/venom20021/B.A.R.Q-AI)"}
        async with httpx.AsyncClient(headers=headers) as client:
            resp = await client.get(
                "https://www.cheapshark.com/api/1.0/deals",
                params={"title": title, "pageSize": 5},
                timeout=10,
            )
            if resp.status_code == 400:
                return {"status": "error", "message": f"No deals found for '{title}'"}
            resp.raise_for_status()
            data = resp.json()
            deals = [
                {
                    "title": d.get("title", ""),
                    "sale_price": float(d.get("salePrice", 0)),
                    "normal_price": float(d.get("normalPrice", 0)),
                    "savings": round(float(d.get("savings", 0)), 1),
                    "store_id": d.get("storeID", ""),
                    "thumb": d.get("thumb", ""),
                }
                for d in data[:5]
            ]
            return {
                "status": "ok",
                "query": title,
                "count": len(deals),
                "deals": deals,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Cocktails ────────────────────────────────────────────────────────────


async def search_cocktail(name: str) -> dict:
    """Search for cocktails by name using Cocktail DB (free test key)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://www.thecocktaildb.com/api/json/v1/1/search.php?s={name}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            drinks = data.get("drinks", [])
            cocktails = []
            for d in drinks[:5] if drinks else []:
                ingredients = []
                for i in range(1, 16):
                    ing = d.get(f"strIngredient{i}")
                    if ing and ing.strip():
                        measure = d.get(f"strMeasure{i}", "") or ""
                        ingredients.append(f"{measure.strip()} {ing.strip()}".strip())
                cocktails.append({
                    "name": d.get("strDrink", ""),
                    "category": d.get("strCategory", ""),
                    "glass": d.get("strGlass", ""),
                    "instructions": d.get("strInstructions", ""),
                    "ingredients": ingredients,
                    "thumbnail": d.get("strDrinkThumb", ""),
                    "alcoholic": d.get("strAlcoholic", ""),
                })
            return {
                "status": "ok",
                "query": name,
                "count": len(cocktails),
                "cocktails": cocktails,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def random_cocktail() -> dict:
    """Fetch a random cocktail recipe (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.thecocktaildb.com/api/json/v1/1/random.php",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            drinks = data.get("drinks", [])
            if not drinks:
                return {"status": "error", "message": "No cocktail found"}
            d = drinks[0]
            ingredients = []
            for i in range(1, 16):
                ing = d.get(f"strIngredient{i}")
                if ing and ing.strip():
                    measure = d.get(f"strMeasure{i}", "") or ""
                    ingredients.append(f"{measure.strip()} {ing.strip()}".strip())
            return {
                "status": "ok",
                "name": d.get("strDrink", ""),
                "category": d.get("strCategory", ""),
                "glass": d.get("strGlass", ""),
                "instructions": d.get("strInstructions", ""),
                "ingredients": ingredients,
                "thumbnail": d.get("strDrinkThumb", ""),
                "alcoholic": d.get("strAlcoholic", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── NASA ─────────────────────────────────────────────────────────────────


async def fetch_nasa_apod() -> dict:
    """Fetch NASA Astronomy Picture of the Day (DEMO_KEY, no signup needed)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "title": data.get("title", ""),
                "date": data.get("date", ""),
                "explanation": data.get("explanation", ""),
                "image_url": data.get("url", ""),
                "hd_url": data.get("hdurl", ""),
                "media_type": data.get("media_type", ""),
                "copyright": data.get("copyright", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Trivia ───────────────────────────────────────────────────────────────


async def fetch_trivia_questions(amount: int = 5) -> dict:
    """Fetch trivia questions from Open Trivia DB (no auth)."""
    try:
        import html as _html
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://opentdb.com/api.php",
                params={"amount": amount},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            questions = [
                {
                    "category": _html.unescape(q.get("category", "")),
                    "difficulty": q.get("difficulty", ""),
                    "question": _html.unescape(q.get("question", "")),
                    "correct_answer": _html.unescape(q.get("correct_answer", "")),
                    "incorrect_answers": [_html.unescape(a) for a in q.get("incorrect_answers", [])],
                }
                for q in results
            ]
            return {
                "status": "ok",
                "count": len(questions),
                "questions": questions,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Animals ──────────────────────────────────────────────────────────────


async def fetch_random_dog() -> dict:
    """Fetch a random dog image from Dog CEO API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://dog.ceo/api/breeds/image/random",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "image_url": data.get("message", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def fetch_random_cat() -> dict:
    """Fetch a random cat image from Cat API (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.thecatapi.com/v1/images/search?limit=1",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data and len(data) > 0:
                return {
                    "status": "ok",
                    "image_url": data[0].get("url", ""),
                    "width": data[0].get("width", 0),
                    "height": data[0].get("height", 0),
                }
            return {"status": "error", "message": "No cat found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Jokes (JokeAPI) ──────────────────────────────────────────────────────


async def fetch_random_joke_api() -> dict:
    """Fetch a random joke from JokeAPI (no auth, more variety than Chuck)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://v2.jokeapi.dev/joke/Any?type=single",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                return {"status": "error", "message": "Joke API error"}
            return {
                "status": "ok",
                "joke": data.get("joke", ""),
                "category": data.get("category", ""),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Rick and Morty ───────────────────────────────────────────────────────


async def fetch_rick_morty_character(character_id: int = 1) -> dict:
    """Fetch a Rick and Morty character (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://rickandmortyapi.com/api/character/{character_id}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "id": data.get("id"),
                "name": data.get("name", ""),
                "status": data.get("status", ""),
                "species": data.get("species", ""),
                "type": data.get("type", ""),
                "gender": data.get("gender", ""),
                "origin": data.get("origin", {}).get("name", ""),
                "location": data.get("location", {}).get("name", ""),
                "image": data.get("image", ""),
                "episode_count": len(data.get("episode", [])),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def random_rick_morty_character() -> dict:
    """Fetch a random Rick and Morty character."""
    import random
    char_id = random.randint(1, 826)
    return await fetch_rick_morty_character(char_id)


# ─── Star Wars (SWAPI) ────────────────────────────────────────────────────


async def fetch_star_wars_character(character_id: int = 1) -> dict:
    """Fetch a Star Wars character from SWAPI (no auth)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://swapi.dev/api/people/{character_id}/",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "name": data.get("name", ""),
                "height": data.get("height", ""),
                "mass": data.get("mass", ""),
                "hair_color": data.get("hair_color", ""),
                "skin_color": data.get("skin_color", ""),
                "eye_color": data.get("eye_color", ""),
                "birth_year": data.get("birth_year", ""),
                "gender": data.get("gender", ""),
                "homeworld": data.get("homeworld", ""),
                "film_count": len(data.get("films", [])),
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def random_star_wars_character() -> dict:
    """Fetch a random Star Wars character."""
    import random
    char_id = random.randint(1, 83)
    return await fetch_star_wars_character(char_id)


# ─── Numbers (via Numbers API) ────────────────────────────────────────────


async def fetch_number_fact(number: int = 42) -> dict:
    """Fetch an interesting fact about a number.
    Falls back to a generated fact if the API is unreachable."""
    import random as _random
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://numbersapi.com/{number}",
                timeout=5,
            )
            if resp.status_code == 200:
                text = resp.text.strip()
                return {
                    "status": "ok",
                    "number": number,
                    "fact": text,
                }
    except Exception:
        pass

    # Fallback: generate a fun fact locally
    fun_facts = [
        f"{number} is a fascinating number. In binary, it's {bin(number)[2:]}, and in Roman numerals, it's {_to_roman(number) if number < 4000 else 'a large numeral'}.",
        f"Did you know? {number} squared is {number**2}, and its cube is {number**3}.",
        f"Fun fact: {number} is {'even' if number % 2 == 0 else 'odd'}, and its square root is approximately {number**0.5:.4f}.",
        f"{number} is the {_ordinal(number)} number. Its prime factors are: {_prime_factors(number) if number > 1 else 'none (it is 1)'}.",
    ]
    return {
        "status": "ok",
        "number": number,
        "fact": _random.choice(fun_facts),
    }


async def fetch_random_number_fact() -> dict:
    """Fetch a fact about a random number. Uses local generation with API fallback."""
    import random
    number = random.randint(1, 9999)
    return await fetch_number_fact(number)


def _to_roman(num: int) -> str:
    """Convert an integer to Roman numerals."""
    vals = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman = ""
    for i, v in enumerate(vals):
        while num >= v:
            roman += syms[i]
            num -= v
    return roman


def _ordinal(n: int) -> str:
    """Convert an integer to ordinal string (1st, 2nd, 3rd, etc.)."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _prime_factors(n: int) -> str:
    """Return prime factors as a readable string."""
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return ", ".join(str(f) for f in factors) if factors else "prime"
