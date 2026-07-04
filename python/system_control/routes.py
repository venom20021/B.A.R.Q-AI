"""
FastAPI routes for system control: app launcher, file operations,
window management, and desktop control.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import platform
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import analytics_dao, settings_dao

router = APIRouter()


# ─── Models ───────────────────────────────────────────────────────────────────

class AppAction(BaseModel):
    app_name: str

class FileOperation(BaseModel):
    path: str
    content: Optional[str] = None
    destination: Optional[str] = None

class WindowAction(BaseModel):
    action: str  # maximize, minimize, snap_left, snap_right, resize
    width: Optional[int] = None
    height: Optional[int] = None

class CommandRequest(BaseModel):
    command: str
    cwd: Optional[str] = None

class MacroRequest(BaseModel):
    name: str
    steps: list[dict]

class TunnelingRequest(BaseModel):
    port: int


# ─── App Launcher ─────────────────────────────────────────────────────────────

def _detect_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "darwin"
    return "linux"

def _find_app_path(app_name: str) -> Optional[str]:
    """Find an application path across platforms."""
    system = _detect_platform()

    if system == "windows":
        # Check common Windows locations
        common_paths = [
            os.path.expandvars(f"%ProgramFiles%\\{app_name}\\{app_name}.exe"),
            os.path.expandvars(f"%ProgramFiles(x86)%\\{app_name}\\{app_name}.exe"),
            os.path.expandvars(f"%LOCALAPPDATA%\\{app_name}\\{app_name}.exe"),
            os.path.expandvars(f"%APPDATA%\\{app_name}\\{app_name}.exe"),
        ]
        # Check Start Menu
        start_menu = os.path.expandvars("%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs")
        for root, _, files in os.walk(start_menu):
            for f in files:
                if app_name.lower() in f.lower() and f.endswith((".lnk", ".exe")):
                    return os.path.join(root, f)

        for path in common_paths:
            if os.path.exists(path):
                return path
        return None

    elif system == "darwin":
        # macOS: check /Applications
        apps_dir = "/Applications"
        for item in os.listdir(apps_dir):
            if app_name.lower() in item.lower():
                return os.path.join(apps_dir, item)
        return None

    else:
        # Linux: check PATH
        try:
            result = subprocess.run(["which", app_name], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        return None


@router.post("/launch-app")
async def launch_app(request: AppAction):
    """Launch an application by name."""
    try:
        system = _detect_platform()
        app_path = _find_app_path(request.app_name)

        if app_path:
            if system == "windows":
                os.startfile(app_path)
            elif system == "darwin":
                subprocess.Popen(["open", app_path])
            else:
                subprocess.Popen([app_path])
        else:
            # Try launching by name directly
            if system == "windows":
                subprocess.Popen(["start", request.app_name], shell=True)
            elif system == "darwin":
                subprocess.Popen(["open", "-a", request.app_name])
            else:
                subprocess.Popen([request.app_name])

        await analytics_dao.log_activity(
            "system", "launch_app", f"Launched application: {request.app_name}"
        )
        return {"status": "launched", "app": request.app_name, "path": app_path}
    except Exception as e:
        await analytics_dao.log_activity(
            "system", "launch_app_error", str(e), severity="error"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close-app")
async def close_app(request: AppAction):
    """Close an application by name."""
    try:
        system = _detect_platform()
        if system == "windows":
            subprocess.run(["taskkill", "/f", "/im", f"{request.app_name}.exe"],
                           capture_output=True)
        elif system == "darwin":
            subprocess.run(["pkill", "-f", request.app_name], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", request.app_name], capture_output=True)

        await analytics_dao.log_activity(
            "system", "close_app", f"Closed application: {request.app_name}"
        )
        return {"status": "closed", "app": request.app_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── File Operations ──────────────────────────────────────────────────────────

@router.post("/file/create-folder")
async def create_folder(request: FileOperation):
    """Create a folder at the specified path."""
    try:
        path = Path(request.path)
        path.mkdir(parents=True, exist_ok=True)
        await analytics_dao.log_activity(
            "system", "create_folder", f"Created folder: {request.path}"
        )
        return {"status": "created", "path": request.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/read")
async def read_file(request: FileOperation):
    """Read file contents."""
    try:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if not path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        content = path.read_text(encoding="utf-8")
        return {
            "status": "ok",
            "path": request.path,
            "content": content,
            "size_bytes": path.stat().st_size,
            "modified_at": path.stat().st_mtime,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/write")
async def write_file(request: FileOperation):
    """Write content to a file."""
    try:
        if request.content is None:
            raise HTTPException(status_code=400, detail="Content is required")

        path = Path(request.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.content, encoding="utf-8")

        await analytics_dao.log_activity(
            "system", "write_file", f"Wrote file: {request.path}"
        )
        return {"status": "written", "path": request.path, "size_bytes": len(request.content)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/delete")
async def delete_file(request: FileOperation):
    """Delete a file or folder."""
    try:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Path not found")

        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

        await analytics_dao.log_activity(
            "system", "delete_file", f"Deleted: {request.path}"
        )
        return {"status": "deleted", "path": request.path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/move")
async def move_file(request: FileOperation):
    """Move or rename a file/folder."""
    try:
        if not request.destination:
            raise HTTPException(status_code=400, detail="Destination is required")

        src = Path(request.path)
        dst = Path(request.destination)

        if not src.exists():
            raise HTTPException(status_code=404, detail="Source not found")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        await analytics_dao.log_activity(
            "system", "move_file", f"Moved: {request.path} → {request.destination}"
        )
        return {"status": "moved", "from": request.path, "to": request.destination}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/search")
async def search_files(query: str, directory: str = "."):
    """Search for files matching a query."""
    try:
        search_dir = Path(directory)
        if not search_dir.exists():
            raise HTTPException(status_code=404, detail="Directory not found")

        results = []
        query_lower = query.lower()

        for path in search_dir.rglob("*"):
            if path.is_file() and query_lower in path.name.lower():
                try:
                    results.append({
                        "name": path.name,
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "modified_at": path.stat().st_mtime,
                    })
                except (PermissionError, OSError):
                    continue

        return {"results": results[:100], "total": len(results), "query": query}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/sort")
async def sort_directory(directory: str, by: str = "type"):
    """Sort files in a directory by type, date, size, or name."""
    try:
        target_dir = Path(directory)
        if not target_dir.exists():
            raise HTTPException(status_code=404, detail="Directory not found")

        organized = 0
        for item in target_dir.iterdir():
            if item.is_file():
                # Determine subfolder by file extension
                ext = item.suffix.lstrip(".").lower() or "no_extension"
                if by == "type":
                    subfolder = target_dir / f"{ext.upper()} Files"
                elif by == "date":
                    import datetime
                    mtime = datetime.datetime.fromtimestamp(item.stat().st_mtime)
                    subfolder = target_dir / mtime.strftime("%Y-%m")
                else:
                    continue

                subfolder.mkdir(exist_ok=True)
                shutil.move(str(item), str(subfolder / item.name))
                organized += 1

        await analytics_dao.log_activity(
            "system", "sort_directory",
            f"Sorted {organized} files in {directory} by {by}"
        )
        return {"status": "sorted", "files_organized": organized, "directory": directory}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Window Management ────────────────────────────────────────────────────────

@router.post("/window/control")
async def window_control(request: WindowAction):
    """Control window operations (maximize, minimize, snap)."""
    try:
        system = _detect_platform()

        if system == "windows":
            import pygetwindow as gw

            active = gw.getActiveWindow()
            if not active:
                return {"status": "no_active_window", "action": request.action}

            if request.action == "maximize":
                active.maximize()
            elif request.action == "minimize":
                active.minimize()
            elif request.action == "snap_left":
                active.resizeTo(active.screen.width // 2, active.screen.height)
                active.moveTo(0, 0)
            elif request.action == "snap_right":
                active.resizeTo(active.screen.width // 2, active.screen.height)
                active.moveTo(active.screen.width // 2, 0)
            elif request.action == "resize" and request.width and request.height:
                active.resizeTo(request.width, request.height)

        elif system == "darwin":
            # macOS uses AppleScript for window management
            script = {
                "maximize": 'tell app "System Events" to set size of front window to {screen width, screen height}',
                "minimize": 'tell app "System Events" to set miniaturized of front window to true',
            }.get(request.action)
            if script:
                subprocess.run(["osascript", "-e", script], capture_output=True)

        else:
            # Linux: use wmctrl
            action_map = {
                "maximize": "-b add,maximized_vert,maximized_horz",
                "minimize": "-b add,hidden",
            }
            flag = action_map.get(request.action)
            if flag:
                subprocess.run(["wmctrl", "-r", ":ACTIVE:", flag], capture_output=True)

        await analytics_dao.log_activity(
            "system", "window_control", f"Window action: {request.action}"
        )
        return {"status": "applied", "action": request.action}
    except ImportError:
        raise HTTPException(status_code=501, detail="Window management not available on this platform")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Terminal Execution ───────────────────────────────────────────────────────

@router.post("/terminal/run")
async def run_command(request: CommandRequest):
    """Execute a terminal command and return output."""
    try:
        cwd = request.cwd or os.getcwd()

        result = subprocess.run(
            request.command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        await analytics_dao.log_activity(
            "system", "run_command", f"Executed: {request.command[:100]}"
        )
        return {
            "status": "completed" if result.returncode == 0 else "error",
            "command": request.command,
            "output": output[-5000:],  # Limit output size
            "return_code": result.returncode,
            "cwd": cwd,
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "command": request.command, "output": "Command timed out after 30s"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Tunneling (Wormhole) ─────────────────────────────────────────────────────

@router.post("/tunnel/expose")
async def expose_port(request: TunnelingRequest):
    """Expose a local port via localhost tunneling."""
    try:
        # Try cloudflared first, then localtunnel
        cloudflared = subprocess.run(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{request.port}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if cloudflared.returncode == 0:
            # Extract URL from output
            for line in cloudflared.stdout.split("\n"):
                if "trycloudflare.com" in line:
                    url = line.strip()
                    break
            else:
                url = f"http://127.0.0.1:{request.port} (tunnel attempt made)"

            await analytics_dao.log_activity(
                "system", "expose_port", f"Exposed port {request.port}"
            )
            return {"status": "exposed", "port": request.port, "url": url}

        return {"status": "tunnel_unavailable", "port": request.port,
                "message": "Install cloudflared for tunneling: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"}
    except subprocess.TimeoutExpired:
        return {"status": "tunneling_started", "port": request.port}
    except FileNotFoundError:
        return {"status": "tunnel_unavailable", "port": request.port,
                "message": "cloudflared not found. Install it for tunneling support."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── System Status ────────────────────────────────────────────────────────────

@router.get("/status")
async def system_status():
    """Get overall system status information."""
    try:
        return {
            "platform": _detect_platform(),
            "hostname": platform.node(),
            "python_version": sys.version,
            "cpus": os.cpu_count(),
            "cwd": os.getcwd(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
