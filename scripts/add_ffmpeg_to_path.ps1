# Add ffmpeg to Windows User PATH permanently
$ffmpegDir = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*ffmpeg*") {
    $newPath = $currentPath + ";" + $ffmpegDir
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Output "ffmpeg added to User PATH: $ffmpegDir"
} else {
    Write-Output "ffmpeg already in User PATH"
}
