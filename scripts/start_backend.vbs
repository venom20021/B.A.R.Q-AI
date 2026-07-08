' ─── BARQ - Silent Backend Launcher ───────────────────────────────────────
' Launches the Python FastAPI server without any visible console window.
' Designed to be added to Windows Task Scheduler to run at user login.
'
' Uses pythonw.exe (windowless Python interpreter) to avoid console flashes.
' The script resolves its own location to find the project root reliably,
' regardless of the working directory set by Task Scheduler.
' ──────────────────────────────────────────────────────────────────────────

Dim fso, shell
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' ── Resolve script directory (works regardless of Task Scheduler's CWD) ──
' WScript.ScriptFullName always points to THIS script's absolute path.
scriptDir = fso.GetFile(WScript.ScriptFullName).ParentFolder.Path

' ── Navigate up from scripts\ to project root ────────────────────────────
' Expected: "...\BARQ\scripts\start_backend.vbs"
' We want:  "...\BARQ"
projectRoot = fso.GetParentFolderName(scriptDir)  ' ...\BARQ
' (If scripts is nested deeper, uncomment the line below and adjust depth)
' projectRoot = fso.GetParentFolderName(fso.GetParentFolderName(scriptDir))

pythonDir = projectRoot & "\python"

' ── Find pythonw.exe (windowless Python) ─────────────────────────────────
' Check common locations:
'   1. Virtual environment (venv\Scripts\pythonw.exe)
'   2. Global Python installation (in PATH)
'   3. py launcher fallback (py.exe -3)
Dim pythonwExe
pythonwExe = ""

' Check for venv first (most common dev setup)
Dim venvPath
venvPath = projectRoot & "\python\venv\Scripts\pythonw.exe"
If fso.FileExists(venvPath) Then
    pythonwExe = venvPath
End If

' Check for .venv in project root
If pythonwExe = "" Then
    venvPath = projectRoot & "\.venv\Scripts\pythonw.exe"
    If fso.FileExists(venvPath) Then
        pythonwExe = venvPath
    End If
End If

' Fallback: let shell.Run resolve from PATH silently (no console flash)
If pythonwExe = "" Then
    pythonwExe = "pythonw.exe"
End If
' Note: if pythonw.exe isn't in PATH, shell.Run will fail silently.
' The user can create a symlink or copy pythonw.exe to a PATH location.
' python.exe would flash a console, so we avoid it intentionally.

' ── Build the uvicorn command ────────────────────────────────────────────
Dim cmd
cmd = "cd /d """ & pythonDir & """ && """ & pythonwExe & """ -m uvicorn main:app --host 127.0.0.1 --port 8956 --log-level warning"

' ── Launch silently ──────────────────────────────────────────────────────
' Flags: 0 = hide window (no console), False = don't wait for completion
shell.Run "cmd /c " & cmd, 0, False
