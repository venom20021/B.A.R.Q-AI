"""
BARQ Utilities — shared helpers used across modules.
"""

import re


def safe_filename(text: str, max_len: int = 60) -> str:
    """Strip or replace characters illegal in Windows filenames.

    Windows forbidden characters: \\ / : * ? " < > |
    Also strips leading/trailing dots and spaces (also illegal on Windows).
    Collapses multiple consecutive underscores into one.

    Args:
        text: Raw text to sanitize (e.g. job title, company name).
        max_len: Maximum length of the result (default 60).

    Returns:
        Sanitized string safe for use as a filename component on Windows.
    """
    # Replace illegal chars with underscore
    for c in '\\/:*?"<>|':
        text = text.replace(c, "_")
    # Collapse multiple underscores
    text = re.sub(r"_+", "_", text)
    # Strip leading/trailing dots, spaces, underscores
    text = text.strip(". _")
    # Truncate
    return text[:max_len]
