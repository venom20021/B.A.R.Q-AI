"""
CodeHelper — AI-powered code assistant for BARQ.

Inspired by Mark-L's code_helper.py. Provides:
- write: Generate code from description and save to file
- edit: Modify existing file with natural language instruction
- explain: Explain what code does
- run: Execute a file with the appropriate interpreter
- build: Write → run → fix iterative loop
- optimize: Refactor/clean up existing code
- screen_debug: Capture screen error + analyze with vision

All LLM calls use BARQ's existing OllamaClient so no extra API keys needed.
"""

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from utils.ollama_client import OllamaClient

# ─── Constants ────────────────────────────────────────────────────────────────

PROJECTS_DIR = Path.home() / "Desktop" / "BARQ_Projects"
MAX_BUILD_ATTEMPTS = 3

_EXT_MAP = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "html": ".html", "css": ".css",
    "java": ".java", "cpp": ".cpp", "c": ".c",
    "bash": ".sh", "shell": ".sh", "powershell": ".ps1",
    "sql": ".sql", "json": ".json", "rust": ".rs", "go": ".go",
    "markdown": ".md", "md": ".md", "yaml": ".yaml", "yml": ".yml",
    "toml": ".toml", "ini": ".ini", "cfg": ".cfg",
}

_INTERPRETERS = {
    ".py": [sys.executable],
    ".js": ["node"],
    ".ts": ["npx", "ts-node"],
    ".sh": ["bash"],
    ".ps1": ["powershell", "-File"],
    ".rb": ["ruby"],
    ".php": ["php"],
    ".go": ["go", "run"],
    ".rs": ["cargo", "script"],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_llm() -> OllamaClient:
    return OllamaClient()


def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _resolve_save_path(output_path: str, language: str) -> Path:
    ext = _EXT_MAP.get((language or "python").lower(), ".py")
    if output_path:
        p = Path(output_path)
        return p if p.is_absolute() else PROJECTS_DIR / p
    return PROJECTS_DIR / f"code_output{ext}"


def _save_file(path: Path, content: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Saved to: {path}"
    except Exception as e:
        return f"Could not save: {e}"


def _read_file(file_path: str) -> tuple[str, str]:
    if not file_path:
        return "", "No file path provided."
    p = Path(file_path)
    if not p.exists():
        return "", f"File not found: {file_path}"
    try:
        return p.read_text(encoding="utf-8"), ""
    except Exception as e:
        return "", f"Could not read: {e}"


def _preview(code: str, lines: int = 10) -> str:
    all_lines = code.splitlines()
    preview = "\n".join(all_lines[:lines])
    suffix = f"\n... ({len(all_lines) - lines} more lines)" if len(all_lines) > lines else ""
    return preview + suffix


def _has_error(output: str) -> bool:
    signals = ["error", "exception", "traceback", "syntaxerror",
               "nameerror", "typeerror", "failed", "crash", "stderr"]
    return any(s in output.lower() for s in signals)


def _run_file(path: Path, args: list | None = None, timeout: int = 30) -> str:
    interp = _INTERPRETERS.get(path.suffix.lower())
    if not interp:
        # Try to make it executable (Unix) or just run it
        if path.suffix in ("", ".exe", ".bat", ".cmd"):
            interp = [str(path)]
        else:
            return f"No interpreter configured for {path.suffix}."

    try:
        result = subprocess.run(
            interp + [str(path)] + (args or []),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(path.parent),
        )
        output = result.stdout.strip()
        error = result.stderr.strip()
        parts = []
        if output:
            parts.append(f"Output:\n{output}")
        if error:
            parts.append(f"Stderr:\n{error}")
        return "\n\n".join(parts) if parts else "Executed with no output."
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s."
    except FileNotFoundError:
        return f"Interpreter not found: {interp[0]}."
    except Exception as e:
        return f"Execution error: {e}"


# ─── Intent Detection ────────────────────────────────────────────────────────

_VALID_INTENTS = {"write", "edit", "explain", "run", "build", "optimize", "screen_debug"}


def _detect_intent(description: str, file_path: str, code: str) -> str:
    """Detect user intent from description, file_path, and code context.

    Falls back to structural heuristics if LLM is unavailable.
    """
    desc = (description or "").strip()
    file_exists = bool(file_path) and Path(file_path).exists()

    if desc:
        try:
            ctx_parts = []
            if file_path:
                ctx_parts.append(f"file path provided (exists: {file_exists})")
            if code:
                ctx_parts.append("inline code provided")
            ctx = "; ".join(ctx_parts) if ctx_parts else "no additional context"

            prompt = (
                "Classify coding request into exactly ONE intent word.\n\n"
                f"Request: {desc}\n"
                f"Context: {ctx}\n\n"
                "Intents:\n"
                "  write        = create new code from scratch\n"
                "  edit         = modify an existing file\n"
                "  explain      = describe what code/file does\n"
                "  run          = execute an existing file\n"
                "  build        = write code, run it, and iterate until it works\n"
                "  optimize     = refactor / clean up / speed up existing code\n"
                "  screen_debug = analyze an error visible on screen\n\n"
                "Reply with ONLY the intent word."
            )
            llm = _get_llm()
            messages = [
                {"role": "system", "content": "You classify coding requests. Reply with one word only."},
                {"role": "user", "content": prompt},
            ]
            ans = llm.chat(messages).strip().lower().strip("`'\".")
            if ans in _VALID_INTENTS:
                return ans
        except Exception as e:
            print(f"[CodeHelper] Intent detection failed ({e}), using fallback")

    # Structural fallback
    if file_exists:
        return "edit" if desc else "explain"
    if code:
        return "explain"
    return "write"


# ─── Action Implementations ───────────────────────────────────────────────────

async def _write_code(description: str, language: str, output_path: str) -> tuple[str, Path]:
    """Generate code from description and save to file."""
    lang = language or "python"
    llm = _get_llm()

    prompt = (
        f"You are an expert {lang} developer.\n"
        f"Write clean, working, well-commented {lang} code for the description below.\n\n"
        "Rules:\n"
        "- Output ONLY the code. No explanation, no markdown, no backticks.\n"
        "- Add helpful inline comments.\n"
        "- Handle errors and edge cases properly.\n"
        "- Use modern best practices.\n\n"
        f"Description: {description}\n\nCode:"
    )

    messages = [
        {"role": "system", "content": f"You are an expert {lang} developer."},
        {"role": "user", "content": prompt},
    ]
    response = llm.chat(messages)
    code = _clean_code(response)
    path = _resolve_save_path(output_path, lang)
    _save_file(path, code)
    return code, path


async def _fix_code(code: str, error_output: str, description: str) -> str:
    """Fix broken code given error output."""
    llm = _get_llm()
    prompt = (
        "The code below failed with an error. Fix it.\n"
        "Return ONLY the corrected code — no explanation, no markdown, no backticks.\n\n"
        f"Original goal: {description}\n\n"
        f"Error:\n{error_output[:2000]}\n\n"
        f"Broken code:\n{code}\n\nFixed code:"
    )
    messages = [
        {"role": "system", "content": "You are an expert debugger. Return ONLY fixed code."},
        {"role": "user", "content": prompt},
    ]
    response = llm.chat(messages)
    return _clean_code(response)


async def write_action(description: str, language: str = "python", output_path: str = "") -> str:
    """Generate and save code from description."""
    if not description:
        return "Please describe what code you want me to write."
    try:
        code, path = await _write_code(description, language, output_path)
        return f"Code written.\n{_save_file(path, code)}\n\nPreview:\n{_preview(code)}"
    except Exception as e:
        return f"Could not generate code: {e}"


async def edit_action(file_path: str, instruction: str) -> str:
    """Edit an existing file with a natural language instruction."""
    if not file_path:
        return "Please provide a file path to edit."
    if not instruction:
        return "Please describe what change to make."

    content, err = _read_file(file_path)
    if err:
        return err

    llm = _get_llm()
    prompt = (
        "Apply the following change to the code below.\n"
        "Return ONLY the complete updated code — no explanation, no markdown, no backticks.\n\n"
        f"Change: {instruction}\n\n"
        f"Original code:\n{content}\n\nUpdated code:"
    )
    messages = [
        {"role": "system", "content": "You are an expert code editor. Return ONLY the updated code."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.chat(messages)
        edited = _clean_code(response)
    except Exception as e:
        return f"Could not edit code: {e}"

    status = _save_file(Path(file_path), edited)
    return f"File edited. {status}\n\nPreview:\n{_preview(edited)}"


async def explain_action(file_path: str = "", code: str = "") -> str:
    """Explain what code does in simple terms."""
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to explain."

    llm = _get_llm()
    prompt = (
        "Explain what this code does in simple, clear language.\n"
        "Focus on: what it does, how it works, key details.\n"
        "Be concise — 3 to 6 sentences maximum.\n\n"
        f"Code:\n{code[:4000]}\n\nExplanation:"
    )
    messages = [
        {"role": "system", "content": "You explain code concisely and clearly."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.chat(messages)
        return response.strip()
    except Exception as e:
        return f"Could not explain code: {e}"


async def run_action(file_path: str, args: list | None = None, timeout: int = 30) -> str:
    """Execute a file with the appropriate interpreter."""
    if not file_path:
        return "Please provide a file path to run."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    return _run_file(p, args, timeout)


async def build_action(
    description: str,
    language: str = "python",
    output_path: str = "",
    args: list | None = None,
    timeout: int = 30,
) -> str:
    """Write → run → fix loop until code works or max attempts reached."""
    if not description:
        return "Please describe what you want me to build."

    try:
        code, path = await _write_code(description, language, output_path)
        print(f"[CodeHelper] ✅ Written: {path}")
    except Exception as e:
        return f"Could not write initial code: {e}"

    last_output = ""
    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        print(f"[CodeHelper] 🔄 Attempt {attempt}/{MAX_BUILD_ATTEMPTS}")
        last_output = _run_file(path, args, timeout)

        if not _has_error(last_output):
            return (
                f"Build complete after {attempt} attempt{'s' if attempt > 1 else ''}.\n"
                f"Saved to: {path}\n\nOutput:\n{last_output}"
            )

        print(f"[CodeHelper] ⚠️ Error, fixing (attempt {attempt})...")
        try:
            code = await _fix_code(code, last_output, description)
            _save_file(path, code)
        except Exception as e:
            return f"Could not fix code on attempt {attempt}: {e}"

    return (
        f"Could not build successfully after {MAX_BUILD_ATTEMPTS} attempts.\n"
        f"Last error:\n{last_output[:600]}\n\n"
        f"Code saved to: {path}"
    )


async def optimize_action(
    file_path: str = "",
    code: str = "",
    language: str = "python",
    output_path: str = "",
) -> str:
    """Optimize code for performance, readability, and best practices."""
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to optimize."

    lang = language or "python"
    llm = _get_llm()

    prompt = (
        f"You are an expert {lang} developer. Optimize the following code for:\n"
        "1. Performance — eliminate unnecessary ops, use efficient data structures\n"
        "2. Readability — clear names, proper formatting, logical structure\n"
        "3. Best practices — modern patterns, error handling, type hints\n"
        "4. Remove dead code, redundant comments, unnecessary complexity\n\n"
        "Return ONLY the optimized code — no explanation, no markdown, no backticks.\n\n"
        f"Original code:\n{code[:6000]}\n\nOptimized code:"
    )
    messages = [
        {"role": "system", "content": f"You are an expert {lang} developer."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.chat(messages)
        optimized = _clean_code(response)
    except Exception as e:
        return f"Could not optimize code: {e}"

    save_path = Path(file_path) if file_path else _resolve_save_path(output_path, lang)
    status = _save_file(save_path, optimized)
    original_lines = len(code.splitlines())
    optimized_lines = len(optimized.splitlines())
    diff = original_lines - optimized_lines
    return (
        f"Code optimized. {status}\n"
        f"Lines: {original_lines} → {optimized_lines} "
        f"({'−' if diff > 0 else '+'}{abs(diff)} lines)\n\n"
        f"Preview:\n{_preview(optimized)}"
    )


async def screen_debug_action(description: str = "", file_path: str = "") -> str:
    """Take a screenshot and analyze errors using AI vision."""
    print("[CodeHelper] 📸 Capturing screen for debug...")
    screenshot_path = None
    try:
        import pyautogui
        screenshot_path = Path.home() / "Desktop" / f"barq_debug_{int(time.time())}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(str(screenshot_path))
        print(f"[CodeHelper] Screenshot: {screenshot_path}")
    except ImportError:
        return "PyAutoGUI not installed. Run: pip install pyautogui"
    except Exception as e:
        return f"Screenshot failed: {e}"

    # Read file content if provided
    file_content = ""
    if file_path:
        file_content, err = _read_file(file_path)
        if err:
            print(f"[CodeHelper] ⚠️ Could not read file: {err}")

    try:
        # Use Gemini vision for screen analysis (falls back to Ollama if available)
        from agent.vision import analyze_image_with_gemini

        image_bytes = screenshot_path.read_bytes()
        mime_type = "image/png"

        user_question = description or "What error or problem do you see on the screen? How can it be fixed?"

        context = ""
        if file_content:
            context = f"\n\nRelated file:\n```\n{file_content[:4000]}\n```"

        vision_prompt = (
            f"You are an expert programmer analyzing a screenshot.\n\n"
            f"User's question: {user_question}{context}\n\n"
            "Please:\n"
            "1. Identify any errors, exceptions, or problems visible\n"
            "2. Explain the cause in simple terms\n"
            "3. Provide a concrete fix\n"
            "4. If code is visible, show the corrected version\n\n"
            "Be specific and actionable."
        )

        analysis = await analyze_image_with_gemini(image_bytes, mime_type, prompt=vision_prompt)
        print(f"[CodeHelper] ✅ Screen analysis complete")

        # Extract code from analysis and auto-apply fix
        if file_path and file_content:
            code_match = re.search(r"```[a-zA-Z]*\n(.*?)```", analysis, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
                _save_file(Path(file_path), fixed_code)
                analysis += f"\n\n✅ Fixed code saved to: {file_path}"
                print(f"[CodeHelper] ✅ Fixed code saved: {file_path}")

        return analysis

    except ImportError:
        return (
            f"Screen captured: {screenshot_path}\n\n"
            "Vision analysis requires Gemini API key for screen reading.\n"
            "Setting up... please check the screenshot manually."
        )
    except Exception as e:
        return f"Screen analysis failed: {e}"
    finally:
        if screenshot_path and screenshot_path.exists():
            try:
                screenshot_path.unlink()
            except Exception:
                pass


async def auto_action(
    description: str = "",
    file_path: str = "",
    code: str = "",
    language: str = "python",
    output_path: str = "",
    args: list | None = None,
    timeout: int = 30,
) -> str:
    """Auto-detect intent and dispatch to the right action."""
    intent = _detect_intent(description, file_path, code)
    print(f"[CodeHelper] 🤖 Auto-detected: {intent}")

    if intent == "write":
        return await write_action(description, language, output_path)
    elif intent == "edit":
        return await edit_action(file_path, description)
    elif intent == "explain":
        return await explain_action(file_path, code)
    elif intent == "run":
        return await run_action(file_path, args, timeout)
    elif intent == "build":
        return await build_action(description, language, output_path, args, timeout)
    elif intent == "optimize":
        return await optimize_action(file_path, code, language, output_path)
    elif intent == "screen_debug":
        return await screen_debug_action(description, file_path)
    else:
        return f"Unknown intent: {intent}"


# ─── Unified Entry Point ──────────────────────────────────────────────────────

async def code_helper(params: dict) -> str:
    """Main entry point for the code helper skill.

    Args:
        params: Dict with keys:
            - action: "write" | "edit" | "explain" | "run" | "build" | "optimize" | "screen_debug" | "auto"
            - description: What the code should do / what change to make
            - language: Programming language (default: python)
            - output_path: Where to save the file
            - file_path: Path to existing file
            - code: Raw code string
            - args: CLI argument list for run/build
            - timeout: Execution timeout in seconds

    Returns:
        Human-readable result string.
    """
    action = params.get("action", "auto").lower().strip()
    description = params.get("description", "").strip()
    language = params.get("language", "python").strip()
    output_path = params.get("output_path", "").strip()
    file_path = params.get("file_path", "").strip()
    code = params.get("code", "").strip()
    args = params.get("args", [])
    timeout = int(params.get("timeout", 30))

    action_map = {
        "auto": lambda: auto_action(description, file_path, code, language, output_path, args, timeout),
        "write": lambda: write_action(description, language, output_path),
        "edit": lambda: edit_action(file_path, description),
        "explain": lambda: explain_action(file_path, code),
        "run": lambda: run_action(file_path, args, timeout),
        "build": lambda: build_action(description, language, output_path, args, timeout),
        "optimize": lambda: optimize_action(file_path, code, language, output_path),
        "screen_debug": lambda: screen_debug_action(description, file_path),
    }

    handler = action_map.get(action)
    if not handler:
        return f"Unknown action: '{action}'. Use: write, edit, explain, run, build, optimize, screen_debug, auto."

    return await handler()
