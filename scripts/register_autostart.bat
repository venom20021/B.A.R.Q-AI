@echo off
REM ─── BARQ - Register Windows Auto-Start (Run as Administrator) ───────────
REM Registers a scheduled task that launches the Python backend at user login.
REM
REM USAGE:
REM   1. Right-click this file → "Run as administrator"
REM   2. OR run from an admin Command Prompt: register_autostart.bat
REM ──────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

echo ================================================
echo   BARQ Backend - Auto-Start Registration
echo ================================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] This script must be run as Administrator.
    echo         Right-click this file and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo [INFO] Admin privileges confirmed.
echo.

REM Resolve script directory
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "VBS_PATH=%SCRIPT_DIR%start_backend.vbs"

echo [INFO] VBS Launcher: %VBS_PATH%
echo.

REM Check the VBS exists
if not exist "%VBS_PATH%" (
    echo [ERROR] start_backend.vbs not found at %VBS_PATH%
    pause
    exit /b 1
)

REM Register the scheduled task
echo [1/2] Registering scheduled task "BARQ Backend"...
schtasks /Create ^
    /TN "BARQ Backend" ^
    /TR "wscript.exe \"%VBS_PATH%\"" ^
    /SC ONLOGON ^
    /RL LIMITED ^
    /F ^
    /IT

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to register scheduled task.
    pause
    exit /b 1
)

echo [OK] Task registered successfully.
echo.

REM Start the task immediately to verify it works
echo [2/2] Starting backend to verify...
schtasks /Run /TN "BARQ Backend"

REM Wait a moment for the backend to boot
timeout /t 4 /nobreak >nul

REM Check if the backend is responding
echo.
echo [INFO] Checking backend status...
curl -s http://127.0.0.1:8956/voice/status >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Backend is running on http://127.0.0.1:8956
) else (
    echo [WARN] Backend not yet responding. It may still be loading models.
    echo        Check in a few seconds at http://127.0.0.1:8956/voice/status
)

echo.
echo ============== Registration Complete ==============
echo.
echo The BARQ backend will now auto-start every time you log in.
echo.
echo To remove auto-start later, run this command as Admin:
echo   schtasks /Delete /TN "BARQ Backend" /F
echo.
pause
