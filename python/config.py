"""
BARQ Configuration - Centralized settings management.
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file from the project root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(env_path)


class Settings(BaseSettings):
    # Sidecar server
    host: str = os.getenv("SIDECAR_HOST", "127.0.0.1")
    port: int = int(os.getenv("SIDECAR_PORT", "8956"))
    debug: bool = os.getenv("BARQ_DEBUG", "false").lower() == "true"

    # Voice
    wake_word: str = "hey barq"
    vosk_model_path: str = os.getenv("VOSK_MODEL_PATH", "models/vosk")
    vosk_hindi_model_path: str = os.getenv("VOSK_HINDI_MODEL_PATH", "models/vosk-hi")
    whisper_model: str = os.getenv("WHISPER_MODEL", "base")
    voice_language: str = os.getenv("VOICE_LANGUAGE", "en")  # "en" or "hi"

    # LLM
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    # Job Search
    job_scan_interval_hours: int = int(os.getenv("JOB_SCAN_INTERVAL_HOURS", "6"))
    match_threshold: float = float(os.getenv("MATCH_THRESHOLD", "0.7"))

    # Social Media
    trend_check_interval_hours: int = int(os.getenv("TREND_CHECK_INTERVAL_HOURS", "6"))

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), 'barq.db')}",
    )

    # Notifications
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # SMTP / Email
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")
    notification_email: str = os.getenv("NOTIFICATION_EMAIL", "")

    # Career / Jobs
    career_ops_path: str = os.getenv("CAREER_OPS_PATH", os.path.join(os.path.expanduser("~"), "career-ops"))
    resume_path: str = os.getenv("RESUME_PATH", "")
    barq_port: int = int(os.getenv("BARQ_PORT", "8111"))

    # Scheduler
    job_scan_interval_hours: int = int(os.getenv("JOB_SCAN_INTERVAL_HOURS", "6"))
    auto_match_interval_hours: int = int(os.getenv("AUTO_MATCH_INTERVAL_HOURS", "1"))

    # Matching thresholds
    match_threshold_high: float = float(os.getenv("MATCH_THRESHOLD_HIGH", "80"))
    match_threshold_medium: float = float(os.getenv("MATCH_THRESHOLD_MEDIUM", "60"))

    # Email / SMTP
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")
    notification_email: str = os.getenv("NOTIFICATION_EMAIL", "")
    sender_name: str = os.getenv("SENDER_NAME", "")

    # API Authentication
    barq_api_key: str = os.getenv("BARQ_API_KEY", "")

    # External API Keys (loaded from .env)
    linkedin_email: str = os.getenv("LINKEDIN_EMAIL", "")
    linkedin_password: str = os.getenv("LINKEDIN_PASSWORD", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    twitter_api_key: str = os.getenv("TWITTER_API_KEY", "")
    twitter_api_secret: str = os.getenv("TWITTER_API_SECRET", "")

    model_config = {"env_file": env_path, "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
