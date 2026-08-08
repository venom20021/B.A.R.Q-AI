"""
Telegram Ingestion Bot — accepts job descriptions/URLs via Telegram and
returns a tailored PDF resume via the BARQ pipeline.

Standalone worker script. Run with:
    python telegram_ingestion_bot.py

Architecture:
    Uses python-telegram-bot v20+ Application with polling.
    On receiving a job description/URL, acknowledges instantly with
    "⚡ Processing..." then processes in background via
    asyncio.create_task() to keep the bot responsive.

Required env vars (.env):
    TELEGRAM_BOT_TOKEN       — Your bot token from BotFather
    TELEGRAM_ALLOWED_CHAT_ID — Your chat ID or @username (security gate)
"""

import asyncio
import html
import logging
import os
import re
import sys
from typing import Any

# Fix Windows console encoding for emoji/Unicode output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Older Python versions

# Ensure the python directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import get_settings
from jobs.matcher import JobMatcher
from jobs.optimizer import ResumeOptimizer
from jobs.pdf_generator import GENERATED_DIR, ResumePDFGenerator
from jobs.resume_parser import parse_resume
from utils import safe_filename




logger = logging.getLogger("barq.telegram_ingestion")

# ─── Settings ────────────────────────────────────────────────────────────────

settings = get_settings()

BOT_TOKEN = settings.telegram_bot_token
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", settings.telegram_chat_id)

if not BOT_TOKEN:
    raise ValueError(
        "TELEGRAM_BOT_TOKEN not set. "
        "Add it to your .env file: TELEGRAM_BOT_TOKEN=your_bot_token"
    )
if not ALLOWED_CHAT_ID:
    raise ValueError(
        "TELEGRAM_ALLOWED_CHAT_ID not set. "
        "Add it to your .env file: TELEGRAM_ALLOWED_CHAT_ID=your_chat_id\n"
        "Use your numeric chat ID or @username (e.g. @lovey_xmol)"
    )

# Normalize chat ID — support both numeric IDs and @usernames
ALLOWED_CHAT_ID_STR = str(ALLOWED_CHAT_ID).strip()
ALLOWED_CHAT_ID_INT: int | None = None
try:
    if ALLOWED_CHAT_ID_STR.lstrip("-").isdigit():
        ALLOWED_CHAT_ID_INT = int(ALLOWED_CHAT_ID_STR)
except ValueError:
    pass


# ─── Security Gate ───────────────────────────────────────────────────────────

