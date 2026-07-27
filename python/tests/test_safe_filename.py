"""
Tests for utils.safe_filename — Windows-safe filename sanitization.

Covers:
- All 9 Windows-illegal characters: \ / : * ? " < > |
- Underscore collapsing (multiple → single)
- Leading/trailing dot, space, underscore stripping
- max_len truncation (default and custom)
- Edge cases: empty string, only-special, already-clean
- Real-world scenarios: LinkedIn job titles with pipe
"""

import pytest
from utils import safe_filename


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Windows-illegal Characters
# ═══════════════════════════════════════════════════════════════════════════════


class TestWindowsIllegalChars:
    """All 9 characters forbidden in Windows filenames: \ / : * ? " < > |"""

    @pytest.mark.parametrize("illegal_char", [
        "\\",   # backslash
        "/",    # forward slash
        ":",    # colon
        "*",    # asterisk
        "?",    # question mark
        '"',    # double quote
        "<",    # less than
        ">",    # greater than
        "|",    # pipe
    ])
    def test_illegal_chars_replaced_with_underscore(self, illegal_char):
        """Each illegal character should be replaced with an underscore."""
        result = safe_filename(f"file{illegal_char}name")
        assert "_" in result, f"Illegal char {illegal_char!r} should be replaced"
        assert illegal_char not in result, f"Illegal char {illegal_char!r} should not remain"

    def test_multiple_illegal_chars(self):
        """Multiple different illegal chars should all be replaced."""
        result = safe_filename('foo:bar*baz?qux"quux<quuz>corge|grault')
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_real_world_linkedin_pipe(self):
        """Real-world case: 'Full Stack Engineer in Ireland | LinkedIn Skill'."""
        raw = "Full_Stack_Engineer_in_Ireland_|_LinkedIn_Skill"
        result = safe_filename(raw)
        assert "|" not in result, "Pipe should be removed"
        assert result == safe_filename(raw.replace("|", "_"))  # same as if pipe was underscore


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Underscore Collapsing
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnderscoreCollapsing:
    """Multiple consecutive underscores should collapse into one."""

    @pytest.mark.parametrize("input_str,expected", [
        ("hello___world", "hello_world"),
        ("a__b__c", "a_b_c"),
        ("___leading", "leading"),
        ("trailing___", "trailing"),
        ("only___underscores", "only_underscores"),
    ])
    def test_collapse_multi_underscores(self, input_str, expected):
        assert safe_filename(input_str) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Leading / Trailing Strip
# ═══════════════════════════════════════════════════════════════════════════════


