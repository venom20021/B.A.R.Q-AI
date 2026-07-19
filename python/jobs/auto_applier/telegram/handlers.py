"""
Telegram message handlers and callback query processors.

Handles:
  - /start, /help commands
  - [⚡ Apply Via Bot] and [❌ Skip Role] inline button callbacks
  - Morning dispatch interaction
  - Error notifications
"""

import json
import logging
from typing import Any, Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger("barq.auto_applier.telegram.handlers")

# Will be set by AutoApplyBot._wire_callbacks()
_bot_instance: Any = None


def set_bot_instance(bot: Any) -> None:
    """Called by AutoApplyBot to register itself for callback dispatching."""
    global _bot_instance
    _bot_instance = bot


# ─── Router ───────────────────────────────────────────────────────────────

router = Router()


# ─── Command Handlers ─────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    text = (
        "👋 <b>BARQ Auto Applier</b>\n\n"
        "I can help you apply to jobs automatically!\n\n"
        "Commands:\n"
        "  /scan — Scan for new jobs\n"
        "  /digest — Get today's top matches\n"
        "  /apply <#N> — Apply to job #N\n"
        "  /status — Check bot status\n"
        "  /help — Show this message"
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Show current bot status."""
    from ..config import CONFIG, PROFILE
    text = (
        f"<b>BARQ Auto Applier Status</b>\n\n"
        f"👤 Profile: {PROFILE.full_name}\n"
        f"🎯 Targeting: {PROFILE.seeking}\n"
        f"🤖 Ollama: {CONFIG.ollama_model}\n"
        f"🧠 Resume: {'✅ Loaded' if CONFIG.resume_pdf_path else '❌ Not set'}\n"
        f"🔑 LinkedIn: {'✅ Configured' if CONFIG.linkedin_email else '❌ Not configured'}\n"
        f"📱 Telegram: {'✅ Active' if CONFIG.telegram_bot_token else '❌ Not configured'}\n"
    )
    await message.answer(text)


@router.message(Command("scan"))
async def cmd_scan(message: Message) -> None:
    """Trigger a job scan."""
    await message.answer("🔍 Scanning for new jobs... (this may take a few minutes)")

    if _bot_instance and _bot_instance.on_scan:
        try:
            results = await _bot_instance.on_scan()
            await message.answer(f"✅ Scan complete! Found {len(results)} matching jobs.")
        except Exception as exc:
            await message.answer(f"❌ Scan failed: {exc}")
    else:
        await message.answer("⚠️ Scan handler not registered. Please start BARQ first.")


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    """Send the morning digest."""
    await message.answer("📋 Generating morning digest...")
    if _bot_instance:
        await _bot_instance.send_morning_digest([])
    else:
        await message.answer("⚠️ Bot not fully initialized.")


@router.message(Command("apply"))
async def cmd_apply(message: Message) -> None:
    """Apply to a specific job by index."""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /apply <job_number> (e.g., /apply 3)")
        return

    try:
        job_num = int(args[1])
        await message.answer(f"⚡ Applying to job #{job_num}...")

        if _bot_instance and _bot_instance.on_apply:
            result = await _bot_instance.on_apply(str(job_num))
            status = "✅ Submitted!" if result.get("submitted") else "⚠️ Incomplete"
            await message.answer(f"{status}\n{json.dumps(result, indent=2)[:500]}")
        else:
            await message.answer("⚠️ Apply handler not registered.")
    except ValueError:
        await message.answer("Please provide a valid job number.")


# ─── Callback Query Handlers ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("apply:"))
async def cb_apply(callback: CallbackQuery) -> None:
    """Handle [⚡ Apply Via Bot] button click."""
    job_id = callback.data.split(":", 1)[1]
    await callback.answer("⚡ Starting application...")
    await callback.message.edit_text(
        f"{callback.message.html_text}\n\n⚡ <i>Applying via bot...</i>",
    )

    if _bot_instance and _bot_instance.on_apply:
        try:
            result = await _bot_instance.on_apply(job_id)
            status = "✅ Submitted!" if result.get("submitted") else "⚠️ Incomplete"
            await callback.message.answer(
                f"<b>Result for #{job_id}</b>\n{status}\n"
                f"📄 {json.dumps(result, indent=2)[:300]}"
            )
        except Exception as exc:
            await callback.message.answer(f"❌ Application failed: {exc}")
    else:
        await callback.message.answer("⚠️ Apply handler not registered.")


@router.callback_query(F.data.startswith("skip:"))
async def cb_skip(callback: CallbackQuery) -> None:
    """Handle [❌ Skip Role] button click."""
    job_id = callback.data.split(":", 1)[1]
    await callback.answer(f"Skipped job #{job_id}")
    await callback.message.edit_text(
        f"{callback.message.html_text}\n\n❌ <i>Skipped</i>",
    )

    if _bot_instance and _bot_instance.on_skip:
        await _bot_instance.on_skip(job_id)


@router.callback_query(F.data == "apply:all")
async def cb_apply_all(callback: CallbackQuery) -> None:
    """Handle 'Apply to All' button."""
    await callback.answer("⚡ Applying to all matches...")
    await callback.message.answer("⚡ Processing all jobs in batch (this may take a while)...")


@router.callback_query(F.data == "scan:now")
async def cb_scan_now(callback: CallbackQuery) -> None:
    """Handle 'Scan Now' button."""
    await callback.answer("🔍 Starting scan...")
    await callback.message.answer("🔍 Scanning for new jobs...")


@router.callback_query(F.data.startswith("details:"))
async def cb_details(callback: CallbackQuery) -> None:
    """Handle 'View Details' button."""
    job_id = callback.data.split(":", 1)[1]
    await callback.answer(f"📄 Details for #{job_id}")
    await callback.message.answer(f"📄 <b>Job #{job_id} Details</b>\n(Full details coming soon)")


@router.callback_query(F.data.startswith("back:"))
async def cb_back(callback: CallbackQuery) -> None:
    """Handle back navigation."""
    await callback.answer()
    await callback.message.edit_text("« Back to main menu")


# ─── Fallback ─────────────────────────────────────────────────────────────

@router.message()
async def fallback(message: Message) -> None:
    """Handle unrecognized messages."""
    text = message.text or ""
    if text.startswith("/"):
        await message.answer(f"Unknown command: {text}\nTry /help")
    else:
        await message.answer("Use /help to see available commands.")
