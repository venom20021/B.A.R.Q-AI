"""
FastAPI router for free, no-auth public API integrations.

All endpoints are prefixed with /api/free and return JSON.
"""

from fastapi import APIRouter, Query

from . import clients

router = APIRouter(prefix="/api/free")

# ─── Dictionary & Reference ────────────────────────────────────────────────


@router.get("/dictionary")
async def dictionary(word: str = Query("hello", description="Word to define")):
    """Look up a word definition (Free Dictionary API)."""
    return await clients.fetch_word_definition(word)


@router.get("/random-fact")
async def random_fact():
    """Fetch a random useless fact."""
    return await clients.fetch_random_fact()


@router.get("/joke")
async def random_joke():
    """Fetch a random Chuck Norris joke."""
    return await clients.fetch_chuck_norris_joke()


# ─── Books & Poetry ────────────────────────────────────────────────────────


@router.get("/books")
async def search_books(
    q: str = Query("programming", description="Search query"),
    limit: int = Query(5, ge=1, le=10),
):
    """Search books on Open Library."""
    return await clients.search_open_library(q, limit)


@router.get("/poem")
async def random_poem():
    """Fetch a random poem from PoetryDB."""
    return await clients.fetch_random_poem()


# ─── Finance & Currency ────────────────────────────────────────────────────


@router.get("/currency")
async def currency_rates(
    base: str = Query("USD", description="Base currency code (e.g. USD, EUR, INR)")
):
    """Fetch exchange rates for a base currency."""
    return await clients.fetch_currency_rates(base)


@router.get("/currency/convert")
async def convert_currency(
    amount: float = Query(1.0, description="Amount to convert"),
    from_: str = Query("USD", alias="from", description="Source currency"),
    to: str = Query("EUR", description="Target currency"),
):
    """Convert an amount between currencies."""
    return await clients.convert_currency(amount, from_, to)


@router.get("/currency/list")
async def list_currencies():
    """List all supported currencies."""
    return await clients.list_currencies()


# ─── Productivity Tools ────────────────────────────────────────────────────


@router.get("/ip")
async def ip_info():
    """Get your public IP and geolocation."""
    return await clients.fetch_ip_info()


@router.get("/qrcode")
async def qr_code(
    data: str = Query("https://barq.app", description="Data to encode"),
    size: int = Query(256, ge=128, le=1024, description="QR code size in pixels"),
):
    """Generate a QR code image URL."""
    return await clients.generate_qr_code(data, size)


@router.get("/email/validate")
async def validate_email(
    email: str = Query(..., description="Email address to validate")
):
    """Validate an email address."""
    return await clients.validate_email(email)


# ─── Reference & Demographics ──────────────────────────────────────────────


@router.get("/holidays")
async def public_holidays(
    year: int = Query(2025, ge=2020, le=2030, description="Year"),
    country: str = Query("US", description="ISO 3166-1 alpha-2 country code"),
):
    """Fetch public holidays for a country/year."""
    return await clients.fetch_public_holidays(year, country)


@router.get("/holidays/countries")
async def holiday_countries():
    """List countries supported by the holidays API."""
    return await clients.fetch_supported_holiday_countries()


@router.get("/age")
async def estimate_age(
    name: str = Query(..., description="First name to estimate age for")
):
    """Estimate age from a first name."""
    return await clients.estimate_age(name)


@router.get("/gender")
async def estimate_gender(
    name: str = Query(..., description="First name to estimate gender for")
):
    """Estimate gender from a first name."""
    return await clients.estimate_gender(name)


@router.get("/nationality")
async def estimate_nationality(
    name: str = Query(..., description="First name to estimate nationality for")
):
    """Estimate nationality from a first name."""
    return await clients.estimate_nationality(name)


# ─── Entertainment ─────────────────────────────────────────────────────────


@router.get("/bored")
async def bored_activity():
    """Fetch a random activity suggestion."""
    return await clients.fetch_bored_activity()


@router.get("/games")
async def free_games():
    """Fetch free-to-play games."""
    return await clients.fetch_free_games()


@router.get("/steam-deals")
async def steam_deals(limit: int = Query(5, ge=1, le=20)):
    """Fetch Steam game deals from CheapShark."""
    return await clients.fetch_steam_deals(limit)


@router.get("/steam-deals/search")
async def steam_deals_search(
    title: str = Query(..., description="Game title to search")
):
    """Search Steam deals by game title."""
    return await clients.search_steam_deals(title)


@router.get("/cocktail")
async def cocktail_search(
    name: str = Query("margarita", description="Cocktail name")
):
    """Search cocktails by name."""
    return await clients.search_cocktail(name)


@router.get("/cocktail/random")
async def cocktail_random():
    """Fetch a random cocktail recipe."""
    return await clients.random_cocktail()


@router.get("/nasa/apod")
async def nasa_apod():
    """Fetch NASA Astronomy Picture of the Day."""
    return await clients.fetch_nasa_apod()


@router.get("/trivia")
async def trivia(
    amount: int = Query(5, ge=1, le=20, description="Number of questions")
):
    """Fetch trivia questions."""
    return await clients.fetch_trivia_questions(amount)


@router.get("/dog")
async def random_dog():
    """Fetch a random dog image."""
    return await clients.fetch_random_dog()


@router.get("/cat")
async def random_cat():
    """Fetch a random cat image."""
    return await clients.fetch_random_cat()


@router.get("/jokeapi")
async def random_joke_v2():
    """Fetch a random joke from JokeAPI (variety of categories)."""
    return await clients.fetch_random_joke_api()


@router.get("/rick-morty")
async def rick_morty(
    character_id: int = Query(1, ge=1, le=826, description="Character ID")
):
    """Fetch a Rick and Morty character."""
    return await clients.fetch_rick_morty_character(character_id)


@router.get("/rick-morty/random")
async def rick_morty_random():
    """Fetch a random Rick and Morty character."""
    return await clients.random_rick_morty_character()


@router.get("/star-wars")
async def star_wars(
    character_id: int = Query(1, ge=1, le=83, description="Character ID")
):
    """Fetch a Star Wars character."""
    return await clients.fetch_star_wars_character(character_id)


@router.get("/star-wars/random")
async def star_wars_random():
    """Fetch a random Star Wars character."""
    return await clients.random_star_wars_character()


@router.get("/number-fact")
async def number_fact(
    number: int = Query(42, ge=0, le=999999, description="Number")
):
    """Fetch a fact about a number."""
    return await clients.fetch_number_fact(number)


@router.get("/number-fact/random")
async def random_number_fact():
    """Fetch a random number fact."""
    return await clients.fetch_random_number_fact()
