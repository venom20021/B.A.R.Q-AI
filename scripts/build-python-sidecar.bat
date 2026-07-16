@echo off
REM ─── BARQ - Build Python Sidecar (Windows) ──────────────────────────────
REM
REM Run from the project root:
REM   scripts\build-python-sidecar.bat
REM
REM Bundles python/main.py into python/dist/barq-sidecar/ using PyInstaller.
REM The output is consumed by electron-builder as extraResources.
REM ─────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

echo ================================================
echo   BARQ - Building Python Sidecar
echo ================================================
echo.

REM ─── Find Python ───────────────────────────────────────────────────────
set PYTHON=python
where %PYTHON% >nul 2>nul
if %ERRORLEVEL% neq 0 (
    set PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
    if not exist "!PYTHON!" (
        set PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
        if not exist "!PYTHON!" (
            echo [ERROR] Could not find Python.
            echo   Install Python 3.11+ from https://python.org
            pause
            exit /b 1
        )
    )
)

echo [INFO] Using Python: %PYTHON%
%PYTHON% --version

REM ─── Ensure PyInstaller is installed ───────────────────────────────────
echo.
echo [1/2] Checking PyInstaller...
%PYTHON% -m pip install pyinstaller -q 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)
echo [OK] PyInstaller ready

REM ─── Determine paths ───────────────────────────────────────────────────
set PROJECT_DIR=%~dp0..
set PYTHON_DIR=%PROJECT_DIR%\python

REM ─── Run PyInstaller ───────────────────────────────────────────────────
echo.
echo [2/2] Bundling Python backend...

cd /d "%PYTHON_DIR%"

%PYTHON% -m PyInstaller ^
    --name barq-sidecar ^
    --onedir ^
    --distpath dist ^
    --workpath build ^
    --add-data "models/vosk;models/vosk" ^
    --add-data "models/vosk/README;models/vosk/" ^
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

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

REM ─── Verify output ─────────────────────────────────────────────────────
echo.
if exist "%PYTHON_DIR%\dist\barq-sidecar.exe" (
    for %%f in ("%PYTHON_DIR%\dist\barq-sidecar.exe") do echo [OK] Build complete: %%~nxf (%%~zf bytes)
) else (
    echo [WARN] One-file exe not found, checking directory mode...
    if exist "%PYTHON_DIR%\dist\barq-sidecar" (
        dir /s "%PYTHON_DIR%\dist\barq-sidecar\barq-sidecar.exe" 2>nul >nul
        if !ERRORLEVEL! equ 0 (
            echo [OK] Build complete: barq-sidecar directory created
        ) else (
            echo [ERROR] Expected barq-sidecar.exe not found in dist/
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] No output found in dist/
        pause
        exit /b 1
    )
)

REM Clean up build artifacts
if exist "%PYTHON_DIR%\build" (
    rmdir /s /q "%PYTHON_DIR%\build"
    echo [INFO] Cleaned up build artifacts
)

echo.
echo ================================================
echo   Python sidecar ready at:
echo     %PYTHON_DIR%\dist\barq-sidecar.exe
echo ================================================

pause
