<#
.SYNOPSIS
    Registers BARQ Backend as a Windows scheduled task that auto-starts at user login.
.DESCRIPTION
    Creates a scheduled task "BARQ Backend" that runs start_backend.vbs
    silently when the user logs on. This ensures the Python FastAPI server
    is always available without needing to start it manually.

    Run this script once (as Administrator or regular user).
    To remove later:    Unregister-ScheduledTask -TaskName "BARQ Backend" -Confirm:$false
#>

$taskName = "BARQ Backend"
$scriptPath = Join-Path $PSScriptRoot "start_backend.vbs"

# Resolve to absolute path
$scriptPath = Resolve-Path $scriptPath -ErrorAction Stop

Write-Host "=== BARQ Backend Auto-Start Registration ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Task Name:   $taskName"
Write-Host "Script Path: $scriptPath"
Write-Host ""

# Check if task already exists
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[INFO] Task '$taskName' already exists. Removing and recreating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Define the task action: run wscript.exe with the VBS script
# Using WScript.exe instead of CScript.exe ensures no console window
$action = New-ScheduledTaskAction -Execute "WScript.exe" -Argument "`"$scriptPath`""

# Trigger: at user logon (not at system boot - we want it per-user)
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Settings: allow task to run on demand, stop if running too long? No, keep running.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
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
Write-Host "[INFO] Starting the backend now to verify..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3

# Verify it's running
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8956/voice/status" -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ Backend is running! (HTTP $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Backend not yet responding. It may still be loading models." -ForegroundColor Yellow
    Write-Host "       Check in a few seconds at http://127.0.0.1:8956/voice/status"
}

Write-Host ""
Write-Host "--- Summary ---" -ForegroundColor Cyan
Write-Host "The BARQ backend will now auto-start every time you log in."
Write-Host "To remove auto-start later, run:"
Write-Host "  Unregister-ScheduledTask -TaskName `"$taskName`" -Confirm:`$false"
Write-Host ""
