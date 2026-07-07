"""
FastAPI routes for voice control.
Handles wake word detection, speech transcription, TTS,
multi-turn conversation state, sensitivity control, and command history.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from config import get_settings
from ai.responder import BARQResponder
from . import WakeWordDetector, SpeechProcessor, play_command_accepted_sound, set_sound_enabled, get_sound_settings
from .conversation_listener import ConversationListener
from database import analytics_dao, settings_dao, db_connection
from system_control.command_whitelist import SAFE, WARN, DANGEROUS, classify_command, describe_classification, approve_command, is_approved, get_custom_rules
from .action_log import log_action, get_recent_actions, INFO, WARNING, DANGER as ACTION_DANGER

router = APIRouter()

# Singleton instances
wake_word_detector: WakeWordDetector | None = None
speech_processor = SpeechProcessor()
responder = BARQResponder()
conversation_listener = ConversationListener(stt=speech_processor, responder=responder)
# on_stop is set after _on_conversation_stopped is defined (below)

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


def _play_mp3_via_sounddevice(mp3_path: str):
    """Play an MP3 file through sounddevice with the configured output device.

    Uses the ffmpeg binary bundled with imageio-ffmpeg (moviepy dependency)
    to convert MP3 to WAV, then plays through sounddevice. This ensures audio
    goes through the BARQ-selected output device instead of the OS default.
    """
    import os
    import tempfile
    import wave
    import subprocess
    import numpy as np

    # Find ffmpeg via imageio-ffmpeg (bundled with moviepy)
    ffmpeg_path = None
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
        print("[Audio] ffmpeg not available \u2014 cannot play greeting audio")
        return

    # Convert MP3 to WAV using ffmpeg
    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    try:
        result = subprocess.run(
            [ffmpeg_path, "-y", "-i", mp3_path,
             "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1", wav_path],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors='replace')[:200]
            print(f"[Audio] ffmpeg conversion failed: {err}")
            return

        # Read WAV and play through sounddevice with configured output device
        import sounddevice as sd
        from .audio_device import resolve_output_device
        from config import get_settings as _cfg

        output_device = resolve_output_device(_cfg().audio_output_device)

        with wave.open(wav_path, "rb") as wf:
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            rate = wf.getframerate()

        sd.play(data, rate, device=output_device)
        sd.wait()
        print("[Audio] Wake greeting played through sounddevice")
    except Exception as e:
        print(f"[Audio] TTS playback error: {e}")
    finally:
        try:
            os.unlink(wav_path)
        except Exception:
            pass


async def _speak_wake_greeting():
    """Gather weather, system, and job info and speak a greeting via TTS.
    Runs after wake word detection, then enters conversation mode."""
    responder.is_processing = True
    try:
        info_parts = []

        # 1. System status
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            info_parts.append(
                f"Your system is running. CPU is at {cpu} percent. "
                f"Memory is {mem.percent} percent used with {mem.available / (1024**3):.1f} gigabytes free."
            )
        except Exception:
            info_parts.append("Your system is running.")

        # 2. Job search status
        try:
            row = await db_connection.fetch_one(
                "SELECT COUNT(*) as count FROM job_listings"
            )
            total_jobs = row["count"] if row else 0

            submitted = await db_connection.fetch_one(
                "SELECT COUNT(*) as count FROM applications WHERE status = 'submitted'"
            )
            interviews = await db_connection.fetch_one(
                "SELECT COUNT(*) as count FROM applications WHERE status = 'interview'"
            )
            queued = await db_connection.fetch_one(
                "SELECT COUNT(*) as count FROM applications WHERE status = 'queued'"
            )

            sub_count = submitted["count"] if submitted else 0
            int_count = interviews["count"] if interviews else 0
            queued_count = queued["count"] if queued else 0

            if total_jobs > 0:
                info_parts.append(
                    f"Job search: {total_jobs} jobs scanned, {queued_count} pending review, "
                    f"{sub_count} applications submitted, {int_count} interviews."
                )
        except Exception:
            pass

        # 3. Weather (if API key is configured — uses saved city from DB or 'London' as fallback)
        try:
            import httpx
            import os as _os
            api_key = _os.getenv("OPENWEATHER_API_KEY", "")
            if api_key:
                # Try to get saved city from user settings
                city = await settings_dao.get_setting("weather_city")
                if not city:
                    city = "London"
                async with httpx.AsyncClient() as client:
                    geo_resp = await client.get(
                        "https://api.openweathermap.org/geo/1.0/direct",
                        params={"q": city, "limit": 1, "appid": api_key},
                        timeout=5,
                    )
                    geo_data = geo_resp.json()
                    if geo_data:
                        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
                        w_resp = await client.get(
                            "https://api.openweathermap.org/data/2.5/weather",
                            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
                            timeout=5,
                        )
                        w = w_resp.json()
                        if "main" in w:
                            temp = w["main"]["temp"]
                            desc = w["weather"][0]["description"]
                            city_name = geo_data[0].get("name", "your area")
                            info_parts.append(
                                f"Weather in {city_name}: {desc}, {temp:.0f} degrees Celsius."
                            )
        except Exception:
            pass

        # 4. Stock prices (if yfinance is installed — reads configured tickers from DB setting)
        try:
            import os as _os
            tickers_str = await settings_dao.get_setting("stock_tickers")
            if tickers_str:
                tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()][:5]
                if tickers:
                    import yfinance as yf
                    prices = []
                    for t in tickers:
                        try:
                            stock = yf.Ticker(t)
                            info = stock.info
                            price = info.get("currentPrice")
                            change = info.get("regularMarketChangePercent", 0)
                            if price:
                                direction = "up" if change and change >= 0 else "down"
                                change_str = f"{abs(change):.1f}%" if change else ""
                                prices.append(f"{t} at ${price:.2f}, {direction} {change_str}")
                        except Exception:
                            continue
                    if prices:
                        info_parts.append(f"Stocks: {"; ".join(prices)}.")
        except Exception:
            pass

        # 5. News headlines (if NEWS_API_KEY is configured)
        try:
            import os as _os
            news_key = _os.getenv("NEWS_API_KEY", "")
            if news_key:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://newsapi.org/v2/top-headlines",
                        params={"language": "en", "pageSize": 3, "apiKey": news_key},
                        timeout=5,
                    )
                    data = resp.json()
                    articles = data.get("articles", [])
                    if articles:
                        headlines = [
                            a["title"].rstrip(".!?") for a in articles[:3] if a.get("title")
                        ]
                        news_text = ". ".join(headlines) + "."
                        info_parts.append(f"Latest headlines: {news_text}")
        except Exception:
            pass

        # 6. Upcoming interviews and scheduled tasks (calendar check)
        try:
            from datetime import date
            today = date.today().isoformat()

            # Upcoming interviews from applications
            interviews = await db_connection.fetch_all(
                "SELECT j.company, a.interview_date FROM applications a "
                "JOIN job_listings j ON a.job_listing_id = j.id "
                "WHERE a.interview_date IS NOT NULL AND a.interview_date >= ? "
                "ORDER BY a.interview_date ASC LIMIT 3",
                (today,),
            )
            if interviews:
                interview_texts = []
                for row in interviews:
                    company = row["company"]
                    iv_date = row["interview_date"]
                    if iv_date == today:
                        interview_texts.append(f"{company} today")
                    else:
                        interview_texts.append(f"{company} on {iv_date}")
                info_parts.append(
                    f"Upcoming interviews: {", ".join(interview_texts)}."
                )

            # Today's scheduled tasks
            tasks = await db_connection.fetch_all(
                "SELECT name FROM scheduled_tasks WHERE enabled = 1 AND (last_run IS NULL OR date(last_run) < ?) LIMIT 2",
                (today,),
            )
            if tasks:
                task_names = [t["name"] for t in tasks]
                info_parts.append(
                    f"Pending tasks: {", ".join(task_names)}."
                )
        except Exception:
            pass

        # 7. Unread email count (if SMTP/IMAP credentials are configured)
        try:
            import os as _os
            host = _os.getenv("SMTP_HOST", "smtp.gmail.com")
            user = _os.getenv("SMTP_USER", "")
            password = _os.getenv("SMTP_PASS", "")
            if user and password:
                import imaplib
                # Convert SMTP host to IMAP host (e.g. smtp.gmail.com → imap.gmail.com)
                imap_host = host.replace("smtp.", "imap.") if "smtp." in host else f"imap.{host}"
                try:
                    mail = imaplib.IMAP4_SSL(imap_host, timeout=10)
                    mail.login(user, password)
                    mail.select("INBOX")
                    _, data = mail.search(None, "UNSEEN")
                    unread_count = len(data[0].split()) if data[0] else 0
                    mail.logout()
                    if unread_count > 0:
                        label = "email" if unread_count == 1 else "emails"
                        info_parts.append(f"You have {unread_count} unread {label}.")
                except Exception:
                    pass
        except Exception:
            pass

        # 8. GitHub notifications (if GITHUB_TOKEN is configured)
        try:
            import os as _os
            gh_token = _os.getenv("GITHUB_TOKEN", "")
            if gh_token:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.github.com/notifications",
                        headers={
                            "Authorization": f"Bearer {gh_token}",
                            "Accept": "application/vnd.github.v3+json",
                        },
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        notifications = resp.json()
                        gh_count = len(notifications)
                        if gh_count > 0:
                            # Count PRs vs issues from notification subjects
                            pulls = sum(1 for n in notifications if n["subject"]["url"].find("/pulls/") >= 0 or n["subject"]["type"] == "PullRequest")
                            issues = gh_count - pulls
                            parts = []
                            if pulls > 0:
                                parts.append(f"{pulls} pull request{'s' if pulls > 1 else ''}")
                            if issues > 0:
                                parts.append(f"{issues} issue{'s' if issues > 1 else ''}")
                            info_parts.append(f"GitHub: {" and ".join(parts)} need attention.")
        except Exception:
            pass

        # 9. Notes count
        try:
            notes_total = await db_connection.fetch_one(
                "SELECT COUNT(*) as count FROM notes"
            )
            notes_pinned = await db_connection.fetch_one(
                "SELECT COUNT(*) as count FROM notes WHERE pinned = 1"
            )
            total = notes_total["count"] if notes_total else 0
            pinned = notes_pinned["count"] if notes_pinned else 0
            if total > 0:
                notes_label = "note" if total == 1 else "notes"
                pinned_label = f", {pinned} pinned" if pinned > 0 else ""
                info_parts.append(f"You have {total} {notes_label}{pinned_label}.")
        except Exception:
            pass

        # 10. Generated images count (from activity log)
        try:
            img_row = await db_connection.fetch_one(
                "SELECT COUNT(*) as count FROM activity_log WHERE action = 'generate_image'"
            )
            img_count = img_row["count"] if img_row else 0
            if img_count > 0:
                img_label = "image" if img_count == 1 else "images"
                info_parts.append(f"Gallery: {img_count} {img_label} generated.")
        except Exception:
            pass

        # Compose greeting
        if info_parts:
            greeting = "Hello! " + " ".join(info_parts) + " How can I help you?"
        else:
            greeting = "Hello! How can I help you?"

        print(f"[WakeGreeting] {greeting}")

        # Synthesize and play greeting via TTS
        try:
            import edge_tts
            import tempfile
            from pathlib import Path

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            communicate = edge_tts.Communicate(greeting, _tts_voice)
            await communicate.save(tmp_path)

            # Play through sounddevice with configured output device
            responder.is_speaking = True
            try:
                _play_mp3_via_sounddevice(tmp_path)
            finally:
                responder.is_speaking = False

            # Cleanup temp file after playback
            Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            print(f"[WakeGreeting] TTS playback error: {e}")

        # Log the wake greeting activity
        await analytics_dao.log_activity("voice", "wake_greeting", "Wake word detected with greeting")

    except Exception as e:
        print(f"[WakeGreeting] Error gathering info: {e}")

    # Always enter conversation mode after greeting
    responder.is_processing = False
    await conversation_listener.start_conversation()


def _on_conversation_stopped():
    """Callback invoked when the conversation loop ends.

    Resumes the wake word detector so the user can trigger a new conversation
    by saying the wake word again.
    """
    global wake_word_detector
    if wake_word_detector is not None:
        wake_word_detector.resume()
        print("[Voice] Wake word detector resumed after conversation end")
    else:
        print("[Voice] No wake word detector to resume")

# Wire up the callback now that the function is defined
conversation_listener.on_stop = _on_conversation_stopped

def _on_wake_word_callback():
    """Callback fired when wake word is detected by the background listener.

    Immediately pauses the wake word detector to release the microphone stream,
    then speaks a greeting with system/job/weather/stocks/news info (if enabled),
    and starts conversation mode (if hands-free is also enabled).

    When the conversation ends, ``_on_conversation_stopped`` is called which
    resumes the wake word detector so the user can trigger a new conversation.
    """
    global _hands_free_mode
    global _wake_greeting_enabled

    # ── Step 1: Immediately pause the wake word detector to free the mic ──
    global wake_word_detector
    if wake_word_detector is not None:
        wake_word_detector.pause()
        print("[Voice] Wake word detector paused — microphone released")
    else:
        print("[Voice] No wake word detector to pause")

    if not _wake_greeting_enabled:
        if not _hands_free_mode:
            print("[Voice] Hands-free mode disabled — skipping wake greeting")
            # We still need to resume the detector since we paused it
            _on_conversation_stopped()
            return
        print("[Voice] Wake greeting disabled — skipping greeting, starting conversation")
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(conversation_listener.start_conversation())
            # Keep the loop alive for conversation mode
            if conversation_listener.is_active:
                conversation_listener._managed_loop = loop
                loop.run_forever()
                conversation_listener._managed_loop = None
            loop.close()
        except Exception as e:
            print(f"[Voice] Conversation start error: {e}")
        return
    if not _hands_free_mode:
        print("[Voice] Hands-free mode disabled — skipping wake greeting")
        # Resume the detector since we paused it but aren't starting conversation
        _on_conversation_stopped()
        return
    print("[Voice] Wake word detected — speaking greeting and starting conversation")
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_speak_wake_greeting())
        # Keep the loop alive so the conversation loop task can continue
        if conversation_listener.is_active:
            conversation_listener._managed_loop = loop
            loop.run_forever()
            conversation_listener._managed_loop = None
        loop.close()
    except Exception as e:
        print(f"[Voice] Wake greeting error: {e}")


def _on_conversation_trigger():
    """Callback fired from the wake word detector.
    Conversation is now handled by _speak_wake_greeting() which runs after
    the wake word callback, so this is intentionally a no-op.
    """
    pass


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

    # Load VAD silence timeout from DB
    vad_val = await settings_dao.get_setting("vad_silence_timeout")
    if vad_val is not None:
        try:
            global _vad_silence_timeout
            _vad_silence_timeout = float(vad_val)
            if _vad_silence_timeout < 0.1 or _vad_silence_timeout > 3.0:
                _vad_silence_timeout = 0.4
            print(f"[Voice] VAD silence timeout loaded from DB: {_vad_silence_timeout}s")
        except (ValueError, TypeError):
            pass
    else:
        print(f"[Voice] No saved VAD timeout in DB, using default: {_vad_silence_timeout}s")
    # Propagate to the conversation listener
    conversation_listener.vad_silence_timeout = _vad_silence_timeout

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

    # Load wake greeting enabled setting
    wg_val = await settings_dao.get_setting("wake_greeting_enabled")
    if wg_val is not None:
        global _wake_greeting_enabled
        _wake_greeting_enabled = wg_val.lower() == "true"
        print(f"[Voice] Wake greeting enabled loaded from DB: {_wake_greeting_enabled}")

# ─── Multi-turn conversation state ─────────────────────────────────────────

_tts_voice: str = "en-US-JennyNeural"
_sensitivity: str = "medium"
_language: str = "en"  # "en" or "hi"
_hands_free_mode: bool = True  # Alexa/Gemini-style hands-free conversation mode
_wake_greeting_enabled: bool = True  # Speak greeting when wake word is detected (separate from hands-free)
_vad_silence_timeout: float = 0.4  # VAD endpointing silence threshold in seconds (300-500ms range)
# Conversation manager is now managed by the shared responder instance
# _responder and conversation_listener are the canonical singletons above

# ─── Pending command approval state ────────────────────────────────
# Stores the command + tier awaiting voice confirmation (yes/no).
# Cleared after a confirmation decision is made.
_pending_run_command: dict[str, Any] = {
    "command": None,
    "tier": None,
}


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


class WeatherCityRequest(BaseModel):
    city: str  # city name for weather in wake greeting


class VADSettingsRequest(BaseModel):
    silence_timeout: float  # seconds of silence before VAD endpointing (0.1–3.0)


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
    Uses ConversationManager for context and Ollama for LLM responses.
    Returns both the text response and base64-encoded TTS audio using the
    same Edge-TTS voice as the wake greeting."""
    try:
        result = await responder.respond(request.message)

        # Extract text from the response
        if isinstance(result, dict):
            text = result.get("text") or result.get("response") or str(result)
        elif isinstance(result, str):
            text = result
        else:
            text = str(result)

        # Synthesize TTS audio using same voice as wake greeting
        try:
            audio_bytes = await speech_processor.synthesize(text, voice=_tts_voice)
            import base64
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception:
            audio_b64 = None

        await analytics_dao.log_activity("voice", "chat", f"Chat: {request.message[:50]}...")

        response = {
            "text": text,
            "audio_base64": audio_b64,
        }
        if isinstance(result, dict):
            # Merge any additional fields from the original result
            for k, v in result.items():
                if k not in ("text", "response", "audio_base64"):
                    response[k] = v
        return response

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

    # Log every parsed command to the floating action log
    action = result.get("action", "unknown")
    if action != "unknown":
        desc = result.get("command", result.get("target", result.get("query", action.replace("_", " "))))
        severity = INFO
        if action in ("run_command_confirm",) and result.get("tier") in (WARN, DANGEROUS):
            severity = WARNING
        if result.get("tier") == DANGEROUS:
            severity = ACTION_DANGER
        await log_action(
            action=action,
            description=str(desc)[:120],
            severity=severity,
            metadata={"command": command[:80], "tier": result.get("tier")},
        )

    # Play command accepted sound + update conversation manager
    if action != "unknown":
        play_command_accepted_sound()
        if not cm.is_active:
            cm.start_session()

    # Store the result as a JSON string so follow-up detection can parse it back
    import json as _json
    cm.add_assistant_message(_json.dumps(result))

    return result


