"""Tests for the BARQ Agent Error Handler.

Tests the pure functions in agent/error_handler.py:
    - analyze_error() with various error scenarios
    - ErrorDecision enum values
    - _generate_fix_suggestion() tool-specific suggestions
    - Max attempts threshold behavior
"""

from agent.error_handler import (
    ErrorDecision,
    _generate_fix_suggestion,
    analyze_error,
)

# ─── ErrorDecision enum ───────────────────────────────────────────────────

class TestErrorDecision:
    """Verify the enum values exist and have expected string values."""

    def test_values(self):
        assert ErrorDecision.RETRY.value == "retry"
        assert ErrorDecision.SKIP.value == "skip"
        assert ErrorDecision.REPLAN.value == "replan"
        assert ErrorDecision.ABORT.value == "abort"

    def test_all_members(self):
        assert len(ErrorDecision) == 4


# ─── analyze_error ────────────────────────────────────────────────────────

class TestAnalyzeError:
    """Tests for the main analyze_error() function."""

    def test_transient_error_retries(self):
        """A network timeout should produce RETRY decision."""
        step = {"step": 1, "tool": "web_search", "critical": True}
        result = analyze_error(step, "Connection timeout after 30s", attempt=1)
        assert result["decision"] == ErrorDecision.RETRY
        assert "transient" in result["reason"].lower()
        assert result["max_retries"] == 1

    def test_transient_rate_limit_retries(self):
        """429 / rate-limit errors should produce RETRY."""
        step = {"step": 2, "tool": "web_search", "critical": False}
        result = analyze_error(step, "429 Too Many Requests", attempt=1)
        assert result["decision"] == ErrorDecision.RETRY

    def test_max_attempts_forces_replan(self):
        """When attempt >= max_attempts, force REPLAN instead of RETRY."""
        step = {"step": 1, "tool": "web_search", "critical": True}
        # Even transient errors should replan when max attempts reached
        result = analyze_error(step, "Connection timeout", attempt=2, max_attempts=2)
        assert result["decision"] == ErrorDecision.REPLAN
        assert "attempts" in result["reason"]

    def test_non_critical_skippable_tool_skips(self):
        """Non-critical steps with skippable tools should produce SKIP."""
        step = {"step": 3, "tool": "check_trends", "critical": False}
        result = analyze_error(step, "API error: no trends found", attempt=1)
        assert result["decision"] == ErrorDecision.SKIP
        assert "non-critical" in result["reason"].lower()

    def test_critical_step_not_skipped(self):
        """Critical steps should not be skipped even if tool is skippable."""
        step = {"step": 3, "tool": "check_trends", "critical": True}
        result = analyze_error(step, "API error", attempt=1)
        assert result["decision"] != ErrorDecision.SKIP

    def test_unknown_error_defaults_to_replan(self):
        """Unrecognized errors on critical steps should produce REPLAN."""
        step = {"step": 4, "tool": "web_search", "critical": True}
        result = analyze_error(step, "Something went horribly wrong", attempt=1)
        assert result["decision"] == ErrorDecision.REPLAN
        assert result["fix_suggestion"]  # Should have a fix suggestion

    def test_replan_has_user_message(self):
        """REPLAN decisions should include a user-facing message."""
        step = {"step": 5, "tool": "launch_app", "critical": True}
        result = analyze_error(step, "Application not found", attempt=1)
        assert result["decision"] == ErrorDecision.REPLAN
        assert result["user_message"]

    def test_skip_has_empty_user_message(self):
        """SKIP decisions should have empty user_message (no need to notify)."""
        step = {"step": 6, "tool": "read_file", "critical": False}
        result = analyze_error(step, "File not readable", attempt=1)
        assert result["decision"] == ErrorDecision.SKIP
        assert result["user_message"] == ""

    def test_retry_has_user_message(self):
        """RETRY decisions should reassure the user."""
        step = {"step": 7, "tool": "web_search", "critical": True}
        result = analyze_error(step, "temporary failure", attempt=1)
        assert result["decision"] == ErrorDecision.RETRY
        assert "retrying" in result["user_message"].lower()

    def test_tool_send_message_skippable(self):
        """send_message is in the skippable set."""
        step = {"step": 8, "tool": "send_message", "critical": False}
        result = analyze_error(step, "Telegram API error", attempt=1)
        assert result["decision"] == ErrorDecision.SKIP

    def test_tool_browse_url_skippable(self):
        """browse_url is in the skippable set."""
        step = {"step": 9, "tool": "browse_url", "critical": False}
        # Use a non-transient error message so it doesn't match RETRY first
        result = analyze_error(step, "Page element not found", attempt=1)
        assert result["decision"] == ErrorDecision.SKIP

    def test_tool_web_search_not_skippable(self):
        """web_search is NOT in the skippable set (it's primary)."""
        step = {"step": 10, "tool": "web_search", "critical": False}
        result = analyze_error(step, "Search failed", attempt=1)
        assert result["decision"] != ErrorDecision.SKIP


# ─── _generate_fix_suggestion ─────────────────────────────────────────────

class TestGenerateFixSuggestion:
    """Tests for tool-specific fix suggestions."""

    def test_web_search_suggestion(self):
        assert "keywords" in _generate_fix_suggestion("web_search", "no results").lower()

    def test_launch_app_suggestion(self):
        # Use a non-match error so it falls through to tool-specific suggestion
        assert "alternative" in _generate_fix_suggestion("launch_app", "executable missing").lower()

    def test_create_file_suggestion(self):
        assert "permissions" in _generate_fix_suggestion("create_file", "permission denied").lower()

    def test_not_found_error(self):
        """'not found' errors should produce a path verification suggestion."""
        suggestion = _generate_fix_suggestion("read_file", "file not found")
        assert "verify" in suggestion.lower() or "correct" in suggestion.lower()

    def test_permission_error(self):
        """Permission errors should suggest elevated privileges."""
        suggestion = _generate_fix_suggestion("create_file", "access denied")
        assert "permission" in suggestion.lower() or "elevated" in suggestion.lower()

    def test_invalid_error(self):
        """Invalid parameter errors should suggest checking values."""
        suggestion = _generate_fix_suggestion("web_search", "invalid query")
        assert "parameter" in suggestion.lower() or "valid" in suggestion.lower()

    def test_unknown_tool_fallback(self):
        """Unknown tools should return a generic suggestion."""
        suggestion = _generate_fix_suggestion("unknown_tool", "error")
        assert "alternative" in suggestion.lower() or "different" in suggestion.lower()
