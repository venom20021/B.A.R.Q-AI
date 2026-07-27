<#
.SYNOPSIS
    Registers BARQ Watchdog as a Windows scheduled task that auto-starts at user login
    and automatically restarts the backend if it crashes.

.DESCRIPTION
    Creates a scheduled task "BARQ Watchdog" that runs the watchdog PowerShell script
    silently when the user logs on. The watchdog:
    - Starts the BARQ Python FastAPI server via start_backend.vbs
    - Monitors http://127.0.0.1:8956/health every 30 seconds
    - Auto-restarts the backend if it fails 3 consecutive checks
    - Logs all events to logs/watchdog.log

    Run this script once (as Administrator or regular user).
    To remove later:
        Unregister-ScheduledTask -TaskName "BARQ Watchdog" -Confirm:$false

    To check watchdog status:
        Get-ScheduledTask -TaskName "BARQ Watchdog" | Get-ScheduledTaskInfo
#>

$taskName = "BARQ Watchdog"
$watchdogPath = Join-Path $PSScriptRoot "watchdog.ps1"

# Resolve to absolute path
$watchdogPath = Resolve-Path $watchdogPath -ErrorAction Stop

Write-Host "=== BARQ Watchdog Auto-Start Registration ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Task Name:   $taskName"
Write-Host "Watchdog:    $watchdogPath"
Write-Host ""

# Check if task already exists
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[INFO] Task '$taskName' already exists. Removing and recreating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Also clean up old "BARQ Backend" task if it exists
$oldTask = Get-ScheduledTask -TaskName "BARQ Backend" -ErrorAction SilentlyContinue
if ($oldTask) {
    Write-Host "[INFO] Removing old 'BARQ Backend' task (replaced by watchdog)..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName "BARQ Backend" -Confirm:$false
}

# Define the task action: run the watchdog PowerShell script
# Using -WindowStyle Hidden to avoid a console window
$action = New-ScheduledTaskAction `
    -Execute "PowerShell.exe" `
    -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdogPath`""

# Trigger: at user logon (not at system boot - we want it per-user)
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Settings:
# - Allow task to restart on failure (3 times, every 2 minutes)
# - Don't stop if going on batteries
# - Hidden from task list UI
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -Hidden

# Register the task for the current user
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Limited `
    -Force

Write-Host ""
Write-Host "✅ Task '$taskName' registered successfully!" -ForegroundColor Green
Write-Host ""

# Test by starting the task immediately
Write-Host "[INFO] Starting the watchdog + backend now to verify..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $taskName

# Wait for the backend to boot (can take 20+ seconds for full startup)
Write-Host "[INFO] Waiting 25 seconds for backend startup..." -ForegroundColor Yellow
for ($i = 25; $i -ge 0; $i--) {
    Write-Host "`r[INFO] $i seconds remaining..." -NoNewline
    Start-Sleep -Seconds 1
    if ($i % 5 -eq 0) {
        # Quick health check
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8956/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Host ""
                Write-Host ""
                Write-Host "✅ Backend is running! (HTTP $($response.StatusCode))" -ForegroundColor Green
                Write-Host ""
                Write-Host "--- Summary ---" -ForegroundColor Cyan
                Write-Host "The BARQ watchdog will now auto-start every time you log in." -ForegroundColor Cyan
                Write-Host "It monitors the backend health and restarts it if it crashes." -ForegroundColor Cyan
                Write-Host ""
                Write-Host "Watchdog log: logs\watchdog.log" -ForegroundColor Gray
                Write-Host "Backend log:  logs\barq-backend.log" -ForegroundColor Gray
                Write-Host ""
                Write-Host "To remove auto-start later, run this as Admin:" -ForegroundColor Yellow
                Write-Host "  Unregister-ScheduledTask -TaskName `"$taskName`" -Confirm:`$false" -ForegroundColor Yellow
                Write-Host ""
                exit 0
            }
        } catch {
            # Not ready yet - keep waiting
        }
    }
}

Write-Host ""
Write-Host "[WARN] Backend not yet responding. It may still be loading models." -ForegroundColor Yellow
Write-Host "       Check in a few seconds at http://127.0.0.1:8956/health" -ForegroundColor Yellow
Write-Host ""

Write-Host "--- Summary ---" -ForegroundColor Cyan
Write-Host "The BARQ watchdog will now auto-start every time you log in." -ForegroundColor Cyan
Write-Host "It monitors the backend health and restarts it if it crashes." -ForegroundColor Cyan
Write-Host ""
Write-Host "Watchdog log: logs\watchdog.log" -ForegroundColor Gray
Write-Host "Backend log:  logs\barq-backend.log" -ForegroundColor Gray
Write-Host ""
Write-Host "To remove auto-start later, run this as Admin:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName `"$taskName`" -Confirm:`$false" -ForegroundColor Yellow
Write-Host ""