@router.post("/command/approve")
async def voice_approve_command(request: CommandRequest):
    """Approve a voice-parsed command for execution.
    Delegates to the system whitelist approval mechanism.
    Returns tier info so the caller knows if it's safe, warn, or dangerous.
    """
    cmd_text = request.command.strip()
    custom_rules = await get_custom_rules()
    tier = classify_command(cmd_text, custom_rules)

    if tier in (WARN, DANGEROUS):
        approve_command(cmd_text, tier)
        return {
            "status": "approved",
            "tier": tier,
            "tier_description": describe_classification(tier),
            "command": cmd_text,
            "message": f"{'DANGEROUS' if tier == DANGEROUS else 'MODERATE RISK'} command approved for this session via voice.",
        }

    return {
        "status": "already_safe",
        "tier": SAFE,
        "command": cmd_text,
        "message": "Command is classified as SAFE — no approval needed.",
    }


@router.post("/command/execute")
async def voice_execute_approved_command(request: CommandRequest):
    """Execute a command that has been pre-approved through the voice pipeline.
    Checks whitelist before executing, returning requires_approval if not yet approved.
    """
    cmd_text = request.command.strip()
    custom_rules = await get_custom_rules()
    tier = classify_command(cmd_text, custom_rules)

    # Check approval
    if tier == DANGEROUS and not is_approved(cmd_text, DANGEROUS):
        return {
            "status": "requires_approval",
            "tier": DANGEROUS,
            "tier_description": describe_classification(DANGEROUS),
            "command": cmd_text,
            "message": "This command is DANGEROUS. Approve via POST /voice/command/approve first.",
        }

    if tier == WARN and not is_approved(cmd_text, WARN):
        return {
            "status": "requires_approval",
            "tier": WARN,
            "tier_description": describe_classification(WARN),
            "command": cmd_text,
            "message": "This command is MODERATE RISK. Approve via POST /voice/command/approve first.",
        }

    # Execute via the system terminal endpoint
    from system_control.routes import run_command as system_run_command
    from system_control.routes import CommandRequest as SysCommandRequest

    sys_request = SysCommandRequest(command=cmd_text, cwd=None)
    result = await system_run_command(sys_request)

    # Log the voice-executed command
    await analytics_dao.log_activity(
        "voice", "command_execute",
        f"Voice executed: {cmd_text[:80]} — tier: {tier}"
    )

    return {
        "source": "voice",
        "tier": tier,
        **result,
    }


