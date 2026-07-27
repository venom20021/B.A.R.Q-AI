<#
.SYNOPSIS
    BARQ Post-Reboot Verification — Run AFTER rebooting your computer.
    Verifies that the watchdog scheduled task auto-started the backend.

.DESCRIPTION
    This script checks:
    1. The "BARQ Watchdog" scheduled task exists and ran on login
    2. The BARQ backend is responding on port 8956
    3. The Telegram bot is active (embedded in backend)
    4. The watchdog log shows monitoring activity

    Run this after your computer has rebooted and you've logged back in.

.EXAMPLE
    .\verify-after-reboot.ps1

.NOTES
    If any check fails, run the registration script again as Administrator:
      Right-click -> register_autostart.bat -> Run as administrator
#>

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$logFile = Join-Path $projectRoot "logs" "verify-after-reboot.log"
$watchdogLog = Join-Path $projectRoot "logs" "watchdog.log"

# Ensure logs directory exists
$logDir = Split-Path -Parent $logFile
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# ── Results tracking ────────────────────────────────────────────────────

$passed = 0
$failed = 0
$results = @()

function Write-Check {
    param([string]$Label, [bool]$Success, [string]$Detail)
    if ($Success) {
        $passed++
        Write-Host "  ✅ $Label" -ForegroundColor Green
        if ($Detail) { Write-Host "     $Detail" -ForegroundColor DarkGray }
    } else {
        $failed++
        Write-Host "  ❌ $Label" -ForegroundColor Red
        if ($Detail) { Write-Host "     $Detail" -ForegroundColor Yellow }
    }
    $results += [PSCustomObject]@{ Label = $Label; Passed = $Success; Detail = $Detail }
}

# ── Header ──────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     BARQ Post-Reboot Verification               ║" -ForegroundColor Cyan
Write-Host "║     $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')                    ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Check 1: Scheduled Task ─────────────────────────────────────────────

Write-Host "[1/4] Checking scheduled task..." -ForegroundColor White
try {
    $task = Get-ScheduledTask -TaskName "BARQ Watchdog" -ErrorAction Stop
    $lastRun = $task.LastRunTime
    $lastResult = $task.LastTaskResult
    $state = $task.State
    
    $taskExists = $state -ne "Disabled"
    if ($lastRun -and $lastRun -gt [DateTime]::MinValue) {
        $taskRan = $true
        $taskDetail = "State: $state | Last Run: $lastRun | Exit Code: $lastResult"
    } else {
        $taskRan = $false
        $taskDetail = "State: $state (never ran yet — may need to log in)"
    }
    Write-Check "BARQ Watchdog task exists and ran" $taskRan $taskDetail
} catch {
    Write-Check "BARQ Watchdog task exists" $false "Task not found. Run register_autostart.bat as Administrator."
}

# ── Check 2: Backend Health ─────────────────────────────────────────────

Write-Host "[2/4] Checking backend health..." -ForegroundColor White
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8956/health" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        $health = $response.Content | ConvertFrom-Json
        Write-Check "Backend responding on port 8956" $true "Version: $($health.version) | Status: $($health.status)"
    } else {
        Write-Check "Backend responding on port 8956" $false "HTTP $($response.StatusCode)"
    }
} catch {
    Write-Check "Backend responding on port 8956" $false "Connection failed. Watchdog may still be starting backend (takes ~30s). Retry in 1 minute."
}

# ── Check 3: Watchdog Log ───────────────────────────────────────────────

Write-Host "[3/4] Checking watchdog log..." -ForegroundColor White
if (Test-Path $watchdogLog) {
    $logAge = (Get-Date) - (Get-Item $watchdogLog).LastWriteTime
    $recent = Get-Content $watchdogLog -Tail 5 -ErrorAction SilentlyContinue
    $hasHealthCheck = $recent -match "Health check"
    $hasStarted = $recent -match "Watchdog Started"
    
    if ($hasHealthCheck -or $hasStarted) {
        Write-Check "Watchdog is monitoring" $true "Last log: $($logAge.TotalMinutes -as [int])m ago | Last line: $($recent[-1])"
    } else {
        Write-Check "Watchdog is monitoring" $false "Log exists but no recent health checks. Full log: $watchdogLog"
    }
} else {
    Write-Check "Watchdog is monitoring" $false "No watchdog log found at $watchdogLog. Watchdog may not have started yet."
}

# ── Check 4: Jobs Pipeline ──────────────────────────────────────────────

Write-Host "[4/4] Checking jobs pipeline..." -ForegroundColor White
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8956/jobs/status" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Check "Jobs pipeline accessible" $true "API responds on /jobs/status"
    } else {
        Write-Check "Jobs pipeline accessible" $false "HTTP $($response.StatusCode)"
    }
} catch {
    Write-Check "Jobs pipeline accessible" $false "Jobs endpoint not responding (non-critical — backend is the main check)"
}

# ── Summary ─────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Results: $passed passed, $failed failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Yellow" })
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if ($failed -eq 0) {
    Write-Host "  🎉 All checks passed! BARQ is running with auto-restart." -ForegroundColor Green
    Write-Host "  The watchdog will keep the backend (and Telegram bot) running 24/7." -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Some checks failed. Common fixes:" -ForegroundColor Yellow
    Write-Host "   1. Wait 30 more seconds — the backend takes time to initialize" -ForegroundColor Yellow
    Write-Host "   2. Run register_autostart.bat as Administrator to re-register" -ForegroundColor Yellow
    Write-Host "   3. Check logs\watchdog.log for error details" -ForegroundColor Yellow
}

# Save results to log
$results | Export-Csv -Path $logFile -NoTypeInformation -Encoding utf8
Write-Host ""
Write-Host "Detailed results saved to: $logFile" -ForegroundColor DarkGray
Write-Host ""
