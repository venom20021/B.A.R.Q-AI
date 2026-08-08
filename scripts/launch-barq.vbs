' ─── BARQ - Silent Desktop Launcher ────────────────────────────────────────
' One-click launcher: starts the BARQ frontend + backend with NO console window.
'
' What it does:
'   - Resolves the project root from this script's location (works no matter
'     where the shortcut lives).
'   - Runs `npm run dev` (electron-vite dev) hidden, logging to logs\barq-dev.log
'   - Electron auto-starts the Python sidecar (uvicorn on 127.0.0.1:8956)
'     through src/main/python-bridge.ts — so backend + frontend both come up.
'
' NOTE: npm/npx.cmd must be on PATH (Node.js installer default). If Electron
'       fails to boot, check logs\barq-dev.log.
' ──────────────────────────────────────────────────────────────────────────

Option Explicit

Dim fso, shell
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' ── Resolve script directory (works regardless of shortcut's CWD) ────────
Dim scriptDir, projectRoot
scriptDir = fso.GetFile(WScript.ScriptFullName).ParentFolder.Path
projectRoot = fso.GetParentFolderName(scriptDir)   ' ...\BARQ

' ── Ensure logs folder exists ─────────────────────────────────────────────
Dim logDir, logFile
logDir = projectRoot & "\logs"
If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)
logFile = logDir & "\barq-dev.log"

' ── Pre-flight checks (fail loudly instead of silently) ───────────────────
If Not fso.FolderExists(projectRoot & "\node_modules") Then
    MsgBox "BARQ dependencies are not installed yet." & vbCrLf & vbCrLf & _
           "Run this once in the project folder (" & projectRoot & "):" & vbCrLf & _
           "    npm install" & vbCrLf & vbCrLf & _
           "Then click the BARQ icon again.", 48, "BARQ"
    WScript.Quit 1
End If

Dim npmCheck
On Error Resume Next
npmCheck = shell.Run("cmd /c npm --version >nul 2>&1", 0, True)
On Error GoTo 0
If npmCheck <> 0 Then
    MsgBox "Node.js / npm was not found on PATH." & vbCrLf & vbCrLf & _
           "Install Node.js 18+ from https://nodejs.org and try again.", 48, "BARQ"
    WScript.Quit 1
End If

' ── Build the dev command ─────────────────────────────────────────────────
' Use cmd.exe so npm.cmd resolves. Redirect all output to the log file so no
' console window ever flashes.
Dim cmd
cmd = "cd /d """ & projectRoot & """ && npm run dev > """ & logFile & """ 2>&1"

' ── Launch hidden (0 = hidden window, False = don't wait) ─────────────────
shell.Run "cmd /c " & cmd, 0, False
