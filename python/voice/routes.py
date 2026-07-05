"""
FastAPI routes for voice control.
Handles wake word detection, speech transcription, TTS,
multi-turn conversation state, sensitivity control, and command history.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from config import get_settings
from ai.responder import BARQResponder
from . import WakeWordDetector, SpeechProcessor, play_command_accepted_sound, set_sound_enabled, get_sound_settings
from .conversation_listener import ConversationListener
from database import analytics_dao, settings_dao

router = APIRouter()

# Singleton instances
wake_word_detector: WakeWordDetector | None = None
speech_processor = SpeechProcessor()
responder = BARQResponder()
conversation_listener = ConversationListener(stt=speech_processor, responder=responder)

# Auto-start flag — set to True after first start
_auto_started = False


def get_wake_word_detector() -> WakeWordDetector:
    """Get or create the wake word detector singleton."""
    global wake_word_detector
    if wake_word_detector is None:
        wake_word_detector = WakeWordDetector(
            on_wake_word=_on_wake_word_callback,
            on_conversation_trigger=_on_conversation_trigger,
        )
    return wake_word_detector


def _on_wake_word_callback():
    """Callback fired when wake word is detected by the background listener."""
    print("[Voice] Wake word detected — Electron wake signal sent")


def _on_conversation_trigger():
    """Callback fired from the wake word detector to start the conversation loop.
    This runs in a background thread, so we use asyncio.run_coroutine_threadsafe
    to fire the async conversation loop on the event loop.
    Only triggers if hands-free conversation mode is enabled."""
    global _hands_free_mode
    if not _hands_free_mode:
        print("[Voice] Hands-free mode disabled — skipping conversation trigger")
        return
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                conversation_listener.start_conversation(), loop
            )
            print("[Voice] Hands-free conversation mode triggered from wake word")
    except RuntimeError:
        print("[Voice] No event loop available for conversation trigger")


async def load_sound_settings():
    """Load saved sound preferences and sensitivity from the database on startup.
    This ensures user's mute preferences and sensitivity persist across app restarts."""
    global _sensitivity

    # Load sound preferences
    wake_val = await settings_dao.get_setting("wake_sound_enabled")
    command_val = await settings_dao.get_setting("command_sound_enabled")

    if wake_val is not None:
        set_sound_enabled("wake", wake_val.lower() == "true")
    if command_val is not None:
        set_sound_enabled("command", command_val.lower() == "true")

    current = get_sound_settings()
    print(f"[Voice] Sound settings loaded from DB: {current}")

    # Load saved sensitivity level from DB
    sens_val = await settings_dao.get_setting("wake_word_sensitivity")
    if sens_val is not None and sens_val.lower() in ("low", "medium", "high"):
        _sensitivity = sens_val.lower()
        # Apply to existing detector (if it was already created for mic polling etc.)
        if wake_word_detector is not None:
            wake_word_detector.set_sensitivity(_sensitivity)
        print(f"[Voice] Sensitivity loaded from DB: {_sensitivity}")
    else:
        print(f"[Voice] No saved sensitivity in DB, using default: {_sensitivity}")

    # Load hands-free conversation mode setting
    hf_val = await settings_dao.get_setting("hands_free_mode")
    if hf_val is not None:
        global _hands_free_mode
        _hands_free_mode = hf_val.lower() == "true"
        print(f"[Voice] Hands-free mode loaded from DB: {_hands_free_mode}")

# ─── Multi-turn conversation state ─────────────────────────────────────────

_tts_voice: str = "en-US-JennyNeural"
_sensitivity: str = "medium"
_language: str = "en"  # "en" or "hi"
_hands_free_mode: bool = True  # Alexa/Gemini-style hands-free conversation mode
# Conversation manager is now managed by the shared responder instance
# _responder and conversation_listener are the canonical singletons above


class CommandRequest(BaseModel):
    command: str
    confidence: float = 0.0


class ChatRequest(BaseModel):
    message: str
    language: str = "en"


class SensitivityRequest(BaseModel):
    level: str  # low, medium, high


class LanguageRequest(BaseModel):
    language: str  # "en" or "hi"


class TTSVoiceRequest(BaseModel):
    voice: str


