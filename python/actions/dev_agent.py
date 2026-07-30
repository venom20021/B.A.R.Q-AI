"""
DevAgent — full-stack project builder for BARQ.

Inspired by Mark-L's dev_agent.py. Builds complete software projects from
a natural language description. Uses a plan → write → run → fix loop.

Flow:
1. LLM plans the project structure (files, dependencies, entry point)
2. Each file is written in dependency order (imports first)
3. Dependencies are installed
4. Project is run and tested
5. Errors are automatically parsed and fixed (up to 5 attempts)

All code generation uses BARQ's OllamaClient.
"""

import asyncio
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from utils.ollama_client import OllamaClient

# ─── Constants ────────────────────────────────────────────────────────────────

PROJECTS_DIR = Path.home() / "Desktop" / "BARQ_Projects"
MAX_FIX_ATTEMPTS = 5
MODEL = "ollama"  # Uses Ollama via OllamaClient


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_llm() -> OllamaClient:
    return OllamaClient()


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def _parse_traceback(output: str, project_files: list[str]) -> tuple[Optional[str], Optional[int]]:
    """Parse a Python traceback to find the error file and line number."""
    pattern = re.compile(r'File [\"\']([^\"\']+\.py)[\"\'],\s+line\s+(\d+)', re.IGNORECASE)
    matches = pattern.findall(output)

    for raw_path, line_str in reversed(matches):
        raw_name = Path(raw_path).name
        for pf in project_files:
            if Path(pf).name == raw_name or pf == raw_path or raw_path.endswith(pf):
                return pf, int(line_str)

    return None, None


def _classify_error(output: str) -> str:
    low = output.lower()
    if any(x in low for x in ("no module named", "modulenotfounderror", "importerror")):
        return "dependency_error"
    if "syntaxerror" in low or "invalid syntax" in low:
        return "syntax_error"
    if "cannot import" in low or "importerror" in low:
        return "import_error"
    if any(x in low for x in (
        "traceback", "exception", "error:", "nameerror", "typeerror",
        "attributeerror", "valueerror", "keyerror", "indexerror",
    )):
        return "runtime_error"
    return "none"


def _has_error(output: str) -> bool:
    low = output.lower()
    if not output.strip():
        return False
    if "timed out" in low:
        return False
    return _classify_error(output) != "none"


# ─── Planning ──────────────────────────────────────────────────────────────────