async def _parse_and_route(command: str, is_follow_up: bool = False, last_intent: Optional[str] = None) -> dict[str, Any]:
    """
    Parse a voice command and determine the appropriate action.
    Supports follow-up context resolution for multi-turn conversations.
    """

    global _pending_run_command

    # ─── Conversation follow-up handling ────────────────────────────

    if is_follow_up and last_intent:
        # ─── Handle run_command_confirm (voice whitelist approval) ─
        if last_intent == "run_command_confirm":
            pending = _pending_run_command

            if command in ("yes", "yeah", "confirm", "do it", "go ahead", "okay"):
                cmd_text = pending.get("command")
                tier = pending.get("tier")
                if cmd_text and tier:
                    # Approve and execute the command
                    approve_command(cmd_text, tier)
                    _pending_run_command = {"command": None, "tier": None}
                    if tier == DANGEROUS:
                        tier_label = "DANGEROUS"
                    else:
                        tier_label = "MODERATE RISK"
                    tier_label_text = f"{tier_label} command approved. Executing..."
                    return {
                        "action": "run_command_execute",
                        "command": cmd_text,
                        "tier": tier,
                        "status": "approved",
                        "message": tier_label_text,
                        "follow_up": True,
                    }
                return {
                    "action": "run_command_execute",
                    "status": "error",
                    "message": "No pending command to execute.",
                    "follow_up": True,
                }

            if command in ("no", "nope", "cancel", "stop", "never mind", "abort"):
                _pending_run_command = {"command": None, "tier": None}
                return {
                    "action": "cancel",
                    "status": "cancelled",
                    "message": "Command cancelled.",
                    "follow_up": True,
                }

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

    if command in ("start listening", "wake up", "computer", "hey computer"):
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
            cmd_text = cmd_match.group(1)
            custom = await get_custom_rules()
            tier = classify_command(cmd_text, custom)

            # Already approved in this session → proceed directly
            if is_approved(cmd_text, tier):
                return {
                    "action": "run_command",
                    "command": cmd_text,
                    "endpoint": "POST /system/terminal/run",
                    "status": "parsed",
                    "tier": tier,
                    "tier_description": describe_classification(tier),
                    "requires_approval": False,
                }

            # Needs approval → enter voice confirmation flow
            if tier in (WARN, DANGEROUS):
                _pending_run_command = {"command": cmd_text, "tier": tier}
                return {
                    "action": "run_command_confirm",
                    "command": cmd_text,
                    "tier": tier,
                    "tier_description": describe_classification(tier),
                    "status": "needs_confirmation",
                }

            # SAFE → proceed directly
            return {
                "action": "run_command",
                "command": cmd_text,
                "endpoint": "POST /system/terminal/run",
                "status": "parsed",
                "tier": tier,
                "tier_description": describe_classification(tier),
                "requires_approval": False,
            }

    if "git" in command:
        return {"action": "git_command", "command": command, "status": "parsed"}

    if "deploy" in command:
        return {"action": "deploy", "command": command, "status": "parsed"}

    tunnel_match = re.search(r"(?:expose|tunnel)\s+port\s+(\d+)", command)
    if tunnel_match:
        return {"action": "expose_port", "port": int(tunnel_match.group(1)), "endpoint": "POST /system/tunnel/expose", "status": "parsed"}

    # ─── Approvals / Whitelist ──────────────────────────────────────────

    if "clear" in command and "approval" in command:
        return {"action": "clear_approvals", "status": "triggered"}

    if "show" in command and "approval" in command:
        return {"action": "navigate", "target": "/settings"}

    # ─── Desktop Overlay ──────────────────────────────────────────

    if "overlay" in command:
        if "show" in command:
            return {"action": "overlay_show", "status": "triggered"}
        if "hide" in command:
            return {"action": "overlay_hide", "status": "triggered"}
        return {"action": "overlay_toggle", "status": "triggered"}

    # ─── Diagnostics ─────────────────────────────────────────────────

    if "diagnostics" in command or ("system" in command and "status" in command):
        return {"action": "show_diagnostics", "status": "triggered"}

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

    # Upload/update resume (specific action, check before generic resume and optimize)
    if ("upload" in command or "update" in command) and "resume" in command:
        return {"action": "upload_resume", "endpoint": "POST /api/v1/resume/upload", "status": "needs_file"}

    # Optimize resume (must come before generic resume check since "optimize resume" contains "resume")
    opt_match = re.search(r"optimize(?:\s+resume)?(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if opt_match:
        job_id = opt_match.group(1)
        return {"action": "optimize_resume", "endpoint": f"POST /api/v1/jobs/{job_id}/optimize", "payload": {"job_id": job_id}, "status": "parsed"}

    # Cover letter with job ID (check before generic resume since "cover letter" could be near "resume")
    cl_match = re.search(r"(?:cover letter|coverletter)(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if cl_match:
        job_id = cl_match.group(1)
        return {"action": "cover_letter", "endpoint": f"POST /api/v1/jobs/{job_id}/cover-letter", "payload": {"job_id": job_id}, "status": "parsed"}
    if "cover letter" in command or "write a letter" in command:
        return {"action": "cover_letter", "endpoint": "POST /api/v1/jobs/{id}/cover-letter", "status": "needs_job_id"}

    # Cold mail with job ID (check before generic resume for similar reasons)
    ce_match = re.search(r"(?:cold mail|cold email|email)(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if ce_match:
        job_id = ce_match.group(1)
        return {"action": "cold_mail", "endpoint": f"POST /api/v1/jobs/{job_id}/cold-mail", "payload": {"job_id": job_id}, "status": "parsed"}
    if "cold mail" in command or "cold email" in command or "send email" in command or "email about" in command:
        return {"action": "cold_mail", "endpoint": "POST /api/v1/jobs/{id}/cold-mail", "status": "needs_job_id"}

    # Apply with job ID (check before generic resume just in case)
    apply_match = re.search(r"apply(?:\s+to|\s+for)?(?:\s+job)?\s+(\d+)", command)
    if apply_match:
        job_id = apply_match.group(1)
        return {"action": "apply", "endpoint": f"POST /api/v1/jobs/{job_id}/apply", "payload": {"job_id": job_id}, "status": "parsed"}
    if "apply" in command or "submit application" in command:
        return {"action": "apply", "endpoint": "POST /api/v1/jobs/{id}/apply", "status": "needs_job_id"}

    # Generic resume (fallback — any other "resume" command)
    if "resume" in command:
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


@router.get("/action-log/recent")
async def action_log_recent(limit: int = Query(default=10, ge=1, le=100)):
    """Get the most recent AI-executed actions for the floating action log."""
    actions = await get_recent_actions(limit=limit)
    return {"actions": actions}


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream a chat response token-by-token via Server-Sent Events.
    Each token is sent as an SSE event and can be played via incremental TTS.
    """
    from fastapi.responses import StreamingResponse

    async def event_generator():
        import asyncio as _asyncio
        import json as _json

        try:
            # Stream from Ollama's native streaming API token-by-token
            # This uses the responder's Ollama client with stream=True
            from utils.ollama_client import OllamaClient

            cm = responder.conversation
            cm.add_user_message(request.message)
            context = cm.get_context()

            llm = OllamaClient()
            full_text = ""

            # Use the streaming chat method
            async for token in llm.stream_chat(context):
                full_text += token
                yield f"data: {_json.dumps({'type': 'token', 'text': token})}\n\n"

            cm.add_assistant_message(full_text)

            # Log the action
            action_text = full_text[:80]
            await log_action(
                "chat_response",
                f"AI: {action_text}..." if len(full_text) > 80 else f"AI: {full_text}",
                severity=INFO,
                metadata={"message": request.message[:100], "response_length": len(full_text)},
            )

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/speak")
async def speak_text(request: CommandRequest):
    """Synthesize text to speech using the configured TTS voice."""
    try:
        audio_bytes = await speech_processor.synthesize(request.command, voice=_tts_voice)
        return {"status": "synthesized", "size_bytes": len(audio_bytes), "voice": _tts_voice}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices")
async def list_audio_devices():
    """List all available audio input/output devices.
    Used by the frontend to let users choose which mic/speaker to use.
    """
    from .audio_device import get_device_list, reset_cache
    reset_cache()  # Refresh device list in case hardware changed
    devices = get_device_list()
    # Also show which device is currently selected
    cfg = get_settings()
    input_device = None
    output_device = None
    import sounddevice as sd
    try:
        default_input = sd.query_devices(kind='input')
        default_output = sd.query_devices(kind='output')
        input_device = default_input['name'] if default_input else None
        output_device = default_output['name'] if default_output else None
    except Exception:
        pass
    return {
        "devices": devices,
        "config": {
            "input_setting": cfg.audio_input_device,
            "output_setting": cfg.audio_output_device,
        },
        "defaults": {
            "input_device": input_device,
            "output_device": output_device,
        },
    }


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


@router.get("/vad-settings")
async def get_vad_settings():
    """Get current VAD (Voice Activity Detection) settings."""
    return {
        "silence_timeout": round(_vad_silence_timeout, 2),
        "min": 0.1,
        "max": 3.0,
        "step": 0.05,
    }


@router.post("/vad-settings")
async def set_vad_settings(request: VADSettingsRequest):
    """Update VAD silence timeout and persist to database."""
    global _vad_silence_timeout

    timeout = max(0.1, min(3.0, request.silence_timeout))
    _vad_silence_timeout = timeout
    # Propagate to the conversation listener immediately
    conversation_listener.vad_silence_timeout = timeout

    await settings_dao.set_setting(
        "vad_silence_timeout", str(round(timeout, 2)), "voice"
    )
    await analytics_dao.log_activity(
        "voice", "vad_settings",
        f"VAD silence timeout set to {timeout}s"
    )
    print(f"[Voice] VAD silence timeout updated to {timeout}s")

    return {
        "status": "set",
        "silence_timeout": round(timeout, 2),
    }


@router.post("/weather-city")
async def set_weather_city(request: WeatherCityRequest):
    """Set the city for weather in the wake word greeting."""
    city = request.city.strip()
    if not city or len(city) < 2:
        raise HTTPException(status_code=400, detail="City name must be at least 2 characters")

    await settings_dao.set_setting("weather_city", city, "voice")
    await analytics_dao.log_activity("voice", "weather_city", f"Weather city set to: {city}")
    print(f"[Voice] Weather city set to: {city}")

    return {"status": "set", "weather_city": city}


@router.post("/wake-greeting-mode")
async def set_wake_greeting_mode(request: ConversationModeRequest):
    """Enable or disable the wake word greeting.
    When enabled, saying the wake word will speak system/job/weather/stocks/news
    info before entering conversation mode. When disabled, the wake word
    directly enters conversation mode (or just focuses the window).
    This is independent of hands-free conversation mode.
    """
    global _wake_greeting_enabled
    _wake_greeting_enabled = request.enabled
    print(f"[Voice] Wake greeting {'enabled' if request.enabled else 'disabled'}")

    await settings_dao.set_setting("wake_greeting_enabled", str(request.enabled), "voice")
    await analytics_dao.log_activity("voice", "wake_greeting_mode", f"Wake greeting: {request.enabled}")

    return {"status": "set", "wake_greeting_enabled": request.enabled}


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


@router.websocket("/ws/status")
async def voice_status_ws(websocket: WebSocket):
    """WebSocket endpoint for real-time voice status updates.
    Pushes full status + mic level every 100ms — no polling needed."""
    await websocket.accept()
    try:
        while True:
            detector = get_wake_word_detector()
            is_running = detector._running if detector else False
            mic_level = detector.get_mic_level() if detector else 0.0

            await websocket.send_json({
                "type": "voice_status",
                "is_listening": is_running,
                "conversation_active": responder.conversation.is_active,
                "is_speaking": responder.is_speaking,
                "is_processing": responder.is_processing,
                "conversation_turns": responder.conversation.turn_count,
                "mic_level": round(mic_level, 4),
                "stt_text": getattr(responder, 'stt_text', ''),
                "stt_confidence": getattr(responder, 'stt_confidence', 0.0),
            })
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass


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

    # Get weather city setting
    weather_city = await settings_dao.get_setting("weather_city")
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
        "is_speaking": responder.is_speaking,
        "is_processing": responder.is_processing,
        "hands_free_mode": _hands_free_mode,
        "wake_greeting_enabled": _wake_greeting_enabled,
        "weather_city": weather_city or "London",
        "recent_commands": [
            {"transcript": c["transcript"], "confidence": c.get("confidence", 0.0), "created_at": c["created_at"]}
            for c in recent_commands
        ],
    }
