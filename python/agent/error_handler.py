"""
BARQ Agent Error Handler — analyzes step failures and decides recovery strategy.

When a step in a multi-step plan fails, the error handler examines the
error type, step context, and retry count to determine the best recovery
strategy: retry, skip, replan, or abort.

Inspired by MARK XXXIX-OR's error_handler.py.
"""

from enum import Enum

from .skill_registry import get_skill_registry


class ErrorDecision(Enum):
    """Recovery strategies for failed steps."""
    RETRY = "retry"    # Transient error — try the same step again
    SKIP = "skip"       # Non-critical step — continue without it
    REPLAN = "replan"   # Wrong approach — create a new plan
    ABORT = "abort"    # Fatal — cannot continue


# Transient error patterns that are likely to succeed on retry
_TRANSIENT_ERRORS = [
    "timeout",
    "connection refused",
    "connection reset",
    "network",
    "temporary",
    "rate limit",
    "too many requests",
    "429",
    "503",
    "502",
    "500",
    "internal server error",
    "service unavailable",
    "temporarily",
    "retry",
]

# Non-critical step tools that can be safely skipped.
# Derived from the SkillRegistry instead of hardcoded.
# Falls back to the legacy set when the registry reports empty
# (e.g. during tests or before built-in skills are registered).
_LEGACY_SKIPPABLE_TOOLS = {
    "check_trends",
    "send_message",
    "browse_url",
    "read_file",
}


def _get_skiplist() -> set[str]:
    """Get the current set of skippable (non-critical) skill names.

    Delegates to ``SkillRegistry.get_skiplist()`` so that dynamically
    registered skills are automatically reflected.
    Falls back to the legacy hardcoded set if no skills are registered.
    """
    try:
        registry_skiplist = get_skill_registry().get_skiplist()
        if registry_skiplist:
            return registry_skiplist
        return _LEGACY_SKIPPABLE_TOOLS
    except Exception:
        return _LEGACY_SKIPPABLE_TOOLS


def analyze_error(
    step: dict,
    error: str,
    attempt: int = 1,
    max_attempts: int = 2,
) -> dict:
    """Analyze a failed step and determine the best recovery strategy.

    Args:
        step: The step dict that failed.
        error: The error message or traceback.
        attempt: Current attempt number (1-based).
        max_attempts: Maximum retries before forcing replan.

    Returns:
        Dict with keys: decision (ErrorDecision), reason, fix_suggestion,
        max_retries, user_message.
    """
    error_lower = error.lower()
    is_transient = any(pattern in error_lower for pattern in _TRANSIENT_ERRORS)
    is_critical = step.get("critical", False)
    tool = step.get("tool", "")

    # ── Max attempts reached → force replan ──────────────────────────
    if attempt >= max_attempts:
        print(f"[ErrorHandler] WARN Max attempts ({max_attempts}) reached for step {step.get('step')}")
        return _make_decision(
            ErrorDecision.REPLAN,
            f"Failed after {attempt} attempts: {error[:100]}",
            "Try a different approach or tool",
            0,
            "Trying a different approach.",
        )

    # ── Transient error → retry ─────────────────────────────────────
    if is_transient:
        print(f"[ErrorHandler] RETRY Transient error detected — retrying (attempt {attempt})")
        return _make_decision(
            ErrorDecision.RETRY,
            f"Transient error: {error[:100]}",
            "",
            1,
            "I hit a temporary issue, retrying...",
        )

    # ── Non-critical step → skip ────────────────────────────────────
    _skiplist = _get_skiplist()
    if not is_critical and tool in _skiplist:
        print(f"[ErrorHandler] SKIP Non-critical step, skipping: {tool}")
        return _make_decision(
            ErrorDecision.SKIP,
            f"Non-critical step '{tool}' failed: {error[:100]}",
            "",
            0,
            "",
        )

    # ── Permission error → abort (safety) ────────────────────────
    if "permission" in error_lower or "access denied" in error_lower or "not permitted" in error_lower:
        print(f"[ErrorHandler] ABORT Permission denied — cannot continue")
        return _make_decision(
            ErrorDecision.ABORT,
            f"Permission denied: {error[:100]}",
            "Request user approval or use a different command.",
            0,
            "I can't proceed — permission denied. Please approve the command or try a different approach.",
        )

    # ── Default: replan with fix suggestion ─────────────────────────
    fix = _generate_fix_suggestion(tool, error)
    return _make_decision(
        ErrorDecision.REPLAN,
        f"Step failed: {error[:100]}",
        fix,
        0,
        "Let me try a different approach.",
    )


def _make_decision(
    decision: ErrorDecision,
    reason: str,
    fix_suggestion: str,
    max_retries: int,
    user_message: str,
) -> dict:
    """Create a structured decision dict."""
    return {
        "decision": decision,
        "reason": reason,
        "fix_suggestion": fix_suggestion,
        "max_retries": max_retries,
        "user_message": user_message,
    }


def _generate_fix_suggestion(tool: str, error: str) -> str:
    """Generate a context-aware fix suggestion based on tool and error.

    Args:
        tool: The tool that failed.
        error: The error message.

    Returns:
        A natural language suggestion for an alternative approach.
    """
    error_lower = error.lower()

    suggestions = {
        "web_search": "Try a more specific search query or different keywords.",
        "launch_app": "Try finding the application in an alternative location or using the system search.",
        "system_command": "Try a simpler or alternative command. Check if the required tool is installed.",
        "create_file": "Try a different file path with write permissions.",
        "read_file": "Check if the file exists at the specified path.",
        "browse_url": "The URL may be unreachable. Try searching for the content instead.",
        "get_weather": "Try a nearby city or check the weather service status.",
        "send_message": "The messaging platform may be unavailable. Try an alternative platform.",
        "check_trends": "Try checking trends for a different topic or region.",
    }

    # Check for specific error patterns
    if "not found" in error_lower or "does not exist" in error_lower:
        return "Verify the path or name and try again with the correct value."

    if "permission" in error_lower or "access denied" in error_lower:
        return "Try a different location with write permissions or run with elevated privileges."

    if "invalid" in error_lower:
        return "Check the parameters and provide valid values."

    return suggestions.get(tool, "Try an alternative approach using a different tool.")