class SoundSettingsRequest(BaseModel):
    wake_sound_enabled: Optional[bool] = None
    command_sound_enabled: Optional[bool] = None


class SoundPreviewRequest(BaseModel):
    profile: str  # "wake" or "command_accepted"


class WakeWordRequest(BaseModel):
    wake_word: str  # new wake word phrase


class ConversationModeRequest(BaseModel):
    enabled: bool  # enable or disable hands-free conversation mode


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/sound-preview")
async def preview_sound(request: SoundPreviewRequest):
    """Play a sound profile through speakers for preview. Used by the Sounds tab.
    Bypasses the mute gate so users can always hear the preview."""
    if request.profile not in ("wake", "command_accepted"):
        raise HTTPException(status_code=400, detail="Invalid profile. Use: wake, command_accepted")

    from .wake_word import _generate_chime_wav, _play_wav
    _play_wav(_generate_chime_wav(request.profile), f"{request.profile} preview")

    return {"status": "played", "profile": request.profile}


@router.get("/sound-settings")
async def get_sound_settings_endpoint():
    """Get current sound preference state (wake chime, command accepted ping)."""
    return get_sound_settings()


@router.post("/sound-settings")
async def set_sound_settings_endpoint(request: SoundSettingsRequest):
    """Update sound preferences and persist to database."""
    changes = []
    if request.wake_sound_enabled is not None:
        set_sound_enabled("wake", request.wake_sound_enabled)
        await settings_dao.set_setting(
            "wake_sound_enabled", "true" if request.wake_sound_enabled else "false", "voice"
        )
        changes.append(f"wake={request.wake_sound_enabled}")

    if request.command_sound_enabled is not None:
        set_sound_enabled("command", request.command_sound_enabled)
        await settings_dao.set_setting(
            "command_sound_enabled", "true" if request.command_sound_enabled else "false", "voice"
        )
        changes.append(f"command={request.command_sound_enabled}")

    await analytics_dao.log_activity("voice", "sound_settings", ", ".join(changes))
    return get_sound_settings()


@router.post("/start")
async def start_listening():
    """Start wake word detection using the always-on singleton."""
    global _auto_started
    # Ensure sound preferences are loaded before detection starts
    await load_sound_settings()
    detector = get_wake_word_detector()
    # Apply the loaded sensitivity (from load_sound_settings) to the detector
    detector.set_sensitivity(_sensitivity)
    detector.start()
    _auto_started = True
    await analytics_dao.log_activity("voice", "start_listening", "Wake word detection started")
    return {"status": "listening", "wake_word": get_settings().wake_word}


@router.post("/stop")
async def stop_listening():
    """Stop wake word detection."""
    global wake_word_detector

    if wake_word_detector:
        wake_word_detector.stop()

    await analytics_dao.log_activity("voice", "stop_listening", "Wake word detection stopped")
    return {"status": "stopped"}


@router.post("/sensitivity")
async def set_sensitivity(request: SensitivityRequest):
    """Set wake word detection sensitivity and apply to running detector."""
    global _sensitivity
    if request.level not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="Invalid sensitivity level. Use: low, medium, high")

    _sensitivity = request.level

    # Apply to running detector (live update — no restart needed)
    detector = get_wake_word_detector()
    detector.set_sensitivity(request.level)

    await settings_dao.set_setting("wake_word_sensitivity", request.level, "voice")
    await analytics_dao.log_activity("voice", "sensitivity", f"Sensitivity set to {request.level}")
    return {"status": "set", "level": request.level}


@router.get("/sensitivity")
async def get_sensitivity():
    """Get current wake word detection sensitivity."""
    return {"level": _sensitivity}


@router.get("/language")
async def get_language():
    """Get the current active language for wake word detection."""
    lang = _language
    if wake_word_detector is not None:
        lang = wake_word_detector.language
    return {"language": lang, "languages_available": ["en", "hi"]}


@router.post("/language")
async def set_language(request: LanguageRequest):
    """Switch wake word detection language between English and Hindi."""
    global _language
    if request.language not in ("en", "hi"):
        raise HTTPException(status_code=400, detail="Language must be 'en' or 'hi'")

    _language = request.language
    detector = get_wake_word_detector()
    success = detector.set_language(request.language)

    if not success:
        raise HTTPException(status_code=400, detail=f"Hindi model not available. Download vosk-model-small-hi-0.22")

    await settings_dao.set_setting("voice_language", request.language, "voice")
    await analytics_dao.log_activity("voice", "language", f"Switched to {request.language}")
    return {"status": "set", "language": request.language}