def _is_allowed(update: Update) -> bool:
    """Check if the message sender matches the configured ALLOWED_CHAT_ID."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False

    # 1. Numeric chat ID match
    if ALLOWED_CHAT_ID_INT is not None and chat.id == ALLOWED_CHAT_ID_INT:
        return True

    # 2. @username match
    if ALLOWED_CHAT_ID_STR.startswith("@"):
        if user.username and user.username.lower() == ALLOWED_CHAT_ID_STR[1:].lower():
            return True

    # 3. Numeric user ID match
    if ALLOWED_CHAT_ID_INT is not None and user.id == ALLOWED_CHAT_ID_INT:
        return True

    return False


# ─── Handlers ────────────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not _is_allowed(update):
        await update.message.reply_text("⛔ Unauthorized. This bot is private.")
        return

    await update.message.reply_text(
        "🤖 <b>BARQ Telegram Ingestion Bot</b>\n\n"
        "Send me a <b>job description</b> or a <b>URL</b> and I'll:\n"
        "1️⃣ Analyze it against your profile\n"
        "2️⃣ Calculate a match score\n"
        "3️⃣ Generate a tailored resume PDF\n"
        "4️⃣ Send it back to you\n\n"
        "<i>Processing takes 30–60 seconds. I'll keep you posted!</i>",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command — list supported formats and usage."""
    if not _is_allowed(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    await update.message.reply_text(
        "🤖 <b>BARQ Telegram Ingestion Bot — Help</b>\n\n"
        "<b>What I do:</b>\n"
        "I take a job description and generate a tailored resume PDF matched "
        "to your profile.\n\n"
        "<b>Supported input formats:</b>\n"
        "📝 <b>Plain text</b> — Paste any job description as a message\n"
        "🔗 <b>URL</b> — Send a job posting link (I'll scrape it with Playwright)\n"
        "📄 <b>PDF</b> — Upload a job description PDF (text or scanned — OCR supported)\n\n"
        "<b>What happens next:</b>\n"
        "1️⃣ I analyze your resume\n"
        "2️⃣ Match the job against your profile\n"
        "3️⃣ Tailor your resume for this specific role\n"
        "4️⃣ Generate a professional PDF resume\n"
        "5️⃣ Send it back with a match score\n\n"
        "<b>Commands:</b>\n"
        "/start — Show welcome message\n"
        "/help — This message\n\n"
        "<i>Processing takes 30–60 seconds. I'll update you at each step!</i>",
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages — job descriptions or URLs."""
    if not _is_allowed(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not update.message or not update.message.text:
        return

    job_text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # Acknowledge immediately so the user knows we're working
    await update.message.reply_text(
        "⚡ <b>Processing your request...</b>\n\n"
        "📥 Queuing pipeline...\n"
        "<i>This takes about 30–60 seconds. I'll update you at each step!</i>",
        parse_mode="HTML",
    )

    # Fire-and-forget: background task keeps the bot responsive
    asyncio.create_task(_process_job(chat_id, job_text, context))


async def handle_pdf_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming PDF documents — extract text and process as job description."""
    if not _is_allowed(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not update.message or not update.message.document:
        return

    chat_id = update.effective_chat.id
    document = update.message.document

    # Acknowledge immediately
    await update.message.reply_text(
        "📄 <b>PDF received! Extracting text...</b>\n\n"
        "📥 Queuing pipeline...\n"
        "<i>This takes about 30–60 seconds. I'll update you at each step!</i>",
        parse_mode="HTML",
    )

    # Fire-and-forget: background task
    asyncio.create_task(_process_pdf(chat_id, document, context))


# ─── Background Processor ────────────────────────────────────────────────────


async def _process_job(chat_id: int, job_text: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background task: run the full BARQ pipeline for a single job description."""
    try:
        # ── Step 1: Parse Resume ──────────────────────────────────────
        await context.bot.send_message(
            chat_id=chat_id,
            text="📖 <b>Step 1/5:</b> Loading your resume...",
            parse_mode="HTML",
        )
        resume = parse_resume()
        if resume.get("_error") or not resume.get("raw_md"):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ <b>Resume not found</b>\n\n"
                     "Please ensure your resume file exists at:\n"
                     f"<code>{resume.get('_path', '?')}</code>",
                parse_mode="HTML",
            )
            return
        resume_md = resume["raw_md"]

        # ── Step 2: Fetch or Use Raw Text ─────────────────────────────
        is_url = bool(re.match(r"https?://", job_text))
        if is_url:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🌐 <b>Step 2/5:</b> Fetching job from URL...",
                parse_mode="HTML",
            )
            job_description = await _scrape_job_url(job_text)
            if not job_description or len(job_description) < 100:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ <b>Could not extract job description</b>\n\n"
                         "The URL may be behind a login wall or blocked. "
                         "Try pasting the job description as plain text instead.",
                    parse_mode="HTML",
                )
                return
        else:
            job_description = job_text
            await context.bot.send_message(
                chat_id=chat_id,
                text="📝 <b>Step 2/5:</b> Job description captured ✓",
                parse_mode="HTML",
            )

        # Extract title / company for display
        job_title = _extract_job_title(job_description)
        company = _extract_company(job_description)
        safe_title = html.escape(job_title or "the position")
        safe_company = html.escape(company or "the company")

        # ── Step 3: Match ─────────────────────────────────────────────
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📊 <b>Step 3/5:</b> Analyzing match for <b>{safe_title}</b>... "
                 f"<i>(LLM evaluating...)</i>",
            parse_mode="HTML",
        )

        job_dict: dict[str, Any] = {
            "title": job_title or "Unknown Position",
            "company": company or "Unknown Company",
            "description": job_description,
        }

        matcher = JobMatcher()
        match_result = await matcher.match(job_dict, resume)
        match_pct = match_result.get("overall_score", 0)
        pros = match_result.get("matching_skills", []) or []
        cons = match_result.get("missing_skills", []) or []

        # ── Step 4: Optimise Resume ───────────────────────────────────
        await context.bot.send_message(
            chat_id=chat_id,
            text="📝 <b>Step 4/5:</b> Tailoring resume for this role... "
                 "<i>(LLM rewriting...)</i>",
            parse_mode="HTML",
        )

        match_analysis = {
            "matching_skills": pros[:5] if isinstance(pros, list) else [],
            "missing_skills": cons[:5] if isinstance(cons, list) else [],
        }
        optimizer = ResumeOptimizer()
        optimized = await optimizer.optimize(resume_md, job_dict, match_analysis)
        optimized_md = optimized.get("optimized_md", resume_md)

        # ── Step 5: Generate PDF ──────────────────────────────────────
        await context.bot.send_message(
            chat_id=chat_id,
            text="📄 <b>Step 5/5:</b> Generating PDF... <i>(compiling...)</i>",
            parse_mode="HTML",
        )

        pdf_gen = ResumePDFGenerator()
        pdf_resume_data = {**resume, "raw_md": optimized_md}
        slug = safe_filename(f"{company}_{job_title}".replace(" ", "_"), max_len=50) or "ingested"
        pdf_result = await pdf_gen.generate(
            pdf_resume_data,
            output_dir=str(GENERATED_DIR / f"telegram_{slug}"),
            filename=f"Resume_{slug}",
            job_description=job_description,
        )
        pdf_path = pdf_result.get("pdf_path", "")

        # ── Send PDF first ────────────────────────────────────────────
        pdf_sent = False
        if pdf_path and os.path.isfile(pdf_path):
            with open(pdf_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=os.path.basename(pdf_path),
                    caption=(
                        f"📄 <b>Tailored Resume</b>: {safe_title} @ {safe_company}"
                    ),
                    parse_mode="HTML",
                )
            pdf_sent = True

        # ── Send concise match summary ────────────────────────────────
        summary = (
            f"🎯 <b>Job Match: {safe_title}</b>\n"
            f"<b>{safe_company}</b>\n"
            f"📊 <b>Match Score:</b> {match_pct:.0f}%"
        )
        if pros:
            summary += "\n\n✅ <b>Strengths</b>"
            for p in pros[:3]:
                summary += f"\n  • {html.escape(str(p)[:120])}"
        if cons:
            summary += "\n\n⚠️ <b>Considerations</b>"
            for c in cons[:3]:
                summary += f"\n  • {html.escape(str(c)[:120])}"
        if pdf_sent:
            summary += "\n\n📎 <i>Tailored resume PDF attached above</i>"

        await context.bot.send_message(
            chat_id=chat_id,
            text=summary,
            parse_mode="HTML",
        )

        if pdf_sent:
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ <b>Done!</b> Send another job description or URL anytime.",
                parse_mode="HTML",
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ PDF generation had an issue, but the match analysis above is valid.",
                parse_mode="HTML",
            )

    except Exception as exc:
        logger.error("[TelegramIngestion] Background task failed", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Processing Error</b>\n\n{html.escape(str(exc)[:500])}",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def _process_pdf(
    chat_id: int,
    document: Any,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Background task: download a PDF, extract text, then delegate to the main pipeline."""
    try:
        # Download & extract text from the PDF
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📄 <b>Step 1:</b> Downloading PDF (<code>{html.escape(document.file_name or 'document.pdf')}</code>)...",
            parse_mode="HTML",
        )

        pdf_text = await _extract_pdf_text(document)
        if not pdf_text or len(pdf_text) < 50:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ <b>Could not extract text from PDF</b>\n\n"
                     "The PDF may be scanned (image-based) or encrypted. "
                     "Try pasting the job description as plain text instead.",
                parse_mode="HTML",
            )
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📝 <b>Step 2:</b> Extracted {len(pdf_text)} characters from PDF ✓. Running pipeline...",
            parse_mode="HTML",
        )

        # Delegate to the main pipeline (resume parse → match → optimize → PDF → send)
        await _process_job(chat_id, pdf_text, context)

    except Exception as exc:
        logger.error("[TelegramIngestion] PDF processing failed", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ <b>PDF Processing Error</b>\n\n{html.escape(str(exc)[:500])}",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _extract_job_title(text: str) -> str:
    """Guess the job title from the first few lines."""
    for line in text.strip().split("\n")[:6]:
        line = line.strip()
        if not line:
            continue
        m = re.search(
            r"(?i)(?:job\s*title|position|role|hiring|we are looking for(?: a| an)?)\s*:?\s*(.{3,60})",
            line,
        )
        if m:
            return m.group(1).strip()
    # Fallback: first non-empty line
    for line in text.strip().split("\n")[:3]:
        if line.strip():
            return line.strip()[:60]
    return "Unknown Position"


def _extract_company(text: str) -> str:
    """Guess the company name from the job description."""
    for line in text.strip().split("\n")[:12]:
        line = line.strip()
        m = re.search(r"(?i)(?:at|company|organization|employer|@)\s+([A-Z][A-Za-z0-9\s&.]+?)(?:\s|$|\.|,| for| –| —)", line)
        if m:
            return m.group(1).strip()[:60]
    return "Unknown Company"


async def _extract_pdf_text(document: Any) -> str:
    """Download a PDF document from Telegram and extract text content.

    Uses a 2-tier approach:
      1. pypdf — fast text extraction (works for text-based PDFs)
      2. PyMuPDF + pytesseract — OCR fallback (scanned/image-based PDFs)

    Requires Tesseract OCR engine installed for fallback:
      https://github.com/UB-Mannheim/tesseract/wiki
    """
    import tempfile

    tg_file = await document.get_file()

    # Download to a temp file
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            temp_path = tmp.name
            await tg_file.download_to_drive(temp_path)

        # ── Tier 1: pypdf (fast, text-based PDFs) ────────────────────
        from pypdf import PdfReader

        reader = PdfReader(temp_path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)

        full_text = "\n\n".join(pages_text)
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in full_text.split("\n")]
        full_text = "\n".join(line for line in lines if line).strip()

        # If pypdf got enough text, return it
        if len(full_text) >= 100:
            logger.info("[TelegramIngestion] pypdf extracted %d chars", len(full_text))
            return full_text[:4000]

        # ── Tier 2: OCR fallback for scanned/image-based PDFs ────────
        logger.info("[TelegramIngestion] pypdf only got %d chars — trying OCR fallback", len(full_text))
        ocr_text = await _ocr_pdf(temp_path)
        if ocr_text and len(ocr_text) >= 50:
            logger.info("[TelegramIngestion] OCR extracted %d chars", len(ocr_text))
            return ocr_text[:4000]

        # Both tiers failed
        logger.warning("[TelegramIngestion] PDF extraction failed (pypdf=%d chars, OCR=%d chars)",
                       len(full_text), len(ocr_text or ""))
        return ""

    except Exception as e:
        logger.warning("[TelegramIngestion] PDF text extraction failed: %s", e)
        return ""
    finally:
        if temp_path and os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


async def _ocr_pdf(pdf_path: str) -> str:
    """Extract text from a scanned/image-based PDF using PyMuPDF + pytesseract.

    Renders each page as a high-DPI image, then runs OCR via pytesseract.
    Returns empty string if Tesseract is not installed or OCR fails.
    """
    try:
        import fitz  # PyMuPDF
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.warning("[TelegramIngestion] OCR dependencies not installed (fitz or Pillow)")
        return ""

    try:
        all_text = []

        with fitz.open(pdf_path) as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]
                # Render page at 300 DPI for good OCR quality
                mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # Run tesseract OCR
                # If tesseract is not installed, pytesseract will raise TesseractNotFoundError
                text = pytesseract.image_to_string(img, lang="eng")
                if text:
                    all_text.append(text)

        full_text = "\n\n".join(all_text)
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in full_text.split("\n")]
        full_text = "\n".join(line for line in lines if line).strip()
        return full_text

    except Exception as e:
        err_str = str(e)
        if "TesseractNotFound" in err_str or "tesseract is not installed" in err_str.lower():
            logger.warning("[TelegramIngestion] Tesseract OCR engine not found. "
                          "Install from https://github.com/UB-Mannheim/tesseract/wiki")
        else:
            logger.warning("[TelegramIngestion] OCR failed on page: %s", err_str[:200])
        return ""


