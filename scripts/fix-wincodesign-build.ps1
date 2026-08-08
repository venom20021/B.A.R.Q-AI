# fix-wincodesign-build.ps1
# Reusable workaround for electron-builder's winCodeSign extraction failure on
# non-admin Windows: 7-Zip cannot create the 2 macOS symlinks in
# winCodeSign-2.6.0.7z ("Cannot create symbolic link: A required privilege is
# not held by the client").
#
# Fix: a small 7za wrapper (barq-7za-shim.exe) that forwards to the real 7za
# with "-x!darwin/..." excludes, wired in via builder-util's getPath7za()
# (which becomes SZA_PATH for the app-builder Go binary).
#
# PREFERRED ALTERNATIVE (more durable, no shim needed):
#   Enable Windows Developer Mode once (as admin):
#     reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" /t REG_DWORD /f /v AllowDevelopmentWithoutDevLicense /d 1
#   Then 7-Zip can create symlinks and this script becomes unnecessary.
#
# Run after:  npm install  /  machine reboot (Temp cleared) / electron-builder update.
#   powershell -ExecutionPolicy Bypass -File scripts\fix-wincodesign-build.ps1

param([string]$Repo = '')

$ErrorActionPreference = 'Stop'

# --- locate the repo (upward search for electron-builder.yml) ---
if (-not $Repo) {
    $dir = $PSScriptRoot
    while ($dir -and -not (Test-Path (Join-Path $dir 'electron-builder.yml'))) {
        $dir = Split-Path -Parent $dir
    }
    $Repo = $dir
}
if (-not $Repo -or -not (Test-Path (Join-Path $Repo 'electron-builder.yml'))) {
    Write-Error 'Could not locate the BARQ repo (electron-builder.yml not found). Pass -Repo <path> explicitly.'
    exit 1
}

$shimDir   = Join-Path $env:TEMP 'barq-shim'
$shimExe   = Join-Path $shimDir 'barq-7za-shim.exe'
$shimCmd   = Join-Path $shimDir 'barq-7za-shim.cmd'
$real7za   = Join-Path $Repo 'node_modules/7zip-bin/win/x64/7za.exe'
$patchFile = Join-Path $Repo 'node_modules/builder-util/out/7za.js'

Write-Host "repo: $Repo"
Write-Host ("real 7za present: " + (Test-Path $real7za))
if (-not (Test-Path $real7za)) {
    Write-Error 'node_modules/7zip-bin/win/x64/7za.exe not found - run npm install first.'
    exit 1
}

$exclude1 = '-x!darwin/10.12/lib/libcrypto.dylib'
$exclude2 = '-x!darwin/10.12/lib/libssl.dylib'

# --- 1) build the shim (prefer a real exe; fall back to .cmd) ---
if (-not (Test-Path $shimDir)) { New-Item -ItemType Directory -Force -Path $shimDir | Out-Null }
if (Test-Path $shimExe) { Remove-Item $shimExe -Force }
if (Test-Path $shimCmd) { Remove-Item $shimCmd -Force }

$shimPath = $shimExe
$csharp = @"
using System;
using System.Diagnostics;
using System.Text;
class Barq7zaShim {
    static string Q(string a) {
        return "\"" + a.Replace("\"", "\\\"") + "\"";
    }
    static int Main(string[] args) {
        var sb = new StringBuilder();
        foreach (var a in args) { sb.Append(Q(a)); sb.Append(' '); }
        sb.Append(Q(@"$exclude1")); sb.Append(' ');
        sb.Append(Q(@"$exclude2"));
        var psi = new ProcessStartInfo(@"$real7za");
        psi.Arguments = sb.ToString();
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        try {
            var p = Process.Start(psi);
            p.WaitForExit();
            return p.ExitCode;
        } catch (Exception e) {
            Console.Error.WriteLine("barq-7za-shim: " + e.Message);
            return 2;
        }
    }
}
"@

try {
    Add-Type -TypeDefinition $csharp -OutputAssembly $shimExe -OutputType ConsoleApplication -ErrorAction Stop
    Write-Host ("shim exe created: " + (Test-Path $shimExe))
} catch {
    Write-Host ("Add-Type failed (" + $_.Exception.Message + "); using .cmd fallback.")
    @"
@echo off
setlocal
"$real7za" %* "$exclude1" "$exclude2"
exit /b %errorlevel%
"@ | Set-Content -Path $shimCmd -Encoding ASCII
    $shimPath = $shimCmd
    Write-Host ("shim cmd created: " + (Test-Path $shimCmd))
}

# --- 2) patch builder-util getPath7za() to prefer the shim (idempotent) ---
if (-not (Test-Path $patchFile)) {
    Write-Error "patch target not found: $patchFile"
    exit 1
}
$js = Get-Content $patchFile -Raw
$shimForward = $shimPath.Replace('\', '/')
if ($js -notmatch 'BARQ: prefer a local 7za shim') {
    $old = 'async function getPath7za() {'
    $new = @"
async function getPath7za() {
    // BARQ: prefer a local 7za shim that skips the darwin symlinks in winCodeSign
    // (7-Zip can't create them without admin on Windows). Recreate via scripts\fix-wincodesign-build.ps1
    // after npm install / reboot. Alternative: enable Windows Developer Mode.
    const shimPath = "$shimForward";
    if (process.platform === "win32" && fs.existsSync(shimPath)) {
        return shimPath;
    }
"@
    $js = $js.Replace($old, $new)
    Set-Content -Path $patchFile -Value $js -Encoding UTF8
    Write-Host 'patched builder-util/out/7za.js'
} else {
    # update the shim path line if it drifted (e.g. TEMP moved)
    $js = $js -replace 'const shimPath = "[^"]*";', "const shimPath = `"$shimForward`";"
    if ($js -match 'shimPath = "C:/Users') {
        Set-Content -Path $patchFile -Value $js -Encoding UTF8
        Write-Host 'updated shim path in builder-util/out/7za.js'
    } else {
        Write-Host '7za.js already patched (ok)'
    }
}

Write-Host ''
Write-Host 'Done. Now run:  npm run package'
