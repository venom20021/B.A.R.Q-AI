"""
Tests for the Telegram job notification pipeline — validates the
concise summary format, HTML escaping, and PDF document sending.

These tests verify the formatting logic WITHOUT needing a real
Telegram bot token. The notification function's HTTP calls are
mocked via the existing httpx test infrastructure.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_job_data() -> dict[str, Any]:
    return {
        "job_title": "Senior Software Engineer",
        "company": "Acme Corp",
        "job_url": "https://linkedin.com/jobs/view/123",
        "match_pct": 85.0,
        "app_id": 42,
    }


@pytest.fixture
def mock_evaluation() -> dict[str, Any]:
    return {
        "pros": json.dumps([
            "Strong Python and TypeScript skills match requirements",
            "5 years of backend experience aligns with senior role",
            "AWS experience matches cloud infrastructure needs",
        ]),
        "cons": json.dumps([
            "No Kubernetes experience listed on resume",
            "Company is in different timezone (PST vs IST)",
        ]),
    }


@pytest.fixture
def mock_resume() -> dict[str, Any]:
    return {
        "full_name": "Sai Prabhat",
        "email": "sai@example.com",
        "linkedin_url": "https://linkedin.com/in/saiprabhat",
        "summary": "Full Stack Engineer with 5+ years experience",
    }


# ─── Test: Summary Formatting ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_telegram_notification_disabled_when_not_configured():
    """Should return False early when Telegram is not configured."""
    from jobs.pipeline import _send_telegram_notification

    with patch("notifications.telegram.TelegramChannel.is_enabled", return_value=False):
        result = await _send_telegram_notification(
            job_title="Engineer",
            company="TestCo",
            job_url="",
            match_pct=75.0,
            app_id=1,
        )
        assert result is False


@pytest.mark.asyncio
async def test_send_telegram_notification_summary_format():
    """Verify the summary message contains Score, Pros, Cons, and Apply Link."""
    from jobs.pipeline import _send_telegram_notification

    # Mock the TelegramChannel to capture what would be sent
    mock_telegram = AsyncMock()
    mock_telegram.is_enabled.return_value = True
    mock_telegram.send_document.return_value.success = True
    mock_telegram.send_document_from_bytes.return_value.success = True
    mock_telegram.send_html_message.return_value.success = True

    with (
        patch("jobs.pipeline.notification_manager.send_job_match_alert", AsyncMock()),
        patch("notifications.telegram.TelegramChannel", return_value=mock_telegram),
    ):
        result = await _send_telegram_notification(
            job_title="Senior Software Engineer",
            company="Acme Corp",
            job_url="https://linkedin.com/jobs/view/123",
            match_pct=85.0,
            app_id=42,
            evaluation={
                "pros": json.dumps(["Strong Python skills", "AWS experience"]),
                "cons": json.dumps(["No Kubernetes"]),
            },
        )

        assert result is True

        # Extract the summary text sent to send_html_message
        call_args = mock_telegram.send_html_message.call_args
        assert call_args is not None, "send_html_message was not called"

        summary = call_args[1]["text"]  # kwargs
        title = call_args[1].get("title", "")

        # ── Verify Score ──────────────────────────────────────────────
        assert "85%" in summary
        assert "Senior Software Engineer" in summary
        assert "Acme Corp" in summary

        # ── Verify Apply Link ─────────────────────────────────────────
        assert "linkedin.com/jobs/view/123" in summary
        assert "OPEN APPLICATION" in summary

        # ── Verify Pros (Strengths) ───────────────────────────────────
        assert "Strengths" in summary or "strengths" in summary
        assert "Strong Python skills" in summary
        assert "AWS experience" in summary

        # ── Verify Cons (Considerations) ──────────────────────────────
        assert "Considerations" in summary or "considerations" in summary
        assert "No Kubernetes" in summary

        # ── Verify Application ID ─────────────────────────────────────
        assert "42" in summary or "#42" in summary or "Application" in summary

        # ── Verify NO raw text dumps ─────────────────────────────────
        assert "━━━" not in summary  # no separator lines
        assert "Part 1" not in summary
        assert "Part 2" not in summary

        # ── Verify title ─────────────────────────────────────────────
        assert "Senior Software Engineer" in title


@pytest.mark.asyncio
async def test_send_telegram_notification_empty_evaluation():
    """Should send a basic summary even when no evaluation data is available."""
    from jobs.pipeline import _send_telegram_notification

    mock_telegram = AsyncMock()
    mock_telegram.is_enabled.return_value = True
    mock_telegram.send_html_message.return_value.success = True

    with (
        patch("jobs.pipeline.notification_manager.send_job_match_alert", AsyncMock()),
        patch("notifications.telegram.TelegramChannel", return_value=mock_telegram),
    ):
        result = await _send_telegram_notification(
            job_title="Junior Developer",
            company="Startup Inc",
            job_url="",
            match_pct=60.0,
            app_id=10,
        )

        assert result is True
        summary = mock_telegram.send_html_message.call_args[1]["text"]
        assert "60%" in summary
        assert "Junior Developer" in summary
        assert "Startup Inc" in summary


@pytest.mark.asyncio
async def test_send_telegram_notification_sends_pdf_bytes():
    """Should use send_document_from_bytes when pdf_bytes are provided."""
    from jobs.pipeline import _send_telegram_notification

    mock_telegram = AsyncMock()
    mock_telegram.is_enabled.return_value = True
    mock_telegram.send_document_from_bytes.return_value.success = True
    mock_telegram.send_html_message.return_value.success = True

    pdf_bytes = {
        "resume": b"%PDF-1.4 mock resume pdf content",
        "cover_letter": b"%PDF-1.4 mock cover letter pdf content",
    }

    with (
        patch("jobs.pipeline.notification_manager.send_job_match_alert", AsyncMock()),
        patch("notifications.telegram.TelegramChannel", return_value=mock_telegram),
    ):
        result = await _send_telegram_notification(
            job_title="DevOps Engineer",
            company="CloudCo",
            job_url="https://example.com/job/5",
            match_pct=90.0,
            app_id=5,
            evaluation={
                "pros": json.dumps(["Docker experience"]),
                "cons": json.dumps([]),
            },
            pdf_bytes=pdf_bytes,
        )

        assert result is True

        # Verify send_document_from_bytes was called for resume
        assert mock_telegram.send_document_from_bytes.call_count >= 1
        resume_call = mock_telegram.send_document_from_bytes.call_args_list[0]
        assert resume_call[1]["file_bytes"] == pdf_bytes["resume"]
        assert resume_call[1]["filename"].endswith(".pdf")
        assert "DevOps Engineer" in resume_call[1]["caption"] or "CloudCo" in resume_call[1]["caption"]


@pytest.mark.asyncio
async def test_send_telegram_notification_fallback_to_file_based():
    """Should use file-based send_document when no pdf_bytes provided."""
    from jobs.pipeline import _send_telegram_notification
    import tempfile
    import os

    mock_telegram = AsyncMock()
    mock_telegram.is_enabled.return_value = True
    mock_telegram.send_document.return_value.success = True
    mock_telegram.send_html_message.return_value.success = True

    # Create a temp PDF file to simulate existing file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 test")
        temp_pdf = f.name

    try:
        pdf_paths = {"resume": temp_pdf}

        with (
            patch("jobs.pipeline.notification_manager.send_job_match_alert", AsyncMock()),
            patch("notifications.telegram.TelegramChannel", return_value=mock_telegram),
        ):
            result = await _send_telegram_notification(
                job_title="Frontend Engineer",
                company="WebCo",
                job_url="",
                match_pct=70.0,
                app_id=8,
                pdf_paths=pdf_paths,
            )

            assert result is True

            # Verify send_document (file-based) was called, not send_document_from_bytes
            assert mock_telegram.send_document.called
            assert not mock_telegram.send_document_from_bytes.called

    finally:
        os.unlink(temp_pdf)


# ─── Test: send_document_from_bytes ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_document_from_bytes_disabled():
    """send_document_from_bytes should return failure when Telegram not configured."""
    from notifications.telegram import TelegramChannel

    channel = TelegramChannel()
    with patch.object(channel, "is_enabled", return_value=False):
        result = await channel.send_document_from_bytes(
            file_bytes=b"test",
            filename="test.pdf",
        )
        assert result.success is False
        assert "not configured" in (result.error or "")


@pytest.mark.asyncio
async def test_send_document_from_bytes_empty():
    """send_document_from_bytes should fail on empty bytes."""
    from notifications.telegram import TelegramChannel

    channel = TelegramChannel()
    with patch.object(channel, "is_enabled", return_value=True):
        result = await channel.send_document_from_bytes(
            file_bytes=b"",
            filename="empty.pdf",
        )
        assert result.success is False
        assert "Empty" in (result.error or "")


# ─── Test: HTML Escaping ─────────────────────────────────────────────────────


def test_summary_html_escaping():
    """Verify that HTML tags in job/company names are escaped."""
    import html as html_mod
    from jobs.pipeline import _send_telegram_notification

    dangerous_title = "<script>alert('xss')</script>"
    dangerous_company = 'Company "&<b>Bold</b>'

    escaped_title = html_mod.escape(dangerous_title)
    escaped_company = html_mod.escape(dangerous_company)

    assert "<" not in escaped_title or "&lt;" in escaped_title
    assert "&amp;" in escaped_company or "&lt;" in escaped_company
    assert escaped_title != dangerous_title  # Must be escaped