class TestStripEdgeChars:
    """Leading/trailing dots, spaces, and underscores should be stripped."""

    @pytest.mark.parametrize("input_str,expected", [
        ("  leading_spaces", "leading_spaces"),
        ("trailing_spaces  ", "trailing_spaces"),
        ("...dots", "dots"),
        ("dots...", "dots"),
        ("  ...mixed  ", "mixed"),
        ("___underscores", "underscores"),
        ("___", ""),
        ("...", ""),
        (" . _ ", ""),
    ])
    def test_strip_leading_trailing(self, input_str, expected):
        """Leading/trailing dots, spaces, underscores should be stripped."""
        assert safe_filename(input_str) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 4. max_len Truncation
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaxLength:
    """Truncation via max_len parameter."""

    def test_default_max_len(self):
        """Default max_len should be 60."""
        long = "a" * 100
        result = safe_filename(long)
        assert len(result) == 60

    def test_custom_max_len(self):
        """Custom max_len should be respected."""
        long = "a" * 50
        result = safe_filename(long, max_len=10)
        assert len(result) == 10

    def test_shorter_than_max_len(self):
        """Strings shorter than max_len should not be truncated."""
        short = "hello"
        result = safe_filename(short, max_len=100)
        assert result == "hello"

    def test_exact_max_len(self):
        """Strings exactly max_len should not be truncated."""
        exact = "a" * 30
        result = safe_filename(exact, max_len=30)
        assert result == exact

    def test_zero_max_len(self):
        """max_len=0 should return empty string."""
        result = safe_filename("anything", max_len=0)
        assert result == ""

    def test_one_max_len(self):
        """max_len=1 should return first character."""
        result = safe_filename("abc", max_len=1)
        assert len(result) == 1
        assert result == "a"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Boundary and edge cases."""

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert safe_filename("") == ""

    def test_only_special_chars(self):
        """String with only illegal chars should become empty after stripping."""
        result = safe_filename("\\/:*?\"<>|")
        # All illegal chars become underscores, then collapsed, then stripped
        assert result == ""  # All underscores stripped

    def test_already_clean(self):
        """Already-safe string should pass through unchanged."""
        assert safe_filename("hello_world-123") == "hello_world-123"

    def test_alphanumeric_only(self):
        """Pure alphanumeric string should pass through."""
        assert safe_filename("Resume123") == "Resume123"

    def test_mixed_case_preserved(self):
        """Case should be preserved (not lowercased)."""
        assert safe_filename("Full_Stack_Engineer") == "Full_Stack_Engineer"

    def test_hyphens_preserved(self):
        """Hyphens are legal in Windows filenames and should be preserved."""
        assert safe_filename("my-file-name") == "my-file-name"

    def test_spaces_preserved_as_underscores(self):
        """Spaces are replaced with underscores by caller before safe_filename."""
        # safe_filename doesn't replace spaces, but callers do .replace(' ', '_')
        result = safe_filename("hello world".replace(" ", "_"))
        assert result == "hello_world"

    def test_only_spaces(self):
        """String with only spaces should become empty."""
        assert safe_filename("   ") == ""

    def test_only_illegal_chars_with_underscores(self):
        """Mix of only illegal chars and underscores should strip cleanly."""
        result = safe_filename("_|_:_*_?_")
        assert result == ""

    def test_unicode_chars_preserved(self):
        """Unicode characters (accents, etc.) should be preserved."""
        assert safe_filename("café_ résumé".replace(" ", "_")) == "café_résumé"
        assert safe_filename("München") == "München"

    def test_numbers_only(self):
        """Numeric string should pass through."""
        assert safe_filename("12345") == "12345"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Real-world Scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestRealWorldScenarios:
    """Scenarios mirroring actual use cases from the codebase."""

    def test_company_job_title_slug(self):
        """Telegram bot slug: f\"{company}_{job_title}\" with LinkedIn pipe."""
        company = "LinkedIn"
        job_title = "Full Stack Engineer in Ireland | Skill Assessment"
        slug_input = f"{company}_{job_title}".replace(" ", "_")
        result = safe_filename(slug_input, max_len=50)
        assert "|" not in result
        assert result.startswith("LinkedIn_")
        assert "Full_Stack_Engineer" in result

    def test_empty_company(self):
        """Edge case where company is empty: _Job_Title."""
        result = safe_filename("_Software_Engineer".replace(" ", "_"), max_len=50)
        assert result == "Software_Engineer"  # Leading underscore stripped

    def test_pathological_title(self):
        """Title with every illegal character."""
        bad_title = 'Senior:Developer*Full?Stack"Engineer<with>Everything\\Bad|Wow'
        result = safe_filename(bad_title.replace(" ", "_"))
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result
        assert result == "Senior_Developer_Full_Stack_Engineer_with_Everything_Bad_Wow"

    def test_filename_roundtrip(self):
        """Verify the output is usable as a Windows filename component."""
        result = safe_filename("Full_Stack_Engineer_in_Ireland_|_LinkedIn_Skill", max_len=50)
        # Windows forbids these characters: \ / : * ? " < > |
        for c in '\\/:*?"<>|':
            assert c not in result, f"Illegal char {c!r} should not appear"

    def test_max_len_short_with_special_chars(self):
        """Short max_len after illegal char replacement should respect boundary."""
        result = safe_filename("a|b|c|d|e", max_len=3)
        assert len(result) <= 3

    @pytest.mark.parametrize("input_str", [
        "test_with_trailing_dot.",
        ".leading_dot",
        "file.with.dots",
        "  spaced  ",
        "___",
        "...",
    ])
    def test_safe_filename_is_idempotent(self, input_str):
        """Running safe_filename twice should give same result."""
        first = safe_filename(input_str)
        second = safe_filename(first)
        assert first == second, f"safe_filename is not idempotent for {input_str!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Consistency / Idempotency
# ═══════════════════════════════════════════════════════════════════════════════


class TestIdempotency:
    """safe_filename should be idempotent — running it twice yields same result."""

    def test_clean_string_idempotent(self):
        """Already-clean strings should be identical after second pass."""
        assert safe_filename(safe_filename("hello")) == safe_filename("hello")

    def test_special_chars_idempotent(self):
        """Strings with illegal chars should converge after first pass."""
        first = safe_filename("hello|world:test")
        second = safe_filename(first)
        assert first == second

    def test_leading_trailing_idempotent(self):
        """Leading/trailing cleanup should converge after first pass."""
        first = safe_filename("  hello  ")
        second = safe_filename(first)
        assert first == second
