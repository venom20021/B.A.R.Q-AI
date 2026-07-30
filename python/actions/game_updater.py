"""
Game Updater — Steam library management, Epic Games integration.

Scans Steam library via appmanifest_*.acf files, triggers updates
via steam:// protocol URLs, installs new games, and lists Epic library.
"""

import json
import logging
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("barq.game_updater")

_IS_WINDOWS = platform.system() == "Windows"
_IS_MAC = platform.system() == "Darwin"
_IS_LINUX = platform.system() == "Linux"

_CNW: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if _IS_WINDOWS else {}
)

# Known Steam AppIDs for quick lookup
_KNOWN_APPIDS: dict[str, tuple[str, str]] = {
    "pubg": ("578080", "PUBG: Battlegrounds"),
    "gta5": ("271590", "Grand Theft Auto V"),
    "gta v": ("271590", "Grand Theft Auto V"),
    "cs2": ("730", "Counter-Strike 2"),
    "csgo": ("730", "Counter-Strike 2"),
    "dota2": ("570", "Dota 2"),
    "rust": ("252490", "Rust"),
    "valheim": ("892970", "Valheim"),
    "cyberpunk": ("1091500", "Cyberpunk 2077"),
    "elden ring": ("1245620", "ELDEN RING"),
    "minecraft": ("1672970", "Minecraft Launcher"),
    "apex legends": ("1172470", "Apex Legends"),
    "fortnite": ("1517990", "Fortnite"),
    "among us": ("945360", "Among Us"),
    "rocket league": ("252950", "Rocket League"),
    "warframe": ("230410", "Warframe"),
    "destiny 2": ("1085660", "Destiny 2"),
    "team fortress 2": ("440", "Team Fortress 2"),
    "left 4 dead 2": ("550", "Left 4 Dead 2"),
    "war thunder": ("236390", "War Thunder"),
    "path of exile": ("238960", "Path of Exile"),
}

# ─── Steam Path Detection ──────────────────────────────────────────────


def _find_steam_path() -> Optional[Path]:
    """Locate the Steam installation directory."""
    if _IS_WINDOWS:
        return _find_steam_windows()
    if _IS_MAC:
        return _find_steam_mac()
    return _find_steam_linux()


def _find_steam_windows() -> Optional[Path]:
    try:
        import winreg
        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                p = Path(val)
                if p.exists() and (p / "steam.exe").exists():
                    return p
            except Exception:
                continue
    except ImportError:
        pass
    for p in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Steam",
        Path(os.environ.get("ProgramFiles", "")) / "Steam",
    ]:
        if p.exists() and (p / "steam.exe").exists():
            return p
    return None


def _find_steam_mac() -> Optional[Path]:
    p = Path.home() / "Library" / "Application Support" / "Steam"
    return p if p.exists() else None


def _find_steam_linux() -> Optional[Path]:
    for p in [
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    ]:
        if p.exists():
            return p
    return None


def _get_steam_libraries(steam_path: Path) -> list[Path]:
    """Get all Steam library folders."""
    libraries = [steam_path / "steamapps"]
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
    if vdf_path.exists():
        try:
            content = vdf_path.read_text(encoding="utf-8", errors="ignore")
            for raw_path in re.findall(r'"path"\s+"([^"]+)"', content):
                lib = Path(raw_path) / "steamapps"
                if lib.exists() and lib not in libraries:
                    libraries.append(lib)
        except Exception:
            pass
    return libraries


def _parse_acf_state(state: int) -> str:
    """Interpret Steam StateFlags value."""
    if state == 4:
        return "up_to_date"
    if state == 1026:
        return "downloading"
    if state in (6, 516):
        return "update_pending"
    if state == 0:
        return "unknown"
    return f"state_{state}"


# ─── Steam Game Discovery ──────────────────────────────────────────────


