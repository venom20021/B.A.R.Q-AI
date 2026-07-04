"""
FastAPI routes for voice control.
Handles wake word detection, speech transcription, TTS,
and routes voice commands to the appropriate BARQ modules.
"""

import re
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
    Process a voice command text and route to the appropriate BARQ module.

    Supports the full job automation pipeline:
      - Scan/find jobs with keywords
      - Match jobs to resume
      - Optimize resume for a specific job
      - Write cover letter
      - Send cold email
      - Apply to job
      - Show applications/stats
      - Navigate to dashboard/analytics/settings
      - Content pipeline (trends, scripts, render, post)
    """
    command = request.command.lower().strip()

    # Log to database
    await settings_dao.log_command({
        "transcript": command,
        "confidence": 0.0,
        "action": "processed",
        "processed": True,
    })

    # ─── Job Pipeline Commands ───────────────────────────────────────

    # Applications list (most specific, check before generic scan)
    # "show my applications", "application status", "my applications"
    if ("application" in command and ("show" in command or "status" in command or "my" in command)):
        return {"action": "list_applications", "endpoint": "GET /api/v1/applications", "status": "triggered"}

    # Resume (check before scan to avoid "find my resume" -> scan)
    if "resume" in command:
        if "upload" in command or "update" in command:
            return {"action": "upload_resume", "endpoint": "POST /api/v1/resume/upload", "status": "needs_file"}
        return {"action": "get_resume", "endpoint": "GET /api/v1/resume", "status": "triggered"}

    # Scan jobs with optional keyword filter
    # "scan for python jobs", "find full stack jobs on linkedin"
    # Use word boundary instead of $ to catch trailing words like "on linkedin"
    scan_match = re.search(r"(?:scan|find)\s+(?:for\s+)?(.+?)\s+(?:jobs?|positions?|openings?)(?:\s|$)", command)
    if scan_match:
        keywords = scan_match.group(1).strip()
        return {
            "action": "scan_jobs",
            "endpoint": "POST /api/v1/jobs/search",
            "payload": {"keywords": keywords},
            "status": "parsed",
        }

    # Fallback: any command starting with "scan" or "find" that contains "job"
    # Catches: "scan python jobs on linkedin", "find developer positions today"
    if (command.startswith("scan") or command.startswith("find")) and "job" in command:
        # Extract everything between scan/find and the job keyword as the search query
        scan_fallback = re.search(r"(?:scan|find)\s+(?:for\s+)?(.+?)\s+(?:jobs?|positions?|openings?)", command)
        keywords = scan_fallback.group(1).strip() if scan_fallback else ""
        return {
            "action": "scan_jobs",
            "endpoint": "POST /api/v1/jobs/search",
            "payload": {"keywords": keywords if keywords else "all"},
            "status": "parsed",
        }

    # Generic adjacent check: "scan jobs" or "find jobs"
    if "scan jobs" in command or "find jobs" in command:
        return {"action": "scan_jobs", "endpoint": "POST /api/v1/jobs/search", "status": "triggered"}

    # "how many jobs found" or "job stats"
    if ("how many" in command and "jobs" in command) or "job stats" in command or "application stats" in command:
        return {"action": "get_stats", "endpoint": "GET /api/v1/dashboard/stats", "status": "triggered"}

    # Match command: "match jobs to my resume" or "match job" or "score jobs"
    if ("match" in command and "jobs" in command) or "score jobs" in command or "evaluate jobs" in command:
        return {"action": "batch_match", "endpoint": "POST /api/v1/jobs/batch-match", "status": "triggered"}

    # Optimize resume: "optimize resume for job 5" or "optimize for job 12"
    opt_match = re.search(r"optimize(?:\s+resume)?(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if opt_match:
        job_id = opt_match.group(1)
        return {
            "action": "optimize_resume",
            "endpoint": f"POST /api/v1/jobs/{job_id}/optimize",
            "payload": {"job_id": job_id},
            "status": "parsed",
        }

    # Cover letter: "write cover letter for job 5" or "cover letter for this" or "generate cover letter"
    cl_match = re.search(r"(?:cover letter|coverletter)(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if cl_match:
        job_id = cl_match.group(1)
        return {
            "action": "cover_letter",
            "endpoint": f"POST /api/v1/jobs/{job_id}/cover-letter",
            "payload": {"job_id": job_id},
            "status": "parsed",
        }
    if "cover letter" in command or "write a letter" in command:
        return {"action": "cover_letter", "endpoint": "POST /api/v1/jobs/{id}/cover-letter", "status": "needs_job_id"}

    # Cold email: "send cold email for job 5" or "email hiring manager"
    ce_match = re.search(r"(?:cold mail|cold email|email)(?:\s+for)?(?:\s+job)?\s+(\d+)", command)
    if ce_match:
        job_id = ce_match.group(1)
        return {
            "action": "cold_mail",
            "endpoint": f"POST /api/v1/jobs/{job_id}/cold-mail",
            "payload": {"job_id": job_id},
            "status": "parsed",
        }
    if "cold mail" in command or "cold email" in command or "send email" in command or "email about" in command:
        return {"action": "cold_mail", "endpoint": "POST /api/v1/jobs/{id}/cold-mail", "status": "needs_job_id"}

    # Apply: "apply to job 5" or "apply for this" or "submit application"
    apply_match = re.search(r"apply(?:\s+to|\s+for)?(?:\s+job)?\s+(\d+)", command)
    if apply_match:
        job_id = apply_match.group(1)
        return {
            "action": "apply",
            "endpoint": f"POST /api/v1/jobs/{job_id}/apply",
            "payload": {"job_id": job_id},
            "status": "parsed",
        }
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
    if "voice" in command or "listen" in command:
        if "stop" in command:
            return {"action": "voice_stop", "endpoint": "POST /voice/stop", "status": "triggered"}
        return {"action": "voice_start", "endpoint": "POST /voice/start", "status": "triggered"}
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
