@echo off
REM ─── BARQ - Windows Startup Script ───────────────────────────────────────
REM Starts both the Python backend and Electron app.
REM Equivalent to: python scripts/dev.py (for Unix)
REM
REM Usage:
REM   Double-click or run: start.bat
REM   Or from Command Prompt: start.bat
REM ──────────────────────────────────────────────────────────────────────────

echo ================================================
echo   BARQ - Development Mode (Windows)
echo ================================================
echo.

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Check for Node.js
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js not found. Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

echo [1/2] Starting Python sidecar on port 8956...
start "BARQ-Python" cmd /c "cd /d %~dp0..\python && python -m uvicorn main:app --host 127.0.0.1 --port 8956 --reload --log-level info"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to start Python server.
    pause
    exit /b 1
)

REM Wait for Python to boot
timeout /t 4 /nobreak >nul

echo [2/2] Starting Electron app...
start "BARQ-Electron" cmd /c "cd /d %~dp0.. && npm run dev"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to start Electron.
    pause
    exit /b 1
)

echo.
echo Both services started!
echo   Electron: http://localhost:5173
echo   Python API: http://127.0.0.1:8956
echo   Python Docs: http://127.0.0.1:8956/docs
echo.
echo Close the terminal windows to stop both services.
echo.

pause