def steam_list_games() -> dict[str, Any]:
    """List all installed Steam games with their update status."""
    steam_path = _find_steam_path()
    if not steam_path:
        return {"status": "error", "detail": "Steam not found"}

    games = []
    for lib in _get_steam_libraries(steam_path):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                content = acf.read_text(encoding="utf-8", errors="ignore")
                app_id = re.search(r'"appid"\s+"(\d+)"', content)
                name = re.search(r'"name"\s+"([^"]+)"', content)
                state = re.search(r'"StateFlags"\s+"(\d+)"', content)
                size = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)

                if app_id and name:
                    state_val = int(state.group(1)) if state else 0
                    games.append({
                        "id": app_id.group(1),
                        "name": name.group(1),
                        "state": _parse_acf_state(state_val),
                        "state_code": state_val,
                        "size_bytes": int(size.group(1)) if size else 0,
                    })
            except Exception:
                continue

    return {"status": "ok", "count": len(games), "games": games}


def _get_steam_exe(steam_path: Path) -> Path:
    if _IS_WINDOWS:
        return steam_path / "steam.exe"
    if _IS_MAC:
        return Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
    return steam_path / "steam.sh"


def steam_update_game(game_name: str) -> dict[str, Any]:
    """Trigger update for a specific Steam game.

    Finds the game by name and sends a steam://update/ URL.
    """
    steam_path = _find_steam_path()
    if not steam_path:
        return {"status": "error", "detail": "Steam not found"}

    result = steam_list_games()
    games = result.get("games", [])

    name_lower = game_name.lower()
    targets = [g for g in games if name_lower in g["name"].lower()]

    if not targets:
        return {"status": "error", "detail": f"Game '{game_name}' not found"}

    exe = _get_steam_exe(steam_path)
    results = []
    for game in targets:
        if game["state"] == "up_to_date":
            results.append(f"{game['name']} is already up to date")
        else:
            try:
                url = f"steam://update/{game['id']}"
                subprocess.Popen([str(exe), url], **_CNW)
                results.append(f"Update started for {game['name']}")
            except Exception as e:
                results.append(f"{game['name']}: {e}")

    return {"status": "ok", "detail": ". ".join(results)}


def steam_update_all() -> dict[str, Any]:
    """Trigger updates for all Steam games that need it."""
    steam_path = _find_steam_path()
    if not steam_path:
        return {"status": "error", "detail": "Steam not found"}

    result = steam_list_games()
    games = result.get("games", [])

    exe = _get_steam_exe(steam_path)
    updated = []
    up_to_date = []
    errors = []

    for game in games:
        if game["state"] == "up_to_date":
            up_to_date.append(game["name"])
        elif game["state"] in ("downloading", "update_pending"):
            try:
                url = f"steam://update/{game['id']}"
                subprocess.Popen([str(exe), url], **_CNW)
                updated.append(game["name"])
            except Exception as e:
                errors.append(f"{game['name']}: {e}")

    parts = []
    if updated:
        parts.append(f"Updated: {', '.join(updated[:5])}" + (f" +{len(updated)-5} more" if len(updated) > 5 else ""))
    if up_to_date:
        parts.append(f"{len(up_to_date)} game(s) already up to date")
    if errors:
        parts.append(f"Errors: {'; '.join(errors)}")

    return {"status": "ok", "detail": ". ".join(parts), "updated": len(updated)}


