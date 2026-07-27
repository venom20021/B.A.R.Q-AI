@echo off
REM ─── BARQ - Register Windows Auto-Start (Run as Administrator) ───────────
REM Registers a scheduled task that runs the BARQ Watchdog script at user login.
REM The watchdog monitors the Python backend (port 8956) and auto-restarts it
REM if it crashes, including the embedded Telegram ingestion bot.
REM
REM USAGE:
REM   1. Right-click this file → "Run as administrator"
REM   2. OR run from an admin Command Prompt: register_autostart.bat
REM ──────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

echo ================================================
echo   BARQ Watchdog - Auto-Start Registration
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
set "WATCHDOG_PATH=%SCRIPT_DIR%watchdog.ps1"

echo [INFO] Watchdog Script: %WATCHDOG_PATH%
echo.

REM Check the watchdog script exists
if not exist "%WATCHDOG_PATH%" (
    echo [ERROR] watchdog.ps1 not found at %WATCHDOG_PATH%
    pause
    exit /b 1
)

REM Remove old BARQ Backend task if it exists (replaced by watchdog)
schtasks /Query /TN "BARQ Backend" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [INFO] Removing old 'BARQ Backend' task (replaced by watchdog)...
    schtasks /Delete /TN "BARQ Backend" /F >nul 2>&1
)

REM Register the watchdog scheduled task
echo [1/2] Registering scheduled task "BARQ Watchdog"...

schtasks /Create ^
    /TN "BARQ Watchdog" ^
    /TR "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%WATCHDOG_PATH%\"" ^
    /SC ONLOGON ^
    /RL LIMITED ^
    /F ^
    /IT ^
    /DU 24:00 ^
    /K ^
    /Z

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to register scheduled task.
    pause
    exit /b 1
)

REM Configure restart on failure (3 retries at 2-minute intervals)
schtasks /Change ^
    /TN "BARQ Watchdog" ^
    /RI 2 ^
    /RU %USERNAME% >nul 2>&1

echo [OK] Task registered successfully.
echo.

REM Start the task immediately to verify it works
echo [2/2] Starting watchdog to verify...
schtasks /Run /TN "BARQ Watchdog"

REM Wait for the backend to boot (can take 20+ seconds)
echo [INFO] Waiting 25 seconds for backend startup...
echo [INFO] The backend takes time to initialize all services (DB, MemoryBus, etc.)
timeout /t 25 /nobreak >nul

REM Check if the backend is responding
echo.
echo [INFO] Checking backend status...
curl -s http://127.0.0.1:8956/health >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Backend is running on http://127.0.0.1:8956
    echo [OK] Backend health check passed
) else (
    echo [WARN] Backend not yet responding. It may still be loading models.
    echo        Check in a few seconds at http://127.0.0.1:8956/health
)

echo.
echo ============== Registration Complete ==============
echo.
echo The BARQ watchdog will now auto-start every time you log in.
echo It monitors the backend (port 8956) and restarts it if it crashes.
echo.
echo Watchdog log: logs\watchdog.log
echo Backend log:  logs\barq-backend.log
echo.
echo To remove auto-start later, run this command as Admin:
echo   schtasks /Delete /TN "BARQ Watchdog" /F
echo.
pause
