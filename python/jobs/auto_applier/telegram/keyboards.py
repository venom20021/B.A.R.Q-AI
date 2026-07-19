"""Inline keyboard builders for Telegram interactive job cards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def job_application_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Build the inline keyboard for a job card.

    Args:
        job_id: Unique identifier for the job (used in callback_data).
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⚡ Apply Via Bot",
            callback_data=f"apply:{job_id}",
        ),
        InlineKeyboardButton(
            text="❌ Skip Role",
            callback_data=f"skip:{job_id}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📄 View Details",
            callback_data=f"details:{job_id}",
        ),
    )
    return builder.as_markup()


def morning_digest_keyboard() -> InlineKeyboardMarkup:
    """Build the keyboard for the morning dispatch digest."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📋 Apply to All",
            callback_data="apply:all",
        ),
        InlineKeyboardButton(
            text="🔍 Scan Now",
            callback_data="scan:now",
        ),
    )
    return builder.as_markup()


def back_keyboard() -> InlineKeyboardMarkup:
    """Simple back button."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="« Back",
            callback_data="back:main",
        ),
    )
    return builder.as_markup()
