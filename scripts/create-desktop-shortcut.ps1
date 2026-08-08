<#
.SYNOPSIS
    Installs a "BARQ" shortcut on the Desktop with the BARQ logo icon.
    Double-clicking it silently starts BARQ (frontend + backend).

.DESCRIPTION
    Creates %USERPROFILE%\Desktop\BARQ.lnk that points to the hidden
    launcher (scripts\launch-barq.vbs) and uses resources\icon.ico as
    its icon. The shortcut target is wscript.exe with the VBS launcher,
    so no console window appears.

    Run it once:
        powershell -ExecutionPolicy Bypass -File scripts\create-desktop-shortcut.ps1

    To remove later, just delete the BARQ.lnk file on your Desktop.
#>

$ErrorActionPreference = "Stop"

# ── Resolve paths ─────────────────────────────────────────────────────────
$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$vbsPath    = Join-Path $scriptDir "launch-barq.vbs"
$iconPath   = Join-Path $projectRoot "resources\icon.ico"
$desktopDir = [Environment]::GetFolderPath("Desktop")
$lnkPath    = Join-Path $desktopDir "BARQ.lnk"

Write-Host "=== BARQ Desktop Shortcut Installer ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Project root : $projectRoot"
Write-Host "Launcher     : $vbsPath"
Write-Host "Icon         : $iconPath"
Write-Host "Shortcut     : $lnkPath"
Write-Host ""

# ── Sanity checks ─────────────────────────────────────────────────────────
if (-not (Test-Path $vbsPath)) {
    Write-Host "[ERROR] launch-barq.vbs not found. Aborting." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $iconPath)) {
    Write-Host "[WARN] resources\icon.ico not found. Run the icon generator first:" -ForegroundColor Yellow
    Write-Host "       python scripts\generate_barq_icon.py"
    Write-Host "       (shortcut will still be created, but with the default icon)"
}

# ── Create the shortcut ───────────────────────────────────────────────────
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($lnkPath)
$shortcut.TargetPath       = "$env:WINDIR\System32\wscript.exe"
$shortcut.Arguments        = "`"$vbsPath`""
$shortcut.IconLocation     = "$iconPath,0"
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description      = "BARQ - Voice-Controlled Desktop Assistant (frontend + backend)"
$shortcut.WindowStyle      = 7   # minimized (hidden anyway via VBS)
$shortcut.Save()

if (Test-Path $lnkPath) {
    Write-Host ""
    Write-Host "[OK] BARQ shortcut created on your Desktop: $lnkPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "Double-click it to start BARQ. Logs go to logs\barq-dev.log" -ForegroundColor Green
    Write-Host ""
    exit 0
}

Write-Host "[ERROR] Failed to create shortcut." -ForegroundColor Red
exit 1