def steam_install_game(game_name: str) -> dict[str, Any]:
    """Install a Steam game by name.

    Searches for the AppID and sends a steam://install/ URL.
    """
    # Check if already installed
    result = steam_list_games()
    for game in result.get("games", []):
        if game_name.lower() in game["name"].lower():
            return {"status": "ok", "detail": f"'{game['name']}' is already installed"}

    # Look up AppID
    app_id = None
    name_lower = game_name.lower()
    if name_lower in _KNOWN_APPIDS:
        app_id, game_name = _KNOWN_APPIDS[name_lower]
    else:
        for key, (aid, cname) in _KNOWN_APPIDS.items():
            if name_lower in key or key in name_lower:
                app_id, game_name = aid, cname
                break

    if not app_id:
        # Try Steam Store API
        try:
            import httpx
            import urllib.parse

            query = urllib.parse.quote(game_name)
            resp = httpx.get(
                f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US",
                headers={"User-Agent": "BARQ/2.0"},
                timeout=10,
            )
            data = resp.json()
            items = data.get("items", [])
            if items:
                app_id = str(items[0]["id"])
                game_name = items[0].get("name", game_name)
        except Exception as e:
            return {"status": "error", "detail": f"Could not find AppID: {e}"}

    if not app_id:
        return {"status": "error", "detail": f"Could not find '{game_name}' on Steam"}

    steam_path = _find_steam_path()
    exe = _get_steam_exe(steam_path) if steam_path else Path("steam")

    try:
        url = f"steam://install/{app_id}"
        subprocess.Popen([str(exe), url], **_CNW)
        return {"status": "ok", "detail": f"Install started for '{game_name}'"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ─── Epic Games ────────────────────────────────────────────────────────


def _find_epic_path() -> Optional[Path]:
    """Locate Epic Games Launcher."""
    if _IS_WINDOWS:
        for p in [
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
        ]:
            if p.exists():
                return p
    if _IS_MAC:
        p = Path("/Applications/Epic Games Launcher.app/Contents/MacOS/EpicGamesLauncher")
        if p.exists():
            return p
    return None


def epic_list_games() -> dict[str, Any]:
    """List games installed via Epic Games Launcher."""
    if _IS_WINDOWS:
        manifests = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    elif _IS_MAC:
        manifests = Path.home() / "Library" / "Application Support" / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    else:
        return {"status": "error", "detail": "Epic Games not supported on Linux"}

    if not manifests.exists():
        return {"status": "error", "detail": "Epic Games not found"}

    games = []
    for item_file in manifests.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            name = data.get("DisplayName") or data.get("AppName", "")
            if name:
                games.append({
                    "id": data.get("AppName", ""),
                    "name": name,
                    "catalog_id": data.get("CatalogItemId", ""),
                })
        except Exception:
            continue

    return {"status": "ok", "count": len(games), "games": games}


# ─── Game Update Check ────────────────────────────────────────────────


def check_game_updates() -> dict[str, Any]:
    """Check which installed games have pending updates.

    Scans Steam library and returns only games that need updating.
    """
    result = steam_list_games()
    if result.get("status") != "ok":
        return result

    games = result.get("games", [])
    pending = [g for g in games if g.get("state") in ("downloading", "update_pending", "state_6", "state_516")]
    up_to_date = [g for g in games if g.get("state") == "up_to_date"]

    return {
        "status": "ok",
        "total_games": len(games),
        "pending_updates": len(pending),
        "up_to_date": len(up_to_date),
        "pending_games": pending,
    }


# ─── Free Games (existing CheapShark / FreeToGame) ────────────────────


async def get_free_games() -> dict[str, Any]:
    """Fetch free-to-play games and Steam deals."""
    import httpx

    results = {}

    # Free games
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.freetogame.com/api/games?sort-by=release-date",
                timeout=10,
            )
            data = resp.json()
            results["free_games"] = [
                {"title": g["title"], "genre": g.get("genre", ""),
                 "platform": g.get("platform", ""), "url": g.get("game_url", "")}
                for g in data[:5]
            ]
    except Exception as e:
        results["free_games_error"] = str(e)

    # Steam deals
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.cheapshark.com/api/1.0/deals",
                params={"upperPrice": 5, "pageSize": 5},
                timeout=10,
            )
            data = resp.json()
            results["steam_deals"] = [
                {"title": d["title"], "sale_price": d.get("salePrice", 0),
                 "normal_price": d.get("normalPrice", 0), "savings": d.get("savings", 0)}
                for d in data[:5]
            ]
    except Exception as e:
        results["steam_deals_error"] = str(e)

    return {"status": "ok", "results": results}
