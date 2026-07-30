"""
Clipboard Intelligence — AI action endpoints.

Provides REST endpoints for the clipboard floating widget AI actions:
- Translate: Detect language → translate to English (or specified target)
- Summarize: Condense long text into key points
- Explain: Explain complex concepts in simple terms
- Fix: Fix grammar, spelling, and clarity

All actions use the configured LLM (Gemini / Ollama) via the responder.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("barq.clipboard")

router = APIRouter()


# ─── Request/Response Models ──────────────────────────────────────────────


class ClipboardActionRequest(BaseModel):
    action: str = Field(..., pattern="^(translate|summarize|explain|fix)$")
    text: str = Field(..., min_length=1, max_length=10000)
    target_language: Optional[str] = "English"


class ClipboardActionResponse(BaseModel):
    status: str
    result: str = ""
    detail: str = ""


# ─── Action System Prompts ────────────────────────────────────────────────

_ACTION_PROMPTS: dict[str, str] = {
    "translate": (
        "You are a professional translator. Translate the following text to {target_language}. "
        "Preserve the original tone and formatting. Return ONLY the translated text, nothing else.\n\n"
        "TEXT:\n{text}"
    ),
    "summarize": (
        "You are an expert summarizer. Summarize the following text into 3-5 concise bullet points. "
        "Capture the key information, main arguments, and important conclusions. "
        "Return ONLY the bullet points, nothing else.\n\n"
        "TEXT:\n{text}"
    ),
    "explain": (
        "You are a brilliant teacher who explains complex topics simply. "
        "Explain the following text in simple, easy-to-understand terms. "
        "Break down any jargon, provide examples, and ensure clarity. "
        "Keep it concise but thorough.\n\n"
        "TEXT:\n{text}"
    ),
    "fix": (
        "You are a professional editor. Fix all grammar, spelling, punctuation, and clarity issues "
        "in the following text. Preserve the original meaning and style. "
        "Return ONLY the corrected text, nothing else.\n\n"
        "TEXT:\n{text}"
    ),
}


# ─── Helper: call LLM ────────────────────────────────────────────────────


async def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    """Route a prompt to the configured LLM (Gemini or Ollama)."""
    try:
        from config import get_settings

        cfg = get_settings()

        # Try Gemini first
        gemini_key = cfg.gemini_api_key or ""
        if gemini_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel("gemini-2.0-flash-lite")
                response = await model.generate_content_async(prompt)
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini clipboard action failed: {e}")

        # Fallback to Ollama
        try:
            from utils.ollama_client import query_ollama

            result = await query_ollama(
                prompt=prompt,
                model=cfg.ollama_model or "llama3.2",
                max_tokens=max_tokens,
            )
            return result.strip()
        except Exception as e:
            logger.warning(f"Ollama clipboard action failed: {e}")

        # No LLM available
        return "⚠️ No AI backend available. Configure Gemini API key in Settings."

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return f"⚠️ Error: {e}"


# ─── Endpoints ────────────────────────────────────────────────────────────


@router.post("/clipboard/action", summary="Run an AI action on clipboard text")
async def run_clipboard_action(request: ClipboardActionRequest):
    """Run an AI action (translate, summarize, explain, fix) on the provided text."""
    try:
        prompt_template = _ACTION_PROMPTS.get(request.action)
        if not prompt_template:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        prompt = prompt_template.format(
            text=request.text,
            target_language=request.target_language or "English",
        )

        result = await _call_llm(prompt)

        return ClipboardActionResponse(
            status="ok",
            result=result,
            detail=f"Action '{request.action}' completed",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clipboard action '{request.action}' failed: {e}")
        return ClipboardActionResponse(
            status="error",
            detail=str(e),
        )


@router.get("/clipboard/actions", summary="List available clipboard AI actions")
async def list_clipboard_actions():
    """Return the list of available AI actions with descriptions."""
    return {
        "actions": [
            {"id": "translate", "label": "Translate", "icon": "🌐",
             "description": "Translate text to another language"},
            {"id": "summarize", "label": "Summarize", "icon": "📝",
             "description": "Condense long text into key bullet points"},
            {"id": "explain", "label": "Explain", "icon": "💡",
             "description": "Explain complex topics in simple terms"},
            {"id": "fix", "label": "Fix", "icon": "🔧",
             "description": "Fix grammar, spelling, and clarity issues"},
        ]
    }