async def _scrape_job_url(url: str) -> str:
    """Scrape a job-posting URL using Playwright headless browser.

    Handles JavaScript-rendered pages (most job boards). Times out
    after 20 seconds and falls back to the simple regex approach.
    """
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
                locale="en-US",
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                # Wait a moment for any lazy-loaded content
                await page.wait_for_timeout(1500)
            except Exception:
                # Continue even if timeout — we still get whatever loaded
                pass

            # Extract visible text (not hidden elements, not scripts/styles)
            text = await page.evaluate("""() => {
                // Clone body to avoid modifying the live page
                const clone = document.body.cloneNode(true);
                // Remove hidden elements, scripts, styles
                const removals = clone.querySelectorAll(
                    'script, style, noscript, svg, '
                    + '[style*="display:none"], [style*="display: none"], '
                    + '[style*="visibility:hidden"], [hidden], '
                    + 'nav, footer, header, aside'
                );
                removals.forEach(el => el.remove());
                return clone.innerText || '';
            }""")

            await browser.close()

        # Clean up whitespace — condense multiple newlines, collapse horizontal whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line).strip()  # remove empty lines too
        # Keep first 4000 characters
        text = text[:4000]

        if len(text) > 100:
            logger.info("[TelegramIngestion] Playwright scraped %d chars from %s", len(text), url)
            return text

        # Playwright got too little content — fall through to regex fallback
        logger.warning("[TelegramIngestion] Playwright returned only %d chars, trying regex fallback", len(text))

    except ImportError:
        logger.warning("[TelegramIngestion] Playwright not installed, falling back to regex scraper")
    except Exception as e:
        logger.warning("[TelegramIngestion] Playwright scrape failed: %s", e)

    # ── Fallback: httpx + regex HTML stripping ──────────────────────
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            resp.raise_for_status()
            raw = resp.text

        # Simple HTML-to-text extraction
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:4000]
        return text if len(text) > 100 else ""

    except Exception as e:
        logger.warning("[TelegramIngestion] URL scrape fallback failed: %s", e)
        return ""


# ─── Error Handler ───────────────────────────────────────────────────────────


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log bot errors and notify the chat if possible (only for allowed users)."""
    logger.error("[TelegramIngestion] Bot error: %s", context.error, exc_info=True)
    # Only send error message to authorized users
    if update and _is_allowed(update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ <b>An unexpected error occurred.</b> Please try again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    """Start the Telegram ingestion bot (polling mode)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    print("=" * 50)
    print("🤖  BARQ Telegram Ingestion Bot")
    print("=" * 50)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf_document))
    app.add_error_handler(error_handler)

    print("  ✅ Bot started")
    print(f"  🔒 Allowed chat: {ALLOWED_CHAT_ID}")
    print("  📡 Waiting for job descriptions, URLs, or PDFs…")
    print("=" * 50)
    print()

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