@router.post("/chat")
async def chat(request: ChatRequest):
    """Send a message to BARQ's conversation AI and get a text+audio response.
    Uses ConversationManager for context and Ollama for LLM responses."""
    try:
        result = await responder.respond(request.message)
        await analytics_dao.log_activity("voice", "chat", f"Chat: {request.message[:50]}...")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/text")
async def chat_text_only(request: ChatRequest):
    """Quick text-only chat (no audio generation)."""
    try:
        text = await responder.respond_text_only(request.message)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-tts-voice")
async def set_tts_voice(request: TTSVoiceRequest):
    """Set the TTS voice for speech synthesis."""
    global _tts_voice
    _tts_voice = request.voice
    speech_processor.tts_voice = request.voice
    await settings_dao.set_setting("tts_voice", request.voice, "voice")
    await analytics_dao.log_activity("voice", "tts_voice", f"TTS voice set to {request.voice}")
    return {"status": "set", "voice": request.voice}


@router.get("/tts-voices")
async def list_tts_voices():
    """List available TTS voices."""
    voices = [
        {"id": "en-US-JennyNeural", "name": "Jenny", "gender": "Female", "locale": "en-US"},
        {"id": "en-US-GuyNeural", "name": "Guy", "gender": "Male", "locale": "en-US"},
        {"id": "en-GB-SoniaNeural", "name": "Sonia", "gender": "Female", "locale": "en-GB"},
        {"id": "en-GB-RyanNeural", "name": "Ryan", "gender": "Male", "locale": "en-GB"},
        {"id": "en-AU-NatashaNeural", "name": "Natasha", "gender": "Female", "locale": "en-AU"},
        {"id": "en-IN-NeerjaNeural", "name": "Neerja", "gender": "Female", "locale": "en-IN"},
    ]
    return {"voices": voices, "current": _tts_voice}


