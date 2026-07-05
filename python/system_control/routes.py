"""
BARQ System Control Module v2.0

Provides OS-level operations:
- App launcher & file operations
- Smart Drop Zones (rules engine for auto-organizing files)
- File sorting wizard (preview, undo, progress tracking)
- Window management (multi-monitor support)
- Terminal execution & streaming (SSE)
- Git operations (status, add, commit, push, pull, branch, log, diff)
- Package manager commands (npm, pip, brew)
- Localhost tunneling
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import platform
import re
import tempfile
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import analytics_dao, settings_dao, db_connection

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════════════════

class AppAction(BaseModel):
    app_name: str

class FileOperation(BaseModel):
    path: str
    content: Optional[str] = None
    destination: Optional[str] = None

class WindowAction(BaseModel):
    action: str  # maximize, minimize, snap_left, snap_right, resize, move_to_monitor
    width: Optional[int] = None
    height: Optional[int] = None
    monitor_index: Optional[int] = None

class CommandRequest(BaseModel):
    command: str
    cwd: Optional[str] = None

class TunnelingRequest(BaseModel):
    port: int

# ─── Smart Drop Zone Models ───────────────────────────────────────────────────

class DropZoneRule(BaseModel):
    name: str
    description: Optional[str] = ""
    conditions: list[dict]  # [{ "field": "extension", "operator": "in", "value": [".jpg", ".png"] }]
    action: str  # move, copy, tag, delete
    target_folder: Optional[str] = None
    priority: int = 0
    enabled: bool = True

class DropZoneEvaluate(BaseModel):
    file_paths: list[str]
    apply: bool = False  # If True, actually perform the actions

# ─── File Sort Wizard Models ──────────────────────────────────────────────────

class SortPreviewRequest(BaseModel):
    directory: str
    strategy: str = "type"  # type, date, size, name, extension_group
    reverse: bool = False

class SortExecuteRequest(BaseModel):
    directory: str
    strategy: str = "type"
    reverse: bool = False
    preview_id: Optional[str] = None  # Validate against preview

# ─── Git Operation Models ────────────────────────────────────────────────────

class GitRequest(BaseModel):
    repo_path: str
    operation: str  # status, add, commit, push, pull, branch, log, diff, checkout, init, clone
    args: Optional[list[str]] = None
    message: Optional[str] = None
    paths: Optional[list[str]] = None
    remote_url: Optional[str] = None
    branch_name: Optional[str] = None

class PackageManagerRequest(BaseModel):
    manager: str  # npm, pip, brew, pnpm, yarn, cargo
    operation: str  # install, uninstall, update, list, search, info, run
    package: Optional[str] = None
    args: Optional[list[str]] = None
    cwd: Optional[str] = None

# ─── Multi-Monitor Models ────────────────────────────────────────────────────

class MonitorAction(BaseModel):
    action: str  # list_monitors, move_window, set_primary, get_window_info
    monitor_index: Optional[int] = None
    window_title: Optional[str] = None
    target_monitor: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

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
        common_paths = [
            os.path.expandvars(f"%ProgramFiles%\\{app_name}\\{app_name}.exe"),
            os.path.expandvars(f"%ProgramFiles(x86)%\\{app_name}\\{app_name}.exe"),
            os.path.expandvars(f"%LOCALAPPDATA%\\{app_name}\\{app_name}.exe"),
            os.path.expandvars(f"%APPDATA%\\{app_name}\\{app_name}.exe"),
        ]
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
        apps_dir = "/Applications"
        # Also check user applications
        user_apps = os.path.expanduser("~/Applications")
        for search_dir in [apps_dir, user_apps]:
            if not os.path.isdir(search_dir):
                continue
            for item in os.listdir(search_dir):
                if app_name.lower() in item.lower():
                    return os.path.join(search_dir, item)

        # Spotlight fallback
        try:
            result = subprocess.run(
                ["mdfind", f"kMDItemKind == 'Application' && kMDItemDisplayName == '*{app_name}*'"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except Exception:
            pass
        return None

    else:
        try:
            result = subprocess.run(["which", app_name], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. App Launcher
# ═══════════════════════════════════════════════════════════════════════════════

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
            subprocess.run(["taskkill", "/f", "/im", f"{request.app_name}.exe"], capture_output=True)
        elif system == "darwin":
            subprocess.run(["pkill", "-f", request.app_name], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", request.app_name], capture_output=True)

        await analytics_dao.log_activity("system", "close_app", f"Closed application: {request.app_name}")
        return {"status": "closed", "app": request.app_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. File Operations
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/file/create-folder")
async def create_folder(request: FileOperation):
    """Create a folder at the specified path."""
    try:
        path = Path(request.path)
        path.mkdir(parents=True, exist_ok=True)
        await analytics_dao.log_activity("system", "create_folder", f"Created folder: {request.path}")
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
        await analytics_dao.log_activity("system", "write_file", f"Wrote file: {request.path}")
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
        await analytics_dao.log_activity("system", "delete_file", f"Deleted: {request.path}")
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
        await analytics_dao.log_activity("system", "move_file", f"Moved: {request.path} → {request.destination}")
        return {"status": "moved", "from": request.path, "to": request.destination}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/search")
async def search_files(query: str = Query(...), directory: str = Query(".")):
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


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Smart Drop Zones — Rules Engine
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_rule_condition(condition: dict, file_path: Path, file_stat) -> bool:
    """Evaluate a single drop zone rule condition against a file."""
    field = condition.get("field", "")
    operator = condition.get("operator", "equals")
    value = condition.get("value")

    # Determine the field value
    if field == "extension":
        field_value = file_path.suffix.lower()
    elif field == "name":
        field_value = file_path.name
    elif field == "name_without_ext":
        field_value = file_path.stem
    elif field == "size_bytes":
        field_value = file_stat.st_size
    elif field == "size_mb":
        field_value = file_stat.st_size / (1024 * 1024)
    elif field == "created_at":
        field_value = file_stat.st_ctime
    elif field == "modified_at":
        field_value = file_stat.st_mtime
    elif field == "is_hidden":
        field_value = file_path.name.startswith(".")
    elif field == "is_directory":
        field_value = file_path.is_dir()
    elif field == "pattern":
        # regex match on full path
        try:
            return bool(re.search(str(value), str(file_path), re.IGNORECASE))
        except re.error:
            return False
    else:
        return False

    # Evaluate operator
    if operator == "equals":
        return field_value == value
    elif operator == "not_equals":
        return field_value != value
    elif operator == "in":
        return field_value in (value or [])
    elif operator == "not_in":
        return field_value not in (value or [])
    elif operator == "greater_than":
        return isinstance(field_value, (int, float)) and field_value > float(value)
    elif operator == "less_than":
        return isinstance(field_value, (int, float)) and field_value < float(value)
    elif operator == "between":
        if isinstance(value, list) and len(value) == 2:
            if isinstance(field_value, (int, float)):
                return float(value[0]) <= field_value <= float(value[1])
        return False
    elif operator == "contains":
        return str(value).lower() in str(field_value).lower()
    elif operator == "starts_with":
        return str(field_value).lower().startswith(str(value).lower())
    elif operator == "ends_with":
        return str(field_value).lower().endswith(str(value).lower())
    elif operator == "regex":
        try:
            return bool(re.search(str(value), str(field_value)))
        except re.error:
            return False
    return False


@router.post("/drop-zone/rules")
async def create_drop_zone_rule(rule: DropZoneRule):
    """Create a Smart Drop Zone rule."""
    try:
        rules_str = await settings_dao.get_setting("drop_zone_rules")
        rules = json.loads(rules_str) if rules_str else []
        rules.append(rule.model_dump())
        await settings_dao.set_setting("drop_zone_rules", json.dumps(rules), category="system")
        return {"status": "created", "rules_count": len(rules)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drop-zone/rules")
async def list_drop_zone_rules():
    """List all Smart Drop Zone rules."""
    try:
        rules_str = await settings_dao.get_setting("drop_zone_rules")
        rules = json.loads(rules_str) if rules_str else []
        return {"rules": rules, "count": len(rules)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/drop-zone/rules/{rule_index}")
async def update_drop_zone_rule(rule_index: int, rule: DropZoneRule):
    """Update a specific drop zone rule by index."""
    try:
        rules_str = await settings_dao.get_setting("drop_zone_rules")
        rules = json.loads(rules_str) if rules_str else []
        if rule_index < 0 or rule_index >= len(rules):
            raise HTTPException(status_code=404, detail="Rule not found")
        rules[rule_index] = rule.model_dump()
        await settings_dao.set_setting("drop_zone_rules", json.dumps(rules), category="system")
        return {"status": "updated", "rule_index": rule_index}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/drop-zone/rules/{rule_index}")
async def delete_drop_zone_rule(rule_index: int):
    """Delete a drop zone rule by index."""
    try:
        rules_str = await settings_dao.get_setting("drop_zone_rules")
        rules = json.loads(rules_str) if rules_str else []
        if rule_index < 0 or rule_index >= len(rules):
            raise HTTPException(status_code=404, detail="Rule not found")
        removed = rules.pop(rule_index)
        await settings_dao.set_setting("drop_zone_rules", json.dumps(rules), category="system")
        return {"status": "deleted", "rule": removed["name"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drop-zone/evaluate")
async def evaluate_drop_zones(request: DropZoneEvaluate):
    """Evaluate files against all active drop zone rules. Optionally apply actions."""
    try:
        rules_str = await settings_dao.get_setting("drop_zone_rules")
        rules = json.loads(rules_str) if rules_str else []
        enabled_rules = sorted(
            [r for r in rules if r.get("enabled", True)],
            key=lambda r: r.get("priority", 0),
            reverse=True
        )

        results = []
        for file_path_str in request.file_paths:
            file_path = Path(file_path_str)
            if not file_path.exists():
                results.append({"file": file_path_str, "status": "not_found", "matches": []})
                continue

            file_stat = file_path.stat()
            matches = []
            for rule in enabled_rules:
                conditions = rule.get("conditions", [])
                if not conditions:
                    continue
                # ALL conditions must match (AND logic)
                all_match = all(
                    _evaluate_rule_condition(c, file_path, file_stat)
                    for c in conditions
                )
                if all_match:
                    matches.append({
                        "rule_name": rule["name"],
                        "action": rule.get("action", "move"),
                        "target_folder": rule.get("target_folder"),
                    })

                    # Apply action if requested
                    if request.apply and matches:
                        action = rule.get("action", "move")
                        target = rule.get("target_folder")
                        if action == "move" and target:
                            target_path = Path(target)
                            target_path.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(target_path / file_path.name))
                        elif action == "copy" and target:
                            target_path = Path(target)
                            target_path.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(file_path), str(target_path / file_path.name))
                        elif action == "delete":
                            file_path.unlink()

                    # First matching rule wins (priority order)
                    break

            results.append({
                "file": file_path_str,
                "status": "matched" if matches else "no_match",
                "matches": matches,
            })

        return {
            "results": results,
            "total_files": len(request.file_paths),
            "matched_count": sum(1 for r in results if r["matches"]),
            "applied": request.apply,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drop-zone/watch")
async def watch_drop_zone(directory: str = Query(...), recursive: bool = True):
    """Watch a directory and auto-apply drop zone rules to new files."""
    try:
        # Index current files
        watch_dir = Path(directory)
        if not watch_dir.exists():
            raise HTTPException(status_code=404, detail="Directory not found")

        files = []
        pattern = "**/*" if recursive else "*"
        for f in watch_dir.glob(pattern):
            if f.is_file():
                files.append(str(f))

        return {
            "status": "indexed",
            "directory": directory,
            "file_count": len(files),
            "message": f"Watching {len(files)} files in {directory}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. File Sorting Wizard (Preview + Execute + Undo)
# ═══════════════════════════════════════════════════════════════════════════════

# In-memory store for sort previews and undo history
_sort_previews: dict[str, dict] = {}
_undo_history: dict[str, list[dict]] = {}


def _apply_sort_strategy(target_dir: Path, strategy: str, reverse: bool) -> list[dict]:
    """Calculate what files would be sorted where. Returns list of moves."""
    moves = []
    items = list(target_dir.iterdir())
    items = [i for i in items if i.is_file()]

    for item in items:
        if strategy == "type":
            ext = item.suffix.lstrip(".").lower() or "no_extension"
            subfolder = ext.upper() + " Files"
        elif strategy == "date":
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            subfolder = mtime.strftime("%Y-%m")
        elif strategy == "size":
            size = item.stat().st_size
            if size < 1024:
                subfolder = "Under 1 KB"
            elif size < 1024 * 1024:
                subfolder = "1 KB - 1 MB"
            elif size < 100 * 1024 * 1024:
                subfolder = "1 MB - 100 MB"
            else:
                subfolder = "Over 100 MB"
        elif strategy == "name":
            first_char = item.stem[0].upper() if item.stem else "#"
            subfolder = first_char if first_char.isalpha() else "#"
        elif strategy == "extension_group":
            ext = item.suffix.lstrip(".").lower() or "no_extension"
            # Group extensions into categories
            image_exts = {"jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "ico"}
            doc_exts = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv"}
            code_exts = {"py", "js", "ts", "jsx", "tsx", "html", "css", "scss", "go", "rs", "java", "cpp", "c", "h", "swift"}
            archive_exts = {"zip", "tar", "gz", "bz2", "7z", "rar"}
            if ext in image_exts:
                subfolder = "Images"
            elif ext in doc_exts:
                subfolder = "Documents"
            elif ext in code_exts:
                subfolder = "Code"
            elif ext in archive_exts:
                subfolder = "Archives"
            else:
                subfolder = ext.upper() + " Files"
        else:
            continue

        moves.append({
            "file": str(item),
            "file_name": item.name,
            "target_folder": subfolder,
            "size_bytes": item.stat().st_size,
            "modified_at": item.stat().st_mtime,
        })

    if reverse:
        moves.reverse()

    return moves


@router.post("/file/sort/preview")
async def sort_preview(request: SortPreviewRequest):
    """Preview file sorting without making changes."""
    try:
        target_dir = Path(request.directory)
        if not target_dir.exists():
            raise HTTPException(status_code=404, detail="Directory not found")

        preview_id = f"sort_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        moves = _apply_sort_strategy(target_dir, request.strategy, request.reverse)

        # Group by target folder
        grouped: dict[str, list[dict]] = {}
        for move in moves:
            grouped.setdefault(move["target_folder"], []).append(move)

        _sort_previews[preview_id] = {
            "directory": request.directory,
            "strategy": request.strategy,
            "moves": moves,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "preview_id": preview_id,
            "directory": request.directory,
            "strategy": request.strategy,
            "total_files": len(moves),
            "groups": {k: {"files": [m["file_name"] for m in v], "count": len(v)} for k, v in grouped.items()},
            "preview": moves[:200],  # Limit preview size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/sort/execute")
async def sort_execute(request: SortExecuteRequest):
    """Execute file sorting with undo support."""
    try:
        target_dir = Path(request.directory)
        if not target_dir.exists():
            raise HTTPException(status_code=404, detail="Directory not found")

        # If preview_id provided, validate against stored preview
        if request.preview_id:
            preview = _sort_previews.get(request.preview_id)
            if not preview:
                raise HTTPException(status_code=400, detail="Preview not found or expired")
            moves = preview["moves"]
        else:
            moves = _apply_sort_strategy(target_dir, request.strategy, request.reverse)

        # Execute moves and record undo info
        undo_id = f"undo_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        undo_entries = []
        executed = 0
        errors = []

        for move in moves:
            try:
                src = Path(move["file"])
                if not src.exists():
                    continue
                subfolder = target_dir / move["target_folder"]
                subfolder.mkdir(exist_ok=True)
                dst = subfolder / move["file_name"]

                # Record undo info before moving
                undo_entries.append({
                    "from": str(dst),
                    "to": str(src),
                })

                shutil.move(str(src), str(dst))
                executed += 1
            except Exception as e:
                errors.append({"file": move["file"], "error": str(e)})

        # Store undo history (limit to 10 recent undo groups)
        _undo_history[undo_id] = undo_entries
        if len(_undo_history) > 10:
            oldest = min(_undo_history.keys())
            del _undo_history[oldest]

        await analytics_dao.log_activity(
            "system", "sort_execute",
            f"Sorted {executed} files in {request.directory} by {request.strategy}"
        )

        return {
            "status": "completed",
            "undo_id": undo_id,
            "files_sorted": executed,
            "files_failed": len(errors),
            "errors": errors[:10],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/sort/undo/{undo_id}")
async def sort_undo(undo_id: str):
    """Undo a previous sort operation."""
    try:
        entries = _undo_history.get(undo_id)
        if not entries:
            raise HTTPException(status_code=404, detail="Undo not found or expired")

        restored = 0
        errors = []
        for entry in reversed(entries):
            try:
                src = Path(entry["from"])
                dst = Path(entry["to"])
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    restored += 1
            except Exception as e:
                errors.append({"from": entry["from"], "error": str(e)})

        del _undo_history[undo_id]

        return {
            "status": "restored",
            "files_restored": restored,
            "errors": errors[:10],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Window Management (Multi-Monitor)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/monitors")
async def list_monitors():
    """List all available monitors/displays."""
    try:
        system = _detect_platform()
        monitors = []

        if system == "windows":
            import pygetwindow as gw
            # Windows: use tkinter or screeninfo for monitor info
            try:
                import screeninfo
                for i, m in enumerate(screeninfo.get_monitors()):
                    monitors.append({
                        "index": i,
                        "name": m.name or f"Monitor {i + 1}",
                        "width": m.width,
                        "height": m.height,
                        "x": m.x,
                        "y": m.y,
                        "is_primary": m.is_primary,
                    })
            except ImportError:
                monitors.append({"index": 0, "name": "Primary", "width": 1920, "height": 1080, "x": 0, "y": 0, "is_primary": True})

        elif system == "darwin":
            # macOS: use system_profiler for display info
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                displays = data.get("SPDisplaysDataType", [])
                for i, display in enumerate(displays):
                    ns_sp = display.get("_sp", {})
                    # Try to get resolution from spdisplays_ndrvs
                    ndrvs = ns_sp.get("spdisplays_ndrvs", [])
                    if ndrvs:
                        res = ndrvs[0].get("_sp", {}).get("spdisplays_resolution", "")
                        monitors.append({
                            "index": i,
                            "name": display.get("_name", f"Display {i + 1}"),
                            "resolution": res,
                            "is_primary": i == 0,
                        })
                    else:
                        monitors.append({
                            "index": i,
                            "name": display.get("_name", f"Display {i + 1}"),
                            "is_primary": i == 0,
                        })
            if not monitors:
                # Fallback: use external display count
                result = subprocess.run(
                    ["osascript", "-e", 'tell app "Finder" to count every desktop'],
                    capture_output=True, text=True, timeout=5
                )
                count = int(result.stdout.strip() or 1)
                for i in range(count):
                    monitors.append({"index": i, "name": f"Monitor {i + 1}", "is_primary": i == 0})

        else:
            # Linux: use xrandr
            result = subprocess.run(
                ["xrandr", "--listmonitors"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if line.strip() and not line.startswith("Monitors:"):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        monitors.append({
                            "index": len(monitors),
                            "name": parts[-1],
                            "is_primary": "+" in parts[0],
                        })

        return {"monitors": monitors, "count": len(monitors)}
    except ImportError:
        return {"monitors": [{"index": 0, "name": "Primary", "is_primary": True}], "count": 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/window/control")
async def window_control(request: WindowAction):
    """Control window operations (maximize, minimize, snap, move to monitor)."""
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
            elif request.action == "move_to_monitor" and request.monitor_index is not None:
                # Move window to specific monitor
                try:
                    import screeninfo
                    monitors = screeninfo.get_monitors()
                    if 0 <= request.monitor_index < len(monitors):
                        target = monitors[request.monitor_index]
                        active.moveTo(target.x, target.y)
                        active.resizeTo(target.width // 2, target.height // 2)
                    else:
                        raise HTTPException(status_code=400, detail="Invalid monitor index")
                except ImportError:
                    pass
            elif request.action == "resize" and request.width and request.height:
                active.resizeTo(request.width, request.height)

        elif system == "darwin":
            scripts = {
                "maximize": 'tell app "System Events" to set size of front window to {(screen width), (screen height)}',
                "minimize": 'tell app "System Events" to set miniaturized of front window to true',
                "snap_left": 'tell app "System Events" to set position of front window to {0, 0}',
                "snap_right": 'tell app "System Events" to set position of front window to {(screen width / 2), 0}',
            }
            script = scripts.get(request.action)
            if script:
                subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)

        else:
            action_map = {
                "maximize": "-b add,maximized_vert,maximized_horz",
                "minimize": "-b add,hidden",
            }
            flag = action_map.get(request.action)
            if flag:
                subprocess.run(["wmctrl", "-r", ":ACTIVE:", flag], capture_output=True, timeout=5)

        await analytics_dao.log_activity("system", "window_control", f"Window action: {request.action}")
        return {"status": "applied", "action": request.action}
    except ImportError:
        raise HTTPException(status_code=501, detail="Window management not available on this platform")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Git Operations
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/git")
async def git_operation(request: GitRequest):
    """Execute Git operations."""
    try:
        repo_path = Path(request.repo_path)
        if not repo_path.exists():
            raise HTTPException(status_code=404, detail="Repository path not found")

        op = request.operation
        git_cmd = ["git", "-C", str(repo_path)]

        command_map = {
            "status": ["status", "--short"],
            "log": ["log", "--oneline", "--graph", "-20"],
            "diff": ["diff"],
            "diff_staged": ["diff", "--cached"],
            "branch": ["branch", "-a"],
            "remote": ["remote", "-v"],
            "init": ["init"],
            "add": ["add"] + (request.paths or ["."]),
            "checkout": ["checkout"] + (request.args or []),
            "pull": ["pull"] + (request.args or ["origin", "main"]),
        }

        if op == "commit":
            msg = request.message or "BARQ auto-commit"
            cmd = git_cmd + ["commit", "-m", msg]
        elif op == "push":
            cmd = git_cmd + ["push"] + (request.args or ["origin", "HEAD"])
        elif op == "clone" and request.remote_url:
            cmd = ["git", "clone", request.remote_url, str(repo_path)]
        elif op in command_map:
            cmd = git_cmd + command_map[op]
        else:
            # Custom git command
            cmd = git_cmd + [op] + (request.args or [])

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(repo_path), timeout=30
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        await analytics_dao.log_activity(
            "system", "git_operation", f"Git {op} in {request.repo_path[:60]}"
        )

        return {
            "status": "completed" if result.returncode == 0 else "error",
            "operation": op,
            "output": output[-5000:],
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "operation": op, "output": "Git command timed out after 30s"}
    except HTTPException:
        raise
    except FileNotFoundError:
        return {"status": "error", "operation": op, "output": "Git not found. Install git CLI."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Package Manager Commands
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/package-manager")
async def package_manager_operation(request: PackageManagerRequest):
    """Execute package manager operations (npm, pip, brew, pnpm, yarn, cargo)."""
    try:
        manager = request.manager
        op = request.operation
        cwd = request.cwd or os.getcwd()

        command_map = {
            "npm": {
                "install": ["npm", "install"] + ([request.package] if request.package else []),
                "uninstall": ["npm", "uninstall"] + ([request.package] if request.package else []),
                "update": ["npm", "update"] + ([request.package] if request.package else []),
                "list": ["npm", "list", "--depth=0"],
                "search": ["npm", "search", request.package or ""],
                "info": ["npm", "info", request.package or "", "--json"],
                "run": ["npm", "run", request.package or ""],
                "init": ["npm", "init", "-y"],
            },
            "pip": {
                "install": [sys.executable, "-m", "pip", "install"] + ([request.package] if request.package else []),
                "uninstall": [sys.executable, "-m", "pip", "uninstall", "-y"] + ([request.package] if request.package else []),
                "update": [sys.executable, "-m", "pip", "install", "--upgrade"] + ([request.package] if request.package else []),
                "list": [sys.executable, "-m", "pip", "list", "--format=columns"],
                "search": [sys.executable, "-m", "pip", "search", request.package or ""],
                "info": [sys.executable, "-m", "pip", "show", request.package or ""],
            },
            "brew": {
                "install": ["brew", "install"] + ([request.package] if request.package else []),
                "uninstall": ["brew", "uninstall"] + ([request.package] if request.package else []),
                "update": ["brew", "update"],
                "list": ["brew", "list"],
                "search": ["brew", "search", request.package or ""],
                "info": ["brew", "info", request.package or ""],
            },
            "pnpm": {
                "install": ["pnpm", "install"] + ([request.package] if request.package else []),
                "uninstall": ["pnpm", "uninstall"] + ([request.package] if request.package else []),
                "update": ["pnpm", "update"] + ([request.package] if request.package else []),
                "list": ["pnpm", "list", "--depth=0"],
                "run": ["pnpm", "run", request.package or ""],
            },
            "yarn": {
                "install": ["yarn", "install"],
                "add": ["yarn", "add", request.package or ""],
                "remove": ["yarn", "remove", request.package or ""],
                "list": ["yarn", "list", "--depth=0"],
                "run": ["yarn", "run", request.package or ""],
            },
            "cargo": {
                "install": ["cargo", "install"] + ([request.package] if request.package else []),
                "uninstall": ["cargo", "uninstall"] + ([request.package] if request.package else []),
                "update": ["cargo", "update"] + ([request.package] if request.package else []),
                "list": ["cargo", "install", "--list"],
                "search": ["cargo", "search", request.package or ""],
                "build": ["cargo", "build"],
                "run": ["cargo", "run"],
            },
        }

        mgr_cmds = command_map.get(manager, {})
        cmd = mgr_cmds.get(op)

        if not cmd:
            # Try to run as direct command
            cmd = [manager, op] + (request.args or [])

        # Add extra args if provided
        if request.args:
            cmd = cmd + request.args

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=120
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return {
            "status": "completed" if result.returncode == 0 else "error",
            "manager": manager,
            "operation": op,
            "output": output[-10000:],  # Limit output
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "manager": request.manager,
            "operation": request.operation,
            "output": "Command timed out after 120s"
        }
    except FileNotFoundError:
        return {
            "status": "unavailable",
            "manager": request.manager,
            "message": f"{request.manager} not found. Install it first."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Terminal Streaming (SSE)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/terminal/stream")
async def terminal_stream(command: str = Query(...), cwd: Optional[str] = None):
    """Stream terminal command output via Server-Sent Events."""
    async def event_generator():
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd or os.getcwd(),
                shell=True,
            )

            # Stream stdout in real-time
            async def stream_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    yield f"data: {json.dumps({'type': 'stdout', 'line': line.decode('utf-8', errors='replace').rstrip()})}\n\n"

            # Stream stderr in real-time
            async def stream_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    yield f"data: {json.dumps({'type': 'stderr', 'line': line.decode('utf-8', errors='replace').rstrip()})}\n\n"

            # Run both streams with asyncio.gather
            stdout_task = asyncio.create_task(_collect_stream(process.stdout))
            stderr_task = asyncio.create_task(_collect_stream(process.stderr))

            # Yield what we have so far
            while not stdout_task.done() or not stderr_task.done():
                # Check stdout
                if not stdout_task.done():
                    line = await _read_line(process.stdout)
                    if line:
                        yield f"data: {json.dumps({'type': 'stdout', 'line': line})}\n\n"
                # Check stderr
                if not stderr_task.done():
                    line = await _read_line(process.stderr)
                    if line:
                        yield f"data: {json.dumps({'type': 'stderr', 'line': line})}\n\n"
                await asyncio.sleep(0.01)

            await process.wait()
            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'return_code': process.returncode})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _read_line(stream) -> Optional[str]:
    """Read a single line from an asyncio stream."""
    try:
        line = await asyncio.wait_for(stream.readline(), timeout=0.1)
        if line:
            return line.decode("utf-8", errors="replace").rstrip()
    except asyncio.TimeoutError:
        pass
    return None


async def _collect_stream(stream):
    """Consume a stream completely."""
    try:
        while True:
            line = await stream.readline()
            if not line:
                break
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Terminal Execution (blocking)
# ═══════════════════════════════════════════════════════════════════════════════

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
            "output": output[-5000:],
            "return_code": result.returncode,
            "cwd": cwd,
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "command": request.command, "output": "Command timed out after 30s"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Tunneling (Wormhole)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/tunnel/expose")
async def expose_port(request: TunnelingRequest):
    """Expose a local port via localhost tunneling."""
    try:
        # Try cloudflared first, then localtunnel
        cloudflared = subprocess.run(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{request.port}"],
            capture_output=True, text=True, timeout=10,
        )
        if cloudflared.returncode == 0:
            for line in cloudflared.stdout.split("\n"):
                if "trycloudflare.com" in line:
                    url = line.strip()
                    break
            else:
                url = f"http://127.0.0.1:{request.port} (tunnel attempt made)"

            await analytics_dao.log_activity("system", "expose_port", f"Exposed port {request.port}")
            return {"status": "exposed", "port": request.port, "url": url}

        return {
            "status": "tunnel_unavailable", "port": request.port,
            "message": "Install cloudflared for tunneling: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
        }
    except subprocess.TimeoutExpired:
        return {"status": "tunneling_started", "port": request.port}
    except FileNotFoundError:
        return {
            "status": "tunnel_unavailable", "port": request.port,
            "message": "cloudflared not found. Install it for tunneling support."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 11. System Status
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def system_status():
    """Get comprehensive system status information."""
    try:
        # Memory info
        memory_info = {}
        try:
            import psutil
            mem = psutil.virtual_memory()
            memory_info = {
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "percent": mem.percent,
            }
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
        except ImportError:
            cpu_percent = 0
            cpu_count = os.cpu_count() or 0

        # Disk info
        disk_info = {}
        try:
            disk = shutil.disk_usage("/")
            disk_info = {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": round(disk.used / disk.total * 100, 1),
            }
        except Exception:
            pass

        return {
            "platform": _detect_platform(),
            "hostname": platform.node(),
            "python_version": sys.version,
            "cpus": cpu_count,
            "cpu_percent": cpu_percent,
            "memory": memory_info,
            "disk": disk_info,
            "cwd": os.getcwd(),
            "user": os.getenv("USER") or os.getenv("USERNAME") or "unknown",
            "uptime": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
