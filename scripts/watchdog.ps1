<#
.SYNOPSIS
    BARQ Backend Watchdog — Monitors the backend and auto-restarts if down.

.DESCRIPTION
    Periodically checks http://127.0.0.1:8956/health. If the backend
    fails to respond after 3 consecutive retries (each 10s apart),
    the watchdog kills any stuck processes and restarts via start_backend.vbs.

    Designed to be registered as a Windows Scheduled Task that runs
    at user login. The watchdog itself stays alive in the background.

    Logs to: ..\logs\watchdog.log

.PARAMETER IntervalSeconds
    Seconds between health checks (default: 30).

.PARAMETER MaxRetries
    Consecutive failures before restarting (default: 3).

.EXAMPLE
    # Run interactively (foreground)
    .\watchdog.ps1

.EXAMPLE
    # Run silently with custom interval
    powershell -WindowStyle Hidden -File .\watchdog.ps1 -IntervalSeconds 15 -MaxRetries 5
#>

param(
    [int]$IntervalSeconds = 30,
    [int]$MaxRetries = 3
)

# ── Paths ─────────────────────────────────────────────────────────────────

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$pythonDir = Join-Path $projectRoot "python"
$logDir = Join-Path $projectRoot "logs"
$logFile = Join-Path $logDir "watchdog.log"
$vbsLauncher = Join-Path $scriptDir "start_backend.vbs"
$lockFile = Join-Path $logDir "watchdog.lock"

# ── Logging ───────────────────────────────────────────────────────────────

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$timestamp [$Level] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

# ── Singleton Guard ───────────────────────────────────────────────────────

# Check if another watchdog instance is already running
if (Test-Path $lockFile) {
    $lockContent = Get-Content $lockFile -Raw -ErrorAction SilentlyContinue
    if ($lockContent) {
        $oldPid = $lockContent.Trim()
        $oldProcess = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($oldProcess -and $oldProcess.ProcessName -match "powershell") {
            Write-Log "Watchdog already running (PID: $oldPid). Exiting." "WARN"
            exit 0
        }
    }
}

# Write our PID to the lock file
$pid.ToString() | Out-File -FilePath $lockFile -Force

# Ensure lock file is cleaned up on exit
# NOTE: Use script-scoped variable (not $using:) for PowerShell 5.1 compatibility
$script:lockFilePath = $lockFile
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    if (Test-Path $script:lockFilePath) {
        Remove-Item $script:lockFilePath -Force -ErrorAction SilentlyContinue
    }
} | Out-Null

# ── Helpers ───────────────────────────────────────────────────────────────

$healthUrl = "http://127.0.0.1:8956/health"
$consecutiveFailures = 0
$totalRestarts = 0
$watchdogStart = Get-Date

function Test-BackendHealth {
    <#
    .SYNOPSIS
        Check if the backend is alive via the health endpoint.
        Returns $true if healthy, $false otherwise.
    #>
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

function Get-BackendProcess {
    <#
    .SYNOPSIS
        Find any running Python processes related to the backend (uvicorn).
        Returns a list of process objects.
    #>
    $processes = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "uvicorn" -or $_.CommandLine -match "main:app"
    }
    return $processes
}

function Restart-Backend {
    <#
    .SYNOPSIS
        Force-kill any stale backend processes and restart via VBS launcher.
    #>

    # 1. Kill existing backend processes
    $processes = Get-BackendProcess
    foreach ($proc in $processes) {
        Write-Log "Killing stale backend PID $($proc.Id)..." "WARN"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }

    # 2. Also kill any pythonw.exe processes that might be orphaned
    # Scope to only BARQ-related pythonw processes (by command line matching project root)
    $orphans = Get-Process -Name "pythonw" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match [regex]::Escape($projectRoot)
    }
    foreach ($proc in $orphans) {
        Write-Log "Killing orphaned pythonw PID $($proc.Id)..." "WARN"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 2

    # 3. Restart: launch uvicorn directly (reliable from PowerShell jobs)
    # NOTE: Not using start_backend.vbs because WScript COM doesn't work
    # reliably from within PowerShell background jobs.
    Write-Log "Starting backend via direct uvicorn launch..." "INFO"
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "python.exe"
    $startInfo.Arguments = "-m uvicorn main:app --host 127.0.0.1 --port 8956 --log-level warning"
    $startInfo.WorkingDirectory = $pythonDir
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    # DO NOT redirect stdout/stderr — the pipe buffer would fill up and block
    # uvicorn from writing output, effectively hanging the backend.
    # Let uvicorn write to its own stdout/stderr (discarded by the hidden window).
    $startInfo.UseShellExecute = $true
    try {
        $proc = [System.Diagnostics.Process]::Start($startInfo)
        Write-Log "Backend started (PID: $($proc.Id))" "INFO"
    } catch {
        Write-Log "Direct launch failed: $($_.Exception.Message)" "ERROR"
        # Last resort: try via cmd /c start /B
        Write-Log "Trying cmd /c fallback..." "WARN"
        $fallback = Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c start /B python -m uvicorn main:app --host 127.0.0.1 --port 8956 --log-level warning" `
            -WorkingDirectory $pythonDir `
            -WindowStyle Hidden `
            -PassThru
        Write-Log "Fallback started (PID: $($fallback.Id))" "INFO"
    }
    $totalRestarts++
    Write-Log "Restart #$totalRestarts initiated." "INFO"

    # 4. Reset failure counter
    $consecutiveFailures = 0
}

# ── Main Loop ─────────────────────────────────────────────────────────────

Write-Log "=== BARQ Watchdog Started ===" "INFO"
Write-Log "PID: $pid"
Write-Log "Health URL: $healthUrl"
Write-Log "Interval: ${IntervalSeconds}s, Max Retries: $MaxRetries"
Write-Log "Log file: $logFile"
Write-Log "VBS launcher: $vbsLauncher"
Write-Log "Python dir: $pythonDir"
Write-Log ""

while ($true) {
    $isHealthy = Test-BackendHealth

    if ($isHealthy) {
        if ($consecutiveFailures -gt 0) {
            Write-Log "Backend recovered after $consecutiveFailures failure(s)." "OK"
        }
        $consecutiveFailures = 0
    } else {
        $consecutiveFailures++
        $uptime = (Get-Date) - $watchdogStart
        Write-Log "Health check FAILED ($consecutiveFailures/$MaxRetries). Uptime: $([int]$uptime.TotalMinutes)m" "WARN"

        if ($consecutiveFailures -ge $MaxRetries) {
            Write-Log "Max retries reached. Restarting backend..." "ERROR"
            Restart-Backend

            # Wait for backend to come up after restart
            Write-Log "Waiting 15 seconds for backend to start..." "INFO"
            Start-Sleep -Seconds 15
        }
    }

    Start-Sleep -Seconds $IntervalSeconds
}
