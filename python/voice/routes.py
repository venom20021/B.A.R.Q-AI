"""
FastAPI routes for voice control.
Uses database DAOs for command logging and activity tracking.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from . import WakeWordDetector, SpeechProcessor
from database import analytics_dao, settings_dao

router = APIRouter()

# Singleton instances
wake_word_detector: WakeWordDetector | None = None
speech_processor = SpeechProcessor()


class CommandRequest(BaseModel):
    command: str


@router.post("/start")
async def start_listening():
    """Start wake word detection."""
    global wake_word_detector

    if wake_word_detector is None:
        wake_word_detector = WakeWordDetector()

    wake_word_detector.start()
    await analytics_dao.log_activity("voice", "start_listening", "Wake word detection started")
    return {"status": "listening", "wake_word": "hey barq"}


@router.post("/stop")
async def stop_listening():
    """Stop wake word detection."""
    global wake_word_detector

    if wake_word_detector:
        wake_word_detector.stop()

    await analytics_dao.log_activity("voice", "stop_listening", "Wake word detection stopped")
    return {"status": "stopped"}


@router.post("/command")
async def process_command(request: CommandRequest):
    """
    Process a voice command text.
    Routes to the appropriate module and logs the command.
    """
    command = request.command.lower().strip()

    # Log to database
    await settings_dao.log_command({
        "transcript": command,
        "confidence": 0.0,
        "action": "processed",
        "processed": True,
    })

    # Basic command routing
    if "scan jobs" in command or "find jobs" in command:
        return {"action": "scan_jobs", "status": "triggered"}
    elif "check trends" in command or "trending" in command:
        return {"action": "check_trends", "status": "triggered"}
    elif "dashboard" in command or "home" in command:
        return {"action": "navigate", "target": "/dashboard"}
    elif "analytics" in command or "stats" in command:
        return {"action": "navigate", "target": "/analytics"}
    elif "notifications" in command or "alerts" in command:
        return {"action": "navigate", "target": "/settings"}
    elif "settings" in command:
        return {"action": "navigate", "target": "/settings"}
    else:
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
    """Synthesize text to speech."""
    try:
        audio_bytes = await speech_processor.synthesize(request.command)
        return {"status": "synthesized", "size_bytes": len(audio_bytes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def voice_status():
    """Get the current status of the voice system."""
    is_running = wake_word_detector is not None and wake_word_detector._running
    recent_commands = await settings_dao.get_recent_commands(limit=5)
    return {
        "is_listening": is_running,
        "wake_word": "hey barq",
        "stt_model": "whisper",
        "tts_model": "edge-tts",
        "recent_commands": [
            {"transcript": c["transcript"], "created_at": c["created_at"]}
            for c in recent_commands
        ],
    }