@router.get("/history")
async def get_command_history(limit: int = Query(default=50, ge=1, le=200)):
    """Get voice command history."""
    try:
        commands = await settings_dao.get_recent_commands(limit=limit)
        return {
            "commands": [
                {
                    "id": c.get("id"),
                    "transcript": c.get("transcript", ""),
                    "action": c.get("action", ""),
                    "success": c.get("success", False),
                    "confidence": c.get("confidence", 0.0),
                    "created_at": c.get("created_at", ""),
                }
                for c in commands
            ],
            "total": len(commands),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/start")
async def start_conversation(topic: Optional[str] = None):
    """Start a multi-turn conversation session."""
    session_id = responder.conversation.start_session(topic)
    await analytics_dao.log_activity("voice", "conversation_start", f"Conversation started: {topic or 'general'}")
    return {"status": "started", "session_id": session_id}


@router.post("/conversation/end")
async def end_conversation():
    """End the current conversation session."""
    if not responder.conversation.is_active:
        return {"status": "no_active_session"}
    turns = responder.conversation.turn_count
    responder.conversation.end_session()
    await analytics_dao.log_activity("voice", "conversation_end", f"Conversation ended. Turns: {turns}")
    return {"status": "ended", "turns": turns}


@router.get("/conversation/context")
async def get_conversation_context():
    """Get the current conversation context."""
    if not responder.conversation.is_active:
        return {"active": False}
    return {
        "active": True,
        "session_id": responder.conversation.session_id,
        "turns": responder.conversation.turn_count,
        "recent_history": responder.conversation.get_recent_history(5),
    }


@router.post("/command")
async def process_command(request: CommandRequest):
    """
    Process a voice command text and route to the appropriate BARQ module.
    Supports multi-turn conversation context for follow-up commands.
    """
    command = request.command.lower().strip()

    # ─── Multi-turn conversation handling ──────────────────────────────
    cm = responder.conversation

    # Check if this is a follow-up in an active conversation
    is_follow_up = cm.is_active and cm.turn_count > 0

    # Add to conversation manager
    cm.add_user_message(command)

    # Log to database
    await settings_dao.log_command({
        "transcript": command,
        "confidence": request.confidence,
        "action": "processed",
        "processed": True,
    })

    # Determine last intent from history
    last_intent = None
    if is_follow_up and cm.history:
        import json as _json
        for msg in reversed(cm.history):
            if msg["role"] == "assistant":
                try:
                    parsed = _json.loads(msg["content"])
                    if isinstance(parsed, dict):
                        last_intent = parsed.get("action")
                        break
                except (_json.JSONDecodeError, TypeError):
                    continue

    result = await _parse_and_route(command, is_follow_up, last_intent)

    # Play command accepted sound + update conversation manager
    if result.get("action") != "unknown":
        play_command_accepted_sound()
        if not cm.is_active:
            cm.start_session()

    # Store the result as a JSON string so follow-up detection can parse it back
    import json as _json
    cm.add_assistant_message(_json.dumps(result))

    return result


async def _parse_and_route(command: str, is_follow_up: bool = False, last_intent: Optional[str] = None) -> dict[str, Any]:
    """
    Parse a voice command and determine the appropriate action.
    Supports follow-up context resolution for multi-turn conversations.
    """

    # ─── Conversation follow-up handling ────────────────────────────

    if is_follow_up and last_intent:
        # Handle follow-ups like "that one", "this", "the second"
        if command in ("that one", "this", "yes", "yeah", "confirm", "do it"):
            # _conversation_context was never defined; return a simple confirmation
            return {"action": last_intent, "status": "confirmed", "follow_up": True}

        if command in ("no", "nope", "cancel", "stop", "never mind"):
            return {"action": "cancel", "status": "cancelled", "follow_up": True}

        # Handle numbered selections
        selection_match = re.search(r"(?:the |number )?(first|second|third|fourth|fifth|\d+)", command)
        if selection_match:
            selection = selection_match.group(1)
            idx_map = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4}
            try:
                idx = idx_map.get(selection, int(selection) - 1) if selection.isdigit() else idx_map.get(selection, 0)
            except (ValueError, KeyError):
                idx = 0
            return {
                "action": f"{last_intent}_select",
                "selection_index": idx,
                "status": "selected",
                "follow_up": True,
            }

    # ─── System Commands ────────────────────────────────────────────

    if command in ("stop listening", "stop voice", "shut up", "silence"):
        return {"action": "voice_stop", "endpoint": "POST /voice/stop", "status": "triggered"}

    if command in ("start listening", "wake up", "hey barq"):
        return {"action": "voice_start", "endpoint": "POST /voice/start", "status": "triggered"}

    # ─── Conversation control ───────────────────────────────────────

    if command in ("start conversation", "let's talk", "begin session"):
        return {"action": "start_conversation", "status": "triggered"}

    if command in ("end conversation", "stop conversation", "that's all", "we're done"):
        return {"action": "end_conversation", "status": "triggered"}

    # ─── System Control Commands ────────────────────────────────────

    # Window management
    if "maximize" in command and ("window" in command or "barq" in command):
        return {"action": "window_control", "target": "maximize", "endpoint": "POST /system/window/control", "status": "triggered"}

    if "minimize" in command:
        if "all" in command:
            return {"action": "show_desktop", "status": "triggered"}
        return {"action": "window_control", "target": "minimize", "endpoint": "POST /system/window/control", "status": "triggered"}

    if "snap" in command or ("move" in command and "window" in command):
        if "left" in command:
            return {"action": "window_control", "target": "snap_left", "endpoint": "POST /system/window/control", "status": "triggered"}
        if "right" in command:
            return {"action": "window_control", "target": "snap_right", "endpoint": "POST /system/window/control", "status": "triggered"}

    if "resize" in command:
        size_match = re.search(r"(\d+)\s*x\s*(\d+)", command)
        if size_match:
            return {"action": "window_control", "target": "resize", "width": int(size_match.group(1)), "height": int(size_match.group(2)), "status": "parsed"}

    # App launcher: "open spotify", "launch chrome", "start terminal"
    app_match = re.search(r"(?:open|launch|start)\s+(.+)$", command)
    if app_match:
        app_name = app_match.group(1).strip().title()
        # Map common names
        app_map = {
            "vs code": "Visual Studio Code", "vscode": "Visual Studio Code",
            "code": "Visual Studio Code", "terminal": "Terminal",
            "spotify": "Spotify", "chrome": "Google Chrome",
            "browser": "Google Chrome", "firefox": "Firefox",
            "slack": "Slack", "discord": "Discord",
            "notion": "Notion", "obsidian": "Obsidian",
        }
        resolved_app = app_map.get(app_name.lower(), app_name)
        return {"action": "launch_app", "target": resolved_app, "endpoint": "POST /system/launch-app", "status": "parsed"}

    # Close app: "close chrome", "kill terminal"
    close_match = re.search(r"(?:close|kill|stop)\s+(.+)$", command)
    if close_match:
        return {"action": "close_app", "target": close_match.group(1).strip().title(), "endpoint": "POST /system/close-app", "status": "parsed"}

    # ─── File Commands ──────────────────────────────────────────────

    file_op_match = re.search(r"(?:create|make)\s+(?:folder|directory)\s+(.+)$", command)
    if file_op_match:
        return {"action": "create_folder", "target": file_op_match.group(1).strip(), "endpoint": "POST /system/file/create-folder", "status": "parsed"}

    read_match = re.search(r"(?:read|open|show)\s+(?:file\s+)?(.+)$", command)
    if read_match and "file" in command:
        return {"action": "read_file", "target": read_match.group(1).strip(), "endpoint": "POST /system/file/read", "status": "parsed"}

    if "sort" in command and ("folder" in command or "download" in command or "directory" in command):
        sort_match = re.search(r"sort\s+(?:my\s+)?(.+?)(?:\s+by\s+(type|date|size|name))?$", command)
        directory = sort_match.group(1) if sort_match else "downloads"
        sort_by = sort_match.group(2) if sort_match and sort_match.group(2) else "type"
        return {"action": "sort_files", "target": directory, "sort_by": sort_by, "endpoint": "POST /system/file/sort", "status": "parsed"}

    if "find" in command and "file" in command:
        search_match = re.search(r"find\s+(?:files?\s+)?(?:about\s+)?(.+)$", command)
        query = search_match.group(1) if search_match else command
        return {"action": "search_files", "query": query, "endpoint": "POST /system/file/search", "status": "parsed"}

    # ─── Developer Commands ─────────────────────────────────────────

    if "run" in command or "execute" in command:
        cmd_match = re.search(r"(?:run|execute)\s+(.+)$", command)
        if cmd_match and "scan" not in command and "match" not in command:
            return {"action": "run_command", "command": cmd_match.group(1), "endpoint": "POST /system/terminal/run", "status": "parsed"}

    if "git" in command:
        return {"action": "git_command", "command": command, "status": "parsed"}

    if "deploy" in command:
        return {"action": "deploy", "command": command, "status": "parsed"}

    tunnel_match = re.search(r"(?:expose|tunnel)\s+port\s+(\d+)", command)
    if tunnel_match:
        return {"action": "expose_port", "port": int(tunnel_match.group(1)), "endpoint": "POST /system/tunnel/expose", "status": "parsed"}

    # ─── Desktop / Wallpaper Commands ───────────────────────────────

    if "wallpaper" in command or "background" in command:
        if "change" in command or "set" in command:
            desc_match = re.search(r"(?:to|as|of)\s+(.+)$", command)
            description = desc_match.group(1) if desc_match else command.replace("change wallpaper", "").replace("set wallpaper", "").replace("set background", "").strip()
            return {"action": "set_wallpaper", "description": description, "endpoint": "POST /desktop/wallpaper/set", "status": "parsed"}

    if "screenshot" in command or "capture screen" in command:
        return {"action": "screenshot", "endpoint": "POST /desktop/ocr/capture", "status": "triggered"}

    if "extract text" in command or "ocr" in command:
        return {"action": "ocr", "endpoint": "POST /desktop/ocr/capture", "status": "triggered"}

    # ─── Workflow Commands ──────────────────────────────────────────

    if "activate" in command and "mode" in command:
        mode_match = re.search(r"activate\s+(.+?)\s+mode", command)
        mode = mode_match.group(1) if mode_match else command.replace("activate", "").replace("mode", "").strip()
        return {"action": "activate_protocol", "target": f"{mode}_mode", "endpoint": "POST /desktop/protocols/activate", "status": "parsed"}

    # ─── Web & Media Commands ───────────────────────────────────────

    if "search for" in command or "google" in command:
        search_query = command.replace("search for", "").replace("google", "").strip()
        return {"action": "web_search", "query": search_query, "endpoint": "POST /web/browse/search", "status": "parsed"}

    if "open" in command and ("http" in command or "www" in command or ".com" in command or ".org" in command):
        return {"action": "open_url", "target": command.split()[-1].strip(), "endpoint": "POST /web/browse", "status": "parsed"}

    if "play" in command and "spotify" in command:
        song_match = re.search(r"play\s+(.+?)(?:\s+on\s+spotify)?$", command)
        return {"action": "spotify_play", "query": song_match.group(1).strip() if song_match else "", "status": "parsed"}

    if "pause" in command and "music" in command:
        return {"action": "spotify_pause", "status": "triggered"}

    # Weather
    weather_match = re.search(r"(?:what('s| is) the )?weather(?: in| for)?(.+)?$", command)
    if "weather" in command or weather_match:
        city = weather_match.group(2).strip() if weather_match and weather_match.group(2) else "London"
        return {"action": "get_weather", "city": city, "endpoint": "GET /web/weather", "status": "parsed"}

    # Stocks
    stock_match = re.search(r"(?:stock|price)\s+(?:of\s+)?(\w+)", command)
    if stock_match or "stock" in command:
        ticker = stock_match.group(1) if stock_match else "AAPL"
        return {"action": "get_stock", "ticker": ticker, "endpoint": "GET /web/stocks", "status": "parsed"}

    # Maps
    if "map of" in command or "show map" in command:
        place_match = re.search(r"(?:map of|show map)\s+(.+)$", command)
        place = place_match.group(1) if place_match else "Tokyo"
        return {"action": "show_map", "place": place, "endpoint": "GET /web/maps/place", "status": "parsed"}

    if "directions" in command and ("to" in command or "from" in command):
        dir_match = re.search(r"directions\s+(?:from\s+(.+?)\s+)?to\s+(.+)$", command)
        if dir_match:
            origin = dir_match.group(1) if dir_match.group(1) else "current location"
            destination = dir_match.group(2)
            return {"action": "get_directions", "origin": origin, "destination": destination, "status": "parsed"}

    # Image generation
    if "generate image" in command or "create image" in command or "make a picture" in command:
        prompt = command.replace("generate image of", "").replace("generate image", "").replace("create image of", "").replace("create image", "").replace("make a picture of", "").strip()
        return {"action": "generate_image", "prompt": prompt or "abstract art", "endpoint": "POST /web/images/generate", "status": "parsed"}

    # ─── Document Commands ──────────────────────────────────────────

    if "create presentation" in command or "create ppt" in command:
        topic = command.replace("create presentation about", "").replace("create presentation on", "").replace("create presentation", "").strip()
        return {"action": "create_ppt", "topic": topic or "Untitled", "endpoint": "POST /documents/powerpoint", "status": "parsed"}

    if "create spreadsheet" in command or "create excel" in command:
        desc = command.replace("create spreadsheet", "").replace("create excel", "").strip()
        return {"action": "create_excel", "description": desc or "New Spreadsheet", "endpoint": "POST /documents/excel", "status": "parsed"}

    if "export to pdf" in command or "generate pdf" in command:
        return {"action": "create_pdf", "status": "triggered", "endpoint": "POST /documents/pdf"}

    # ─── Job Pipeline Commands ───────────────────────────────────────

    # Applications list (most specific, check before generic scan)
    if ("application" in command and ("show" in command or "status" in command or "my" in command)):
        return {"action": "list_applications", "endpoint": "GET /api/v1/applications", "status": "triggered"}

    if "resume" in command:
        if "upload" in command or "update" in command:
            return {"action": "upload_resume", "endpoint": "POST /api/v1/resume/upload", "status": "needs_file"}
        return {"action": "get_resume", "endpoint": "GET /api/v1/resume", "status": "triggered"}

    # Scan jobs with optional keyword filter
    scan_match = re.search(r"(?:scan|find)\s+(?:for\s+)?(.+?)\s+(?:jobs?|positions?|openings?)(?:\s|$)", command)
    if scan_match:
        keywords = scan_match.group(1).strip()
        return {
            "action": "scan_jobs",
            "endpoint": "POST /api/v1/jobs/search",
            "payload": {"keywords": keywords},
            "status": "parsed",
        }

    if (command.startswith("scan") or command.startswith("find")) and "job" in command:
        scan_fallback = re.search(r"(?:scan|find)\s+(?:for\s+)?(.+?)\s+(?:jobs?|positions?|openings?)", command)
        keywords = scan_fallback.group(1).strip() if scan_fallback else ""
        return {
            "action": "scan_jobs",
            "endpoint": "POST /api/v1/jobs/search",
            "payload": {"keywords": keywords if keywords else "all"},
            "status": "parsed",
        }

    if "scan jobs" in command or "find jobs" in command:
        return {"action": "scan_jobs", "endpoint": "POST /api/v1/jobs/search", "status": "triggered"}

    if ("how many" in command and "jobs" in command) or "job stats" in command or "application stats" in command:
        return {"action": "get_stats", "endpoint": "GET /api/v1/dashboard/stats", "status": "triggered"}

    if ("match" in command and "jobs" in command) or "score jobs" in command or "evaluate jobs" in command:
        return {"action": "batch_match", "endpoint": "POST /api/v1/jobs/batch-match", "status": "triggered"}

    opt_match = re.search(r"optimize(?:\s+resume)?(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if opt_match:
        job_id = opt_match.group(1)
        return {"action": "optimize_resume", "endpoint": f"POST /api/v1/jobs/{job_id}/optimize", "payload": {"job_id": job_id}, "status": "parsed"}

    cl_match = re.search(r"(?:cover letter|coverletter)(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if cl_match:
        job_id = cl_match.group(1)
        return {"action": "cover_letter", "endpoint": f"POST /api/v1/jobs/{job_id}/cover-letter", "payload": {"job_id": job_id}, "status": "parsed"}
    if "cover letter" in command or "write a letter" in command:
        return {"action": "cover_letter", "endpoint": "POST /api/v1/jobs/{id}/cover-letter", "status": "needs_job_id"}

    ce_match = re.search(r"(?:cold mail|cold email|email)(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if ce_match:
        job_id = ce_match.group(1)
        return {"action": "cold_mail", "endpoint": f"POST /api/v1/jobs/{job_id}/cold-mail", "payload": {"job_id": job_id}, "status": "parsed"}
    if "cold mail" in command or "cold email" in command or "send email" in command or "email about" in command:
        return {"action": "cold_mail", "endpoint": "POST /api/v1/jobs/{id}/cold-mail", "status": "needs_job_id"}

    apply_match = re.search(r"apply(?:\s+to|\s+for)?(?:\s+job)?\s+(\d+)", command)
    if apply_match:
        job_id = apply_match.group(1)
        return {"action": "apply", "endpoint": f"POST /api/v1/jobs/{job_id}/apply", "payload": {"job_id": job_id}, "status": "parsed"}
    if "apply" in command or "submit application" in command:
        return {"action": "apply", "endpoint": "POST /api/v1/jobs/{id}/apply", "status": "needs_job_id"}

    # ─── Content Pipeline Commands ───────────────────────────────────

    if "check trends" in command or "trending" in command:
        return {"action": "check_trends", "status": "triggered"}
    if "generate script" in command or "write script" in command:
        return {"action": "generate_script", "endpoint": "POST /social/generate-script", "status": "needs_topic"}
    if "render video" in command or "create video" in command:
        return {"action": "render_video", "endpoint": "POST /social/render-video", "status": "needs_script_id"}
    if "post content" in command or "publish" in command:
        return {"action": "post_content", "endpoint": "POST /social/post", "status": "needs_video_id"}

    # ─── Navigation Commands ─────────────────────────────────────────

    if "dashboard" in command or "home" in command:
        return {"action": "navigate", "target": "/dashboard"}
    if "analytics" in command or "stats" in command:
        return {"action": "navigate", "target": "/analytics"}
    if "content" in command or "studio" in command:
        return {"action": "navigate", "target": "/content"}
    if "jobs" in command or "career" in command:
        return {"action": "navigate", "target": "/jobs"}
    if "files" in command or "documents" in command:
        return {"action": "navigate", "target": "/files"}
    if "settings" in command or "preferences" in command:
        return {"action": "navigate", "target": "/settings"}
    if "notifications" in command or "alerts" in command:
        return {"action": "navigate", "target": "/settings"}
    if "help" in command or "commands" in command:
        return {"action": "help", "status": "triggered"}

    # ─── Fallback ────────────────────────────────────────────────────
    return {"action": "unknown", "command": command}


@router.post("/transcribe")
async def transcribe_audio():
    """Transcribe recent microphone input."""
    try:
        text = await speech_processor.transcribe_microphone(duration=5.0)
        await analytics_dao.log_activity("voice", "transcribe", f"Transcribed: {text[:50]}...")
        return {"text": text}
    except Exception as e:
        await analytics_dao.log_activity("voice", "transcribe_error", str(e), severity="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/speak")
async def speak_text(request: CommandRequest):
    """Synthesize text to speech using the configured TTS voice."""
    try:
        audio_bytes = await speech_processor.synthesize(request.command, voice=_tts_voice)
        return {"status": "synthesized", "size_bytes": len(audio_bytes), "voice": _tts_voice}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mic-level")
async def get_mic_level():
    """Get the current microphone audio level (0.0–1.0) from the wake word detector.
    Used by the frontend for real-time mic activity visualization."""
    detector = get_wake_word_detector()
    level = detector.get_mic_level()
    return {"level": round(level, 4), "is_listening": detector._running}


@router.post("/wake-word")
async def set_wake_word(request: WakeWordRequest):
    """Change the wake word dynamically. Rebuilds detection patterns immediately."""
    if not request.wake_word or len(request.wake_word.strip()) < 2:
        raise HTTPException(status_code=400, detail="Wake word must be at least 2 characters")

    new_word = request.wake_word.strip().lower()
    detector = get_wake_word_detector()
    detector.set_wake_word(new_word)

    # Persist to config for future sessions
    await settings_dao.set_setting("wake_word", new_word, "voice")
    await analytics_dao.log_activity("voice", "wake_word", f"Wake word changed to: {new_word}")

    return {"status": "updated", "wake_word": new_word}


@router.post("/conversation-mode")
async def set_conversation_mode(request: ConversationModeRequest):
    """Enable or disable the hands-free Alexa/Gemini-style conversation mode.
    When enabled, saying the wake word will automatically start a continuous
    conversation loop (listen → transcribe → respond → speak → loop).
    When disabled, the wake word only triggers the window focus (default).
    """
    global _hands_free_mode
    _hands_free_mode = request.enabled
    print(f"[Voice] Hands-free conversation mode {'enabled' if request.enabled else 'disabled'}")

    await settings_dao.set_setting("hands_free_mode", str(request.enabled), "voice")
    await analytics_dao.log_activity("voice", "conversation_mode", f"Hands-free mode: {request.enabled}")

    return {"status": "set", "hands_free_enabled": request.enabled}


@router.get("/status")
async def voice_status():
    """Get the current status of the voice system."""
    cfg = get_settings()

    is_running = wake_word_detector is not None and wake_word_detector._running
    recent_commands = await settings_dao.get_recent_commands(limit=5)

    # Get last Vosk recognition confidence from the running detector
    last_confidence = 0.0
    if wake_word_detector is not None:
        last_confidence = wake_word_detector.get_last_confidence()

    # Get active language from detector
    language = _language
    if wake_word_detector is not None:
        language = wake_word_detector.language

    return {
        "is_listening": is_running,
        "wake_word": cfg.wake_word,
        "language": language,
        "stt_model": "whisper",
        "tts_model": "edge-tts",
        "tts_voice": _tts_voice,
        "sensitivity": _sensitivity,
        "last_confidence": round(last_confidence, 4),
        "conversation_active": responder.conversation.is_active,
        "conversation_turns": responder.conversation.turn_count,
        "hands_free_mode": _hands_free_mode,
        "recent_commands": [
            {"transcript": c["transcript"], "confidence": c.get("confidence", 0.0), "created_at": c["created_at"]}
            for c in recent_commands
        ],
    }
