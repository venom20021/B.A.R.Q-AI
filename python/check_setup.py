"""
BARQ Setup Checker
──────────────────
Scans all API keys and credentials across .env and config files,
reports which are configured, and optionally verifies connectivity.

Usage:
    python python/check_setup.py              # basic check
    python python/check_setup.py --verify     # also ping live endpoints
    python python/check_setup.py --json       # machine-readable JSON output
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ─── ANSI colors ────────────────────────────────────────────────────────────
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# ─── Project root ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
API_KEYS_JSON_PATH = PROJECT_ROOT / "python" / "config" / "api_keys.json"


# ─── Key definitions ────────────────────────────────────────────────────────
# Each entry: (env_var_name, source_description, is_required, verify_type, hints)
KeyDef = tuple[str, str, bool, Optional[str], str]

KEYS: list[KeyDef] = [
    # ── Core ──
    ("BARQ_API_KEY", ".env (BARQ_API_KEY)", False, None,
     "Auto-generated if empty. Set to make permanent."),

    # ── AI / LLM ──
    ("GEMINI_API_KEY", ".env or config/api_keys.json", True, "gemini",
     "Get one: https://aistudio.google.com/apikey"),
    ("OPENAI_API_KEY", ".env (OPENAI_API_KEY)", False, "openai",
     "Get one: https://platform.openai.com/api-keys"),

    # ── Career / Jobs ──
    ("LINKEDIN_EMAIL", ".env (LINKEDIN_EMAIL)", False, None,
     "Your LinkedIn account email"),
    ("LINKEDIN_PASSWORD", ".env (LINKEDIN_PASSWORD)", False, None,
     "Your LinkedIn account password"),

    # ── Notifications ──
    ("TELEGRAM_BOT_TOKEN", ".env (TELEGRAM_BOT_TOKEN)", False, "telegram",
     "Create a bot: https://t.me/BotFather"),
    ("TELEGRAM_CHAT_ID", ".env (TELEGRAM_CHAT_ID)", False, None,
     "Find your chat ID via @userinfobot"),
    ("SMTP_USER", ".env (SMTP_USER)", False, None,
     "Gmail address for email notifications"),
    ("SMTP_PASS", ".env (SMTP_PASS)", False, None,
     "Google App Password: https://myaccount.google.com/apppasswords"),
    ("NOTIFICATION_EMAIL", ".env (NOTIFICATION_EMAIL)", False, None,
     "Recipient email for notifications"),

    # ── Social / Content ──
    ("YOUTUBE_API_KEY", ".env (YOUTUBE_API_KEY)", False, None,
     "Enable YouTube Data API in Google Cloud Console"),
    ("TWITTER_API_KEY", ".env (TWITTER_API_KEY)", False, None,
     "https://developer.twitter.com"),
    ("TWITTER_API_SECRET", ".env (TWITTER_API_SECRET)", False, None,
     "Same portal as above"),
    ("INSTAGRAM_ACCESS_TOKEN", ".env (INSTAGRAM_ACCESS_TOKEN)", False, None,
     "Facebook Developer portal (commented in .env.example)"),

    # ── Voice / Assistant ──
    ("OPENWEATHER_API_KEY", ".env (OPENWEATHER_API_KEY)", False, None,
     "https://openweathermap.org/api - free tier"),
    ("NEWS_API_KEY", ".env (NEWS_API_KEY)", False, None,
     "https://newsapi.org/register - free tier"),
    ("GITHUB_TOKEN", ".env (GITHUB_TOKEN)", False, None,
     "https://github.com/settings/tokens"),
]


def c(text: str, color_code: str) -> str:
    """Wrap text in ANSI color if stdout is a terminal."""
    if sys.stdout.isatty():
        return f"{color_code}{text}{RESET}"
    return text


def b(text: str) -> str:
    """Bold text via ANSI if terminal supports it."""
    return c(text, BOLD) if sys.stdout.isatty() else text


# ─── File loaders ───────────────────────────────────────────────────────────

def load_env_file() -> dict[str, str]:
    """Parse .env file and return a dict of key=value pairs."""
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)$', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip().strip("\"'")
            env[key] = value
    return env


def load_api_keys_json() -> dict[str, str]:
    """Parse config/api_keys.json if it exists."""
    if API_KEYS_JSON_PATH.exists():
        try:
            return json.loads(API_KEYS_JSON_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return {}
    return {}


def get_key_value(var_name: str, env: dict[str, str], json_config: dict[str, str]) -> str:
    """Look up a key value from multiple sources (.env, api_keys.json, os.environ)."""
    if var_name in env and env[var_name]:
        return env[var_name]
    json_key_map = {"GEMINI_API_KEY": "gemini_api_key"}
    json_key = json_key_map.get(var_name, var_name.lower())
    if json_key in json_config and json_config[json_key]:
        return json_config[json_key]
    if os.getenv(var_name, ""):
        return os.getenv(var_name, "")
    return ""


# ─── Live verification ──────────────────────────────────────────────────────

def verify_gemini(api_key: str) -> tuple[bool, str]:
    try:
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key}, timeout=5,
        )
        if resp.status_code == 200:
            return (True, "Connected (models accessible)")
        return (False, f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        return (False, f"Connection failed: {e}")


def verify_openai(api_key: str) -> tuple[bool, str]:
    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=5,
        )
        if resp.status_code == 200:
            return (True, "Connected (models accessible)")
        return (False, f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        return (False, f"Connection failed: {e}")


def verify_telegram(bot_token: str) -> tuple[bool, str]:
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getMe", timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                uname = data["result"].get("username", "?")
                name = data["result"].get("first_name", "Unknown")
                return (True, f"Bot @{uname} ({name}) is live")
        return (False, "Invalid bot token")
    except requests.RequestException as e:
        return (False, f"Connection failed: {e}")


def verify_ollama(host: str = "http://127.0.0.1:11434") -> tuple[bool, str]:
    try:
        resp = requests.get(host.rstrip("/") + "/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            names = [m["name"] for m in models]
            return (True, f"Running - {len(models)} model(s): {', '.join(names[:5])}")
        return (False, f"HTTP {resp.status_code}")
    except requests.RequestException:
        return (False, f"Not reachable at {host}")


# ─── Pretty-print helpers (all ASCII-safe) ─────────────────────────────────

_SEP = "=" * 60
_DASH = "-" * 50


def print_header(text: str):
    print(f"\n  {c(_SEP, DIM)}")
    print(f"  {b(c(text, CYAN))}")
    print(f"  {c(_SEP, DIM)}")


def print_footer(passed: int, total: int):
    score = f"{passed}/{total}"
    pct = (passed / total * 100) if total > 0 else 0
    if pct == 100:
        msg = c(f"  [OK] ALL {total}/{total} KEYS CONFIGURED!  ", GREEN)
    elif pct >= 70:
        msg = c(f"  [~] {score} keys configured ({pct:.0f}%) - almost there!  ", YELLOW)
    elif pct >= 30:
        msg = c(f"  [/] {score} keys configured ({pct:.0f}%) - progress!  ", YELLOW)
    else:
        msg = c(f"  [!] {score} keys configured ({pct:.0f}%) - time to set up!  ", RED)
    print(f"\n  {c(_DASH, DIM)}")
    print(f"  {b(msg)}")
    print(f"  {c(_DASH, DIM)}")


def run_check(verify: bool = False, json_output: bool = False) -> dict:
    """Main check routine. Returns a dict with all results."""
    env = load_env_file()
    json_config = load_api_keys_json()

    results = []
    for var_name, source, required, verify_type, hint in KEYS:
        value = get_key_value(var_name, env, json_config)
        configured = bool(value)
        masked = value[:6] + "..." + value[-4:] if len(value) > 12 else "set" if configured else ""

        entry: dict = {
            "key": var_name,
            "source": source,
            "required": required,
            "configured": configured,
            "hint": hint,
        }
        if configured and masked:
            entry["masked"] = masked

        if configured and verify and verify_type and HAS_REQUESTS:
            if verify_type == "gemini":
                ok, msg = verify_gemini(value)
                entry["verified"] = ok
                entry["verify_message"] = msg
            elif verify_type == "openai":
                ok, msg = verify_openai(value)
                entry["verified"] = ok
                entry["verify_message"] = msg
            elif verify_type == "telegram":
                ok, msg = verify_telegram(value)
                entry["verified"] = ok
                entry["verify_message"] = msg

        results.append(entry)

    # Ollama check (uses parsed .env host if present)
    ollama_host = env.get("OLLAMA_HOST", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ollama_ok, ollama_msg = (verify_ollama(ollama_host) if HAS_REQUESTS
                             else (False, "requests not installed"))
    results.append({
        "key": "OLLAMA_HOST",
        "source": ".env or http://127.0.0.1:11434 (default)",
        "required": False,
        "configured": ollama_ok,
        "hint": "Download from https://ollama.com",
        "verify_message": ollama_msg,
    })

    configured_count = sum(1 for r in results if r.get("configured"))
    total = len(results)

    output = {
        "timestamp": datetime.now().isoformat(),
        "project": "BARQ",
        "config_files": {
            "env_file": str(ENV_PATH),
            "env_exists": ENV_PATH.exists(),
            "api_keys_json": str(API_KEYS_JSON_PATH),
            "api_keys_json_exists": API_KEYS_JSON_PATH.exists(),
        },
        "summary": {
            "configured": configured_count,
            "total": total,
            "percentage": round(configured_count / total * 100, 1) if total else 0,
        },
        "keys": results,
    }

    if json_output:
        return output

    # ── Pretty print (fully ASCII-safe) ────────────────────────────────
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"")
    print(f"  {b('B.A.R.Q Setup Checker')}")
    print(f"  {c(ts, DIM)}")
    print(f"  {c(f'Project: {PROJECT_ROOT.name}', DIM)}")
    print(f"  {c(f'Python: {sys.version.split()[0]}', DIM)}")

    # Config files
    print_header("Config Files")
    for fpath, label in [(ENV_PATH, ".env"),
                         (API_KEYS_JSON_PATH, "config/api_keys.json")]:
        ok_text = "[*] EXISTS" if fpath.exists() else "[x] NOT FOUND"
        ok_color = GREEN if fpath.exists() else RED
        print(f"    {label:25s} {c(ok_text, ok_color)}")

    # Key status table
    print_header("API Keys & Credentials")

    for r in results:
        key = r["key"]
        is_cfg = r.get("configured", False)
        masked = r.get("masked", "")
        verified = r.get("verified")
        vmsg = r.get("verify_message", "")

        icon = c("[ok]", GREEN) if is_cfg else c("[--]", YELLOW)
        label_color = GREEN if is_cfg else RED
        status_label = "CONFIGURED" if is_cfg else "MISSING"

        if is_cfg:
            print(f"    {icon} {b(key):22s} {c(status_label + ' ' + masked, label_color)}")
        else:
            print(f"    {icon} {b(key):22s} {c(status_label, label_color)}")

        # Hint for missing keys
        if not is_cfg and r.get("hint"):
            hint = r["hint"]
            print(f"    {'':26s}{c(f'-> {hint}', DIM)}")

        # Verify result
        if verified is not None:
            v_icon = c("[ok]", GREEN) if verified else c("[fail]", RED)
            print(f"    {'':26s}{v_icon} {vmsg}")

    # Check requests library
    if verify and not HAS_REQUESTS:
        notif = c("[!] install requests to enable live verification:", YELLOW)
        hint = c("   pip install requests", DIM)
        print(f"\n    {notif}")
        print(f"    {hint}")

    # Summary
    print_header("Summary")
    print_footer(configured_count, total)

    # Next steps
    missing = [r for r in results if not r.get("configured")]
    if missing:
        print(f"\n  {b('Next steps to configure:')}")
        steps = []
        if any(r["key"] == "GEMINI_API_KEY" for r in missing):
            steps.append("1) GEMINI_API_KEY  -> https://aistudio.google.com/apikey")
        if any(r["key"] == "OPENAI_API_KEY" for r in missing):
            steps.append("2) OPENAI_API_KEY  -> https://platform.openai.com/api-keys")
        if any(r["key"] == "TELEGRAM_BOT_TOKEN" for r in missing):
            steps.append("3) TELEGRAM_BOT_TOKEN -> https://t.me/BotFather")

        for s in steps:
            print(f"    {c(s, CYAN)}")

        env_missing = [r["key"] for r in missing if r["key"] != "OLLAMA_HOST"]
        if env_missing:
            print(f"\n    {c('Quick setup - add to .env:', DIM)}")
            for k in env_missing[:5]:
                print(f"    {c(f'  {k}=your_key_here', DIM)}")
            if len(env_missing) > 5:
                print(f"    {c(f'  ... and {len(env_missing)-5} more', DIM)}")

    return output


def main():
    verify = "--verify" in sys.argv
    json_output = "--json" in sys.argv

    result = run_check(verify=verify, json_output=json_output)

    if json_output:
        print(json.dumps(result, indent=2))

    # Exit code: 0 if all required keys are present
    required_missing = [
        r for r in result["keys"]
        if r.get("required") and not r.get("configured")
    ]
    sys.exit(1 if required_missing else 0)


if __name__ == "__main__":
    main()
