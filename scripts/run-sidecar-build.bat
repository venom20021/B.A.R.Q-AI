@echo off
REM ─── BARQ - Python Sidecar Build (non-interactive) ─────────────────────
REM Runs PyInstaller on python/main.py producing python/dist/barq-sidecar/
REM Used by `npm run package` via electron-builder extraResources.
REM Launched detached (no pause), output → logs\sidecar-build.log
REM ────────────────────────────────────────────────────────────────────────

setlocal
set "ROOT=%~dp0.."
set "PY=%ROOT%\python"

cd /d "%PY%"

python -m PyInstaller ^
  --name barq-sidecar ^
  --onedir ^
  -y ^
  --distpath "%PY%\dist" ^
  --workpath "%PY%\build" ^
  --add-data "%PY%\models\vosk;models/vosk" ^
  --add-data "%PY%\models\vosk\README;models/vosk/" ^
  --collect-all fastapi ^
  --collect-all uvicorn ^
  --collect-all httpx ^
  --collect-all aiosqlite ^
  --collect-all vosk ^
  --collect-all sounddevice ^
  --collect-all edge_tts ^
  --collect-all faster_whisper ^
  --collect-all yfinance ^
  --collect-all numpy ^
  --collect-all psutil ^
  --collect-all PIL ^
  --collect-all av ^
  --exclude-module matplotlib ^
  --exclude-module scipy ^
  --exclude-module pandas ^
  --exclude-module tkinter ^
  --exclude-module PyQt5 ^
  --exclude-module PySide2 ^
  --exclude-module PySide6 ^
  --exclude-module notebook ^
  --exclude-module IPython ^
  --exclude-module test ^
  --exclude-module unittest ^
  --hidden-import agent.routes ^
  --hidden-import agent.vision_routes ^
  --hidden-import agent.agent_executor ^
  --hidden-import agent.agent_planner ^
  --hidden-import agent.error_handler ^
  --hidden-import agent.skill_registry ^
  --hidden-import agent.task_queue ^
  --hidden-import ai.conversation ^
  --hidden-import ai.responder ^
  --hidden-import analytics.career ^
  --hidden-import analytics.social ^
  --hidden-import api.routes ^
  --hidden-import database.analytics_dao ^
  --hidden-import database.connection ^
  --hidden-import database.jobs_dao ^
  --hidden-import database.schema ^
  --hidden-import database.settings_dao ^
  --hidden-import database.social_dao ^
  --hidden-import desktop_automation.routes ^
  --hidden-import external_apis.clients ^
  --hidden-import external_apis.routes ^
  --hidden-import graph_brain ^
  --hidden-import jobs.applier ^
  --hidden-import jobs.cold_mail ^
  --hidden-import jobs.cover_letter ^
  --hidden-import jobs.evaluator ^
  --hidden-import jobs.matcher ^
  --hidden-import jobs.optimizer ^
  --hidden-import jobs.pdf_generator ^
  --hidden-import jobs.pipeline ^
  --hidden-import jobs.response_tracker ^
  --hidden-import jobs.resume_parser ^
  --hidden-import jobs.scanner ^
  --hidden-import memory_knowledge.routes ^
  --hidden-import notifications.base ^
  --hidden-import notifications.desktop ^
  --hidden-import notifications.email_smtp ^
  --hidden-import notifications.manager ^
  --hidden-import notifications.telegram ^
  --hidden-import social.calendar ^
  --hidden-import social.poster ^
  --hidden-import social.script ^
  --hidden-import social.trends ^
  --hidden-import social.video ^
  --hidden-import system_control.command_whitelist ^
  --hidden-import system_control.routes ^
  --hidden-import utils.callback_guards ^
  --hidden-import utils.ollama_client ^
  --hidden-import voice.action_log ^
  --hidden-import voice.audio_device ^
  --hidden-import voice.conversation_listener ^
  --hidden-import voice.interrupt_handler ^
  --hidden-import voice.pipeline ^
  --hidden-import voice.routes ^
  --hidden-import voice.speech ^
  --hidden-import voice.wake_word ^
  --hidden-import web_media.routes ^
  --log-level WARN ^
  main.py

echo SIDECAR_BUILD_EXIT=%ERRORLEVEL%
