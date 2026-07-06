"""
Tests for voice command route parsing (POST /voice/command).
Tests the _parse_and_route function indirectly via the process_command endpoint.
Patches the module-level names that routes.py imports BEFORE module load so
the module-level constructors (SpeechProcessor(), BARQResponder(), etc.) use mocks.
"""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def router():
    """Return the voice routes router with heavy dependencies mocked.

    routes.py imports BARQResponder, SpeechProcessor, and ConversationListener
    at module level and instantiates them immediately. We patch the names that
    routes.py accesses (voice.SpeechProcessor, ai.responder.BARQResponder,
    voice.conversation_listener.ConversationListener) BEFORE the route module
    is imported, so the module-level constructors return MagicMocks.
    """
    mock_conversation = MagicMock(
        is_active=False,
        turn_count=0,
        history=[],
        add_user_message=MagicMock(),
        add_assistant_message=MagicMock(),
        start_session=MagicMock(),
    )
    with (
        patch("voice.SpeechProcessor"),
        patch("ai.responder.BARQResponder", return_value=MagicMock(conversation=mock_conversation)),
        patch("voice.conversation_listener.ConversationListener", return_value=MagicMock()),
    ):
        from voice import routes
        return routes.router


# ─── Diagnostics ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_show_diagnostics_exact(client):
    """POST /voice/command with 'show diagnostics' should return action=show_diagnostics."""
    response = await client.post("/command", json={"command": "show diagnostics"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"
    assert data["status"] == "triggered"


@pytest.mark.asyncio
async def test_system_diagnostics(client):
    """'system diagnostics' should trigger show_diagnostics."""
    response = await client.post("/command", json={"command": "system diagnostics"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"


@pytest.mark.asyncio
async def test_system_status(client):
    """'system status' should trigger show_diagnostics."""
    response = await client.post("/command", json={"command": "system status"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"


@pytest.mark.asyncio
async def test_diagnostics_alone(client):
    """Just 'diagnostics' should trigger show_diagnostics."""
    response = await client.post("/command", json={"command": "diagnostics"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"


@pytest.mark.asyncio
async def test_show_system_diagnostics(client):
    """'show system diagnostics' should trigger show_diagnostics."""
    response = await client.post("/command", json={"command": "show system diagnostics"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"


@pytest.mark.asyncio
async def test_diagnostics_case_insensitive(client):
    """Command matching should be case insensitive (all lowered by process_command)."""
    response = await client.post("/command", json={"command": "SHOW DIAGNOSTICS"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"


# ─── Clear/Show Approvals ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_approvals(client):
    """'clear approvals' should trigger clear_approvals."""
    response = await client.post("/command", json={"command": "clear approvals"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "clear_approvals"
    assert data["status"] == "triggered"


@pytest.mark.asyncio
async def test_clear_all_approvals(client):
    """'clear all approvals' should trigger clear_approvals."""
    response = await client.post("/command", json={"command": "clear all approvals"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "clear_approvals"


@pytest.mark.asyncio
async def test_reset_approvals(client):
    """'reset approvals' should NOT match (no 'clear' keyword). Shows why keyword matching matters."""
    response = await client.post("/command", json={"command": "reset approvals"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] != "clear_approvals"


@pytest.mark.asyncio
async def test_show_approvals(client):
    """'show approvals' should navigate to /settings."""
    response = await client.post("/command", json={"command": "show approvals"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "navigate"
    assert data["target"] == "/settings"


@pytest.mark.asyncio
async def test_view_approvals(client):
    """'view approvals' should NOT match 'show' in command (falls through to unknown)."""
    response = await client.post("/command", json={"command": "view approvals"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "unknown"


# ─── Negative / Edge Cases ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnostics_not_confused_with_navigation(client):
    """'go to diagnostics' contains 'diagnostics' so it routes to show_diagnostics
    (the diagnostics keyword check comes before navigation in _parse_and_route)."""
    response = await client.post("/command", json={"command": "go to diagnostics"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"


@pytest.mark.asyncio
async def test_weather_not_confused_with_diagnostics(client):
    """'weather diagnostics' should trigger show_diagnostics (diagnostics keyword wins)."""
    response = await client.post("/command", json={"command": "weather diagnostics"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_diagnostics"


@pytest.mark.asyncio
async def test_unknown_command(client):
    """Unrecognized command should return action=unknown."""
    response = await client.post("/command", json={"command": "do a barrel roll"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "unknown"
    assert "command" in data


# ─── Action Log /action-log/recent ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_action_log_empty(client):
    """GET /action-log/recent should return empty actions list when nothing logged."""
    response = await client.get("/action-log/recent")
    assert response.status_code == 200
    data = response.json()
    assert data == {"actions": []}


@pytest.mark.asyncio
async def test_action_log_single_entry(client):
    """GET /action-log/recent should return a single logged action."""
    from database.connection import db_connection
    await db_connection.insert(
        "INSERT INTO action_log (action, description, severity, metadata) VALUES (?, ?, ?, ?)",
        ("run_command", "echo hello", "info", '{"command": "echo hello", "tier": "safe"}'),
    )

    response = await client.get("/action-log/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data["actions"]) == 1
    entry = data["actions"][0]
    assert entry["action"] == "run_command"
    assert entry["description"] == "echo hello"
    assert entry["severity"] == "info"
    assert entry["metadata"] == {"command": "echo hello", "tier": "safe"}
    assert "id" in entry
    assert "created_at" in entry


@pytest.mark.asyncio
async def test_action_log_multiple_entries_order(client):
    """GET /action-log/recent should return entries newest-first."""
    from database.connection import db_connection
    # Insert older entry first
    await db_connection.insert(
        "INSERT INTO action_log (action, description, severity, created_at) VALUES (?, ?, ?, ?)",
        ("first_action", "I was created first", "info", "2024-01-01 00:00:00"),
    )
    await db_connection.insert(
        "INSERT INTO action_log (action, description, severity, created_at) VALUES (?, ?, ?, ?)",
        ("second_action", "I was created second", "warning", "2024-06-15 12:00:00"),
    )
    await db_connection.insert(
        "INSERT INTO action_log (action, description, severity, created_at) VALUES (?, ?, ?, ?)",
        ("third_action", "I am the newest", "danger", "2024-12-31 23:59:59"),
    )

    response = await client.get("/action-log/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data["actions"]) == 3
    assert data["actions"][0]["action"] == "third_action"
    assert data["actions"][1]["action"] == "second_action"
    assert data["actions"][2]["action"] == "first_action"


@pytest.mark.asyncio
async def test_action_log_severity_preserved(client):
    """GET /action-log/recent should preserve severity values for all levels."""
    from database.connection import db_connection
    import json
    for sev in ("info", "warning", "danger"):
        await db_connection.insert(
            "INSERT INTO action_log (action, description, severity, metadata) VALUES (?, ?, ?, ?)",
            ("test_action", f"Severity: {sev}", sev, json.dumps({"severity": sev})),
        )

    response = await client.get("/action-log/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data["actions"]) == 3
    severities = {e["severity"] for e in data["actions"]}
    assert severities == {"info", "warning", "danger"}


@pytest.mark.asyncio
async def test_action_log_default_limit(client):
    """GET /action-log/recent without limit should default to 10."""
    from database.connection import db_connection
    for i in range(15):
        await db_connection.insert(
            "INSERT INTO action_log (action, description) VALUES (?, ?)",
            (f"action_{i}", f"Description {i}"),
        )

    response = await client.get("/action-log/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data["actions"]) == 10


@pytest.mark.asyncio
async def test_action_log_custom_limit(client):
    """GET /action-log/recent with limit=3 should return exactly 3 entries."""
    from database.connection import db_connection
    for i in range(10):
        await db_connection.insert(
            "INSERT INTO action_log (action, description) VALUES (?, ?)",
            (f"action_{i}", f"Description {i}"),
        )

    response = await client.get("/action-log/recent?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data["actions"]) == 3


@pytest.mark.asyncio
async def test_action_log_metadata_parsing(client):
    """GET /action-log/recent should parse stored metadata JSON into a dict."""
    from database.connection import db_connection
    import json
    metadata = {"command": "tail -f /var/log/syslog", "tier": "safe", "duration_ms": 1234}
    await db_connection.insert(
        "INSERT INTO action_log (action, description, metadata) VALUES (?, ?, ?)",
        ("run_command", "tail -f /var/log/syslog", json.dumps(metadata)),
    )

    response = await client.get("/action-log/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data["actions"]) == 1
    assert data["actions"][0]["metadata"] == metadata


# ─── Weather ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weather_default(client):
    """'weather' alone should return get_weather with default city London."""
    response = await client.post("/command", json={"command": "weather"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_weather"
    assert data["city"] == "London"


@pytest.mark.asyncio
async def test_weather_whats_the_weather(client):
    """'what's the weather' should return get_weather."""
    response = await client.post("/command", json={"command": "what's the weather"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_weather"


@pytest.mark.asyncio
async def test_weather_in_city(client):
    """'weather in Paris' should return get_weather with city paris (lowercased)."""
    response = await client.post("/command", json={"command": "weather in Paris"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_weather"
    assert data["city"] == "paris"


@pytest.mark.asyncio
async def test_weather_for_tokyo(client):
    """'weather for Tokyo' should return get_weather with city tokyo (lowercased)."""
    response = await client.post("/command", json={"command": "weather for Tokyo"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_weather"
    assert data["city"] == "tokyo"


# ─── Stocks ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stock_default(client):
    """'stock' alone should return get_stock with default ticker AAPL."""
    response = await client.post("/command", json={"command": "stock"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_stock"
    assert data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_stock_with_ticker(client):
    """'stock AAPL' should return get_stock with ticker aapl (lowercased)."""
    response = await client.post("/command", json={"command": "stock AAPL"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_stock"
    assert data["ticker"] == "aapl"


@pytest.mark.asyncio
async def test_price_of_ticker(client):
    """'price of GOOGL' should return get_stock with ticker googl (lowercased)."""
    response = await client.post("/command", json={"command": "price of GOOGL"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_stock"
    assert data["ticker"] == "googl"


# ─── Web & Media ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_for_query(client):
    """'search for cats' should return web_search with query 'cats'."""
    response = await client.post("/command", json={"command": "search for cats"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "web_search"
    assert data["query"] == "cats"


@pytest.mark.asyncio
async def test_google_query(client):
    """'google python tutorials' should return web_search."""
    response = await client.post("/command", json={"command": "google python tutorials"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "web_search"
    assert data["query"] == "python tutorials"


@pytest.mark.asyncio
async def test_open_domain_caught_by_app_launcher(client):
    """'open example.com' is caught by the app launcher regex before the URL check runs.
    The app launcher title()-izes the target to 'Example.Com'."""
    response = await client.post("/command", json={"command": "open example.com"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "launch_app"
    assert "Example.Com" in data["target"]


@pytest.mark.asyncio
async def test_play_spotify(client):
    """'play shape of you on spotify' should return spotify_play."""
    response = await client.post("/command", json={"command": "play shape of you on spotify"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "spotify_play"
    assert "query" in data


@pytest.mark.asyncio
async def test_pause_music(client):
    """'pause music' should return spotify_pause."""
    response = await client.post("/command", json={"command": "pause music"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "spotify_pause"
    assert data["status"] == "triggered"


@pytest.mark.asyncio
async def test_map_of_place(client):
    """'map of Tokyo' should return show_map with place tokyo (lowercased)."""
    response = await client.post("/command", json={"command": "map of Tokyo"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_map"
    assert data["place"] == "tokyo"


@pytest.mark.asyncio
async def test_directions_to_place(client):
    """'directions to New York' should return get_directions with destination lowercased."""
    response = await client.post("/command", json={"command": "directions to New York"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "get_directions"
    assert data["destination"] == "new york"


@pytest.mark.asyncio
async def test_generate_image(client):
    """'generate image of a cat' should return generate_image."""
    response = await client.post("/command", json={"command": "generate image of a cat"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "generate_image"
    assert "prompt" in data


@pytest.mark.asyncio
async def test_create_image(client):
    """'create image of a dog' should return generate_image."""
    response = await client.post("/command", json={"command": "create image of a dog"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "generate_image"
    assert "prompt" in data


# ─── System Control: Window Management ───────────────────────────────────────


@pytest.mark.asyncio
async def test_maximize_window(client):
    """'maximize window' should return window_control maximize."""
    response = await client.post("/command", json={"command": "maximize window"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "maximize"


@pytest.mark.asyncio
async def test_maximize_barq(client):
    """'maximize barq' should return window_control maximize."""
    response = await client.post("/command", json={"command": "maximize barq"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "maximize"


@pytest.mark.asyncio
async def test_maximize_alone_does_not_match(client):
    """'maximize' alone should NOT match (requires 'window' or 'barq')."""
    response = await client.post("/command", json={"command": "maximize"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] != "window_control"


@pytest.mark.asyncio
async def test_minimize(client):
    """'minimize' should return window_control minimize."""
    response = await client.post("/command", json={"command": "minimize"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "minimize"


@pytest.mark.asyncio
async def test_minimize_all(client):
    """'minimize all windows' should return show_desktop."""
    response = await client.post("/command", json={"command": "minimize all windows"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "show_desktop"


@pytest.mark.asyncio
async def test_snap_left(client):
    """'snap left' should return window_control snap_left."""
    response = await client.post("/command", json={"command": "snap left"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "snap_left"


@pytest.mark.asyncio
async def test_snap_right(client):
    """'snap right' should return window_control snap_right."""
    response = await client.post("/command", json={"command": "snap right"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "snap_right"


@pytest.mark.asyncio
async def test_move_window_left(client):
    """'move window left' should return window_control snap_left."""
    response = await client.post("/command", json={"command": "move window left"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "snap_left"


@pytest.mark.asyncio
async def test_move_window_right(client):
    """'move window right' should return window_control snap_right."""
    response = await client.post("/command", json={"command": "move window right"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "snap_right"


@pytest.mark.asyncio
async def test_resize(client):
    """'resize 800x600' should return window_control resize with dimensions."""
    response = await client.post("/command", json={"command": "resize 800x600"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "window_control"
    assert data["target"] == "resize"
    assert data["width"] == 800
    assert data["height"] == 600


# ─── System Control: App Launcher ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_chrome(client):
    """'open chrome' should return launch_app with target Google Chrome."""
    response = await client.post("/command", json={"command": "open chrome"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "launch_app"
    assert data["target"] == "Google Chrome"


@pytest.mark.asyncio
async def test_open_spotify(client):
    """'open spotify' should return launch_app with target Spotify."""
    response = await client.post("/command", json={"command": "open spotify"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "launch_app"
    assert data["target"] == "Spotify"


@pytest.mark.asyncio
async def test_launch_vs_code(client):
    """'launch vs code' should return launch_app with target Visual Studio Code."""
    response = await client.post("/command", json={"command": "launch vs code"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "launch_app"
    assert data["target"] == "Visual Studio Code"


@pytest.mark.asyncio
async def test_start_terminal(client):
    """'start terminal' should return launch_app with target Terminal."""
    response = await client.post("/command", json={"command": "start terminal"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "launch_app"
    assert data["target"] == "Terminal"


@pytest.mark.asyncio
async def test_close_chrome(client):
    """'close chrome' should return close_app with target Chrome."""
    response = await client.post("/command", json={"command": "close chrome"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "close_app"
    assert "Chrome" in data["target"]


@pytest.mark.asyncio
async def test_kill_terminal(client):
    """'kill terminal' should return close_app with target Terminal."""
    response = await client.post("/command", json={"command": "kill terminal"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "close_app"
    assert "Terminal" in data["target"]


@pytest.mark.parametrize("command,expected", [
    ("open firefox", "Firefox"),
    ("open slack", "Slack"),
    ("open discord", "Discord"),
    ("open notion", "Notion"),
])
@pytest.mark.asyncio
async def test_launch_app_map(client, command, expected):
    """Common app names from the app_map should be resolved correctly."""
    response = await client.post("/command", json={"command": command})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "launch_app"
    assert data["target"] == expected


# ─── Desktop Overlay Voice Commands ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_overlay_show(client):
    """'show overlay' should return overlay_show."""
    response = await client.post("/command", json={"command": "show overlay"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "overlay_show"
    assert data["status"] == "triggered"


@pytest.mark.asyncio
async def test_overlay_hide(client):
    """'hide overlay' should return overlay_hide."""
    response = await client.post("/command", json={"command": "hide overlay"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "overlay_hide"
    assert data["status"] == "triggered"


@pytest.mark.asyncio
async def test_overlay_toggle(client):
    """'toggle overlay' should return overlay_toggle."""
    response = await client.post("/command", json={"command": "toggle overlay"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "overlay_toggle"
    assert data["status"] == "triggered"


@pytest.mark.asyncio
async def test_overlay_alone(client):
    """'overlay' alone (no show/hide/toggle) should default to overlay_toggle."""
    response = await client.post("/command", json={"command": "overlay"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "overlay_toggle"


@pytest.mark.asyncio
async def test_overlay_show_me(client):
    """'show me the overlay' should still match overlay_show (permissive keyword)."""
    response = await client.post("/command", json={"command": "show me the overlay"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "overlay_show"


@pytest.mark.asyncio
async def test_overlay_not_confused_with_apps(client):
    """'overlay' keyword should not be caught by app launcher (no open/launch/start)."""
    response = await client.post("/command", json={"command": "show overlay"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "overlay_show"
    assert data["action"] != "launch_app"


@pytest.mark.asyncio
async def test_overlay_hide_now(client):
    """'overlay hide now' should still match (both keywords present)."""
    response = await client.post("/command", json={"command": "overlay hide now"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "overlay_hide"