async def plan_project(description: str, language: str) -> dict:
    """Use LLM to plan a project structure from a description."""
    llm = _get_llm()

    prompt = (
        f"You are a senior software architect. Create a minimal, complete file plan for this project.\n\n"
        f"Language: {language}\n"
        f"Description: {description}\n\n"
        "Return ONLY valid JSON — no markdown, no explanation:\n"
        "{\n"
        '  "project_name": "snake_case_name",\n'
        '  "entry_point": "main.py",\n'
        '  "files": [\n'
        "    {\n"
        '      "path": "main.py",\n'
        '      "description": "Entry point — what it does",\n'
        '      "imports": ["utils.helpers"]\n'
        "    },\n"
        "    {\n"
        '      "path": "utils/helpers.py",\n'
        '      "description": "Helper utilities",\n'
        '      "imports": []\n'
        "    }\n"
        "  ],\n"
        '  "run_command": "python main.py",\n'
        '  "dependencies": ["requests"]\n'
        "}\n\n"
        "Critical rules:\n"
        "1. Files in DEPENDENCY ORDER — no-import files first, entry point last.\n"
        "2. The 'imports' field must list every OTHER project file this file imports (dot-notation).\n"
        "3. Keep it minimal — only files truly needed.\n"
        "4. Entry point must be in the files list.\n"
        "5. Use relative paths only (e.g. 'utils/helpers.py').\n"
        "6. Standard library modules do NOT go in 'dependencies'.\n\nJSON:"
    )

    messages = [
        {"role": "system", "content": "You are a senior software architect. Return ONLY valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.chat(messages)
        raw = _strip_fences(response)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Planner returned invalid JSON: {e}\nRaw: {response[:300]}")
    except Exception as e:
        raise


# ─── File Writer ───────────────────────────────────────────────────────────────

async def _write_project_file(
    file_info: dict,
    project_description: str,
    all_files: list[dict],
    language: str,
    project_dir: Path,
    already_written: dict[str, str],
) -> str:
    """Write a single project file, with context from already-written files."""
    llm = _get_llm()

    file_path = file_info["path"]
    file_desc = file_info.get("description", "")
    file_imports = file_info.get("imports", [])

    file_list = "\n".join(
        f"  [{i+1}] {f['path']}: {f.get('description', '')}"
        for i, f in enumerate(all_files)
    )

    dependency_context = ""
    for dep_dotted in file_imports:
        dep_path = dep_dotted.replace(".", "/") + ".py"
        if dep_path in already_written:
            code_snippet = already_written[dep_path][:2000]
            dependency_context += f"\n\n--- {dep_path} (import this) ---\n{code_snippet}"

    lang_rules = ""
    if language.lower() == "python":
        lang_rules = (
            "Python rules:\n"
            "- Use type hints for all function signatures.\n"
            "- Add docstrings for public functions and classes.\n"
            "- Use if __name__ == '__main__': guard in entry point.\n"
            "- For relative imports, use: from utils.helpers import foo\n"
            "- Do NOT use implicit relative imports (from . import ...).\n"
        )
    elif language.lower() in ("javascript", "typescript", "js", "ts"):
        lang_rules = (
            "JS/TS rules:\n"
            "- Use ES modules (import/export), not CommonJS.\n"
            "- Add JSDoc comments for exported functions.\n"
            "- Handle promise rejections with try/catch.\n"
        )

    prompt = (
        f"You are a senior {language} developer writing production code.\n\n"
        f"Project goal: {project_description}\n\n"
        f"Project files:\n{file_list}\n"
        f"{dependency_context}\n\n"
        f"Your task: Write complete code for: {file_path}\n"
        f"Purpose: {file_desc}\n"
        f"{'Imports from: ' + ', '.join(file_imports) if file_imports else 'No project-internal imports.'}\n\n"
        f"{lang_rules}\n"
        "Rules:\n"
        "- Output ONLY raw code. No explanation, no markdown, no backticks.\n"
        "- Write COMPLETE, RUNNABLE code — no placeholders, no 'TODO', no 'pass' stubs.\n"
        "- Match import paths EXACTLY to file paths in project structure.\n"
        "- Use try/except for I/O or network calls.\n"
        f"Code for {file_path}:"
    )

    messages = [
        {"role": "system", "content": f"You are a senior {language} developer. Return ONLY raw code."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.chat(messages)
        code = _strip_fences(response)

        full_path = project_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")

        print(f"[DevAgent] ✅ Written: {file_path} ({len(code)} chars)")
        return code
    except Exception as e:
        raise


# ─── Dependency Installer ─────────────────────────────────────────────────────

def _install_dependencies(dependencies: list[str], project_dir: Path) -> str:
    """Install missing Python packages."""
    if not dependencies:
        return "No external dependencies."

    to_install = []
    for dep in dependencies:
        pkg_name = re.split(r"[>=<!]", dep)[0].strip()
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg_name],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            to_install.append(dep)
        else:
            print(f"[DevAgent] ✓ Already installed: {pkg_name}")

    if not to_install:
        return f"All dependencies installed: {', '.join(dependencies)}"

    print(f"[DevAgent] 📦 Installing: {to_install}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + to_install,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=120, cwd=str(project_dir),
        )
        if result.returncode == 0:
            return f"Installed: {', '.join(to_install)}"
        return f"Install warning: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "Install timed out (non-fatal)."
    except Exception as e:
        return f"Install error: {e}"


# ─── Project Runner ────────────────────────────────────────────────────────────

def _run_project(run_command: str, project_dir: Path, timeout: int = 30) -> str:
    """Run the project and return output."""
    print(f"[DevAgent] 🚀 Running: {run_command}")
    try:
        parts = run_command.split()
        if parts and parts[0].lower() == "python":
            parts[0] = sys.executable

        result = subprocess.run(
            parts,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            cwd=str(project_dir),
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        parts_list = []
        if stdout:
            parts_list.append(f"STDOUT:\n{stdout}")
        if stderr:
            parts_list.append(f"STDERR:\n{stderr}")
        return "\n\n".join(parts_list) if parts_list else "Ran with no output."

    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s — long-running app may be working."
    except FileNotFoundError as e:
        return f"Command not found: {e}"
    except Exception as e:
        return f"Run error: {e}"


# ─── Auto-fix ─────────────────────────────────────────────────────────────────

def _try_auto_install(error_output: str, project_dir: Path) -> bool:
    """Auto-install missing packages from ModuleNotFoundError."""
    pattern = re.compile(r"No module named ['\"]([a-zA-Z0-9_\-.]+)['\"]", re.IGNORECASE)
    match = pattern.search(error_output)
    if not match:
        return False

    pkg = match.group(1).replace("_", "-").split(".")[0]
    print(f"[DevAgent] 🔧 Auto-installing: {pkg}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=60, cwd=str(project_dir),
        )
        return result.returncode == 0
    except Exception:
        return False


async def _fix_project_files(
    error_output: str,
    project_description: str,
    all_files: list[dict],
    file_codes: dict[str, str],
    language: str,
    project_dir: Path,
    entry_point: str,
) -> dict[str, str]:
    """Fix project files based on error output."""
    llm = _get_llm()

    error_file, error_line = _parse_traceback(error_output, list(file_codes.keys()))
    error_type = _classify_error(error_output)

    files_to_fix: list[str] = []
    if error_file:
        files_to_fix.append(error_file)
        if error_type == "import_error":
            for fi in all_files:
                dotted = error_file.replace("/", ".").replace(".py", "")
                if dotted in fi.get("imports", []):
                    p = fi["path"]
                    if p not in files_to_fix:
                        files_to_fix.append(p)
    else:
        files_to_fix.append(entry_point)

    updated_codes: dict[str, str] = {}

    for fix_path in files_to_fix:
        current_code = file_codes.get(fix_path, "")

        other_ctx = ""
        for fp, code in file_codes.items():
            if fp != fix_path and code:
                snippet = code[:1500] + ("..." if len(code) > 1500 else "")
                other_ctx += f"\n--- {fp} ---\n{snippet}\n"

        line_hint = (
            f"\nError near line {error_line} in this file."
            if error_line and fix_path == error_file else ""
        )

        prompt = (
            f"You are an expert {language} debugger. Fix the broken file below.\n\n"
            f"Project goal: {project_description}\n\n"
            f"All project files:\n"
            + "\n".join(f"  - {f['path']}: {f.get('description', '')}" for f in all_files)
            + f"\n\nOther files:\n{other_ctx[:3500]}"
            + f"\n\nFile to fix: {fix_path}{line_hint}\n"
            f"Error type: {error_type}\n\n"
            f"Error output:\n{error_output[:2500]}\n\n"
            f"Current (broken) code:\n{current_code}\n\n"
            "Rules:\n"
            "- Output ONLY the complete fixed code. No explanation, no markdown.\n"
            "- Fix ALL errors visible in the error output.\n"
            "- Keep all existing correct logic.\n"
            "- Match import paths exactly to project structure.\n\n"
            f"Fixed code for {fix_path}:"
        )

        messages = [
            {"role": "system", "content": "You are an expert debugger. Return ONLY fixed code."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = llm.chat(messages)
            fixed = _strip_fences(response)

            full_path = project_dir / fix_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(fixed, encoding="utf-8")

            updated_codes[fix_path] = fixed
            print(f"[DevAgent] 🔧 Fixed: {fix_path}")
        except Exception as e:
            print(f"[DevAgent] ⚠️ Could not fix {fix_path}: {e}")

    return updated_codes


# ─── VSCode Opener ─────────────────────────────────────────────────────────────

def _open_vscode(project_dir: Path) -> bool:
    """Open VSCode at the project directory."""
    candidates = [
        "code",
        str(Path.home() / "AppData/Local/Programs/Microsoft VS Code/bin/cmd.cmd"),
        r"C:\Program Files\Microsoft VS Code\bin\cmd.cmd",
    ]
    for cmd in candidates:
        try:
            subprocess.Popen(
                [cmd, str(project_dir)],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[DevAgent] 💻 VSCode opened: {project_dir}")
            return True
        except Exception:
            continue
    return False


# ─── Main Build Loop ───────────────────────────────────────────────────────────

async def build_project(
    description: str,
    language: str = "python",
    project_name: str = "",
    timeout: int = 30,
) -> str:
    """Full project build loop: plan → write → install → run → fix.

    Returns a human-readable build report.
    """
    def log(msg: str):
        print(f"[DevAgent] {msg}")

    log("Planning project structure...")
    try:
        plan = await _plan_project(description, language)
    except ValueError as e:
        return f"Planning failed: {e}"
    except Exception as e:
        return f"Planning error: {e}"

    proj_name = project_name or plan.get("project_name", "barq_project")
    proj_name = re.sub(r"[^\w\-]", "_", proj_name)
    project_dir = PROJECTS_DIR / proj_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files = plan.get("files", [])
    entry_point = plan.get("entry_point", "main.py")
    run_command = plan.get("run_command", f"python {entry_point}")
    dependencies = plan.get("dependencies", [])

    log(f"Project: {proj_name} | Files: {len(files)} | Entry: {entry_point}")

    # Sort files by import dependency count (fewest imports first)
    sorted_files = sorted(files, key=lambda fi: len(fi.get("imports", [])))

    # Write all files
    file_codes: dict[str, str] = {}
    for file_info in sorted_files:
        fp = file_info.get("path", "")
        if not fp:
            continue
        log(f"Writing {fp}...")
        try:
            code = await _write_project_file(
                file_info=file_info,
                project_description=description,
                all_files=files,
                language=language,
                project_dir=project_dir,
                already_written=file_codes,
            )
            file_codes[fp] = code
            await asyncio.sleep(0.3)  # Rate limit buffer
        except Exception as e:
            log(f"Failed to write {fp}: {e}")

    if not file_codes:
        return "Could not write any project files."

    # Install dependencies
    if dependencies:
        dep_result = _install_dependencies(dependencies, project_dir)
        log(dep_result)

    # Open in VSCode
    _open_vscode(project_dir)

    # Run → fix loop
    last_output = ""
    auto_installs = 0

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        log(f"Running (attempt {attempt}/{MAX_FIX_ATTEMPTS})...")
        last_output = _run_project(run_command, project_dir, timeout)
        log(f"Output: {last_output[:150]}")

        if not _has_error(last_output):
            return (
                f"Project '{proj_name}' built successfully in {attempt} attempt(s).\n"
                f"Saved to: {project_dir}\n\nOutput:\n{last_output}"
            )

        if attempt == MAX_FIX_ATTEMPTS:
            break

        # Auto-install missing deps
        error_type = _classify_error(last_output)
        if error_type == "dependency_error" and auto_installs < 3:
            installed = _try_auto_install(last_output, project_dir)
            if installed:
                auto_installs += 1
                log("Dependency auto-installed, retrying...")
                await asyncio.sleep(1)
                continue

        log(f"Fixing errors (type: {error_type})...")
        try:
            updated = await _fix_project_files(
                error_output=last_output,
                project_description=description,
                all_files=files,
                file_codes=file_codes,
                language=language,
                project_dir=project_dir,
                entry_point=entry_point,
            )
            file_codes.update(updated)
            await asyncio.sleep(1)
        except Exception as e:
            log(f"Fix step failed: {e}")

    return (
        f"Could not fully fix '{proj_name}' after {MAX_FIX_ATTEMPTS} attempts.\n"
        f"Project saved at: {project_dir}\n"
        f"Open it in VSCode and check manually.\n\n"
        f"Last error:\n{last_output[:600]}"
    )


# ─── Entry Point ───────────────────────────────────────────────────────────────

async def dev_agent(params: dict) -> str:
    """Build a complete project from a natural language description.

    Args:
        params: Dict with keys:
            - description: What to build (required)
            - language: Programming language (default: python)
            - project_name: Optional project directory name
            - timeout: Execution timeout in seconds

    Returns:
        Human-readable build report.
    """
    description = params.get("description", "").strip()
    if not description:
        return "Please describe the project you want me to build."

    language = params.get("language", "python").strip()
    project_name = params.get("project_name", "").strip()
    timeout = int(params.get("timeout", 30))

    return await build_project(
        description=description,
        language=language,
        project_name=project_name,
        timeout=timeout,
    )
