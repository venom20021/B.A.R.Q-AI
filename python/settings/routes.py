"""
FastAPI routes for user-facing settings management.
Provides endpoints for cloud LLM configuration that can be
saved/loaded via the Settings UI.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import settings_dao

router = APIRouter()

SETTINGS_CATEGORY = "cloud_llm"


# ─── Models ──────────────────────────────────────────────────────────────────


class CloudLLMSettingsRequest(BaseModel):
    enabled: bool = True
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/settings/cloud-llm", summary="Get cloud LLM settings")
async def get_cloud_llm_settings():
    """Get current cloud LLM configuration from the database."""
    try:
        enabled_raw = await settings_dao.get_setting("cloud_llm_enabled")
        api_key = await settings_dao.get_setting("cloud_llm_api_key")
        model = await settings_dao.get_setting("cloud_llm_model")
        base_url = await settings_dao.get_setting("cloud_llm_base_url")

        return {
            "enabled": enabled_raw == "true" if enabled_raw else True,
            "has_api_key": bool(api_key),
            "api_key_masked": (
                api_key[:8] + "..." + api_key[-4:]
                if api_key and len(api_key) > 12
                else ("*" * min(len(api_key), 8) if api_key else "")
            ),
            "model": model or "gpt-4o-mini",
            "base_url": base_url or "https://api.openai.com/v1",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/cloud-llm", summary="Save cloud LLM settings")
async def save_cloud_llm_settings(request: CloudLLMSettingsRequest):
    """Save cloud LLM configuration to the database."""
    try:
        await settings_dao.set_setting(
            "cloud_llm_enabled", str(request.enabled).lower(), SETTINGS_CATEGORY
        )
        if request.api_key:
            await settings_dao.set_setting(
                "cloud_llm_api_key", request.api_key, SETTINGS_CATEGORY
            )
        if request.model:
            await settings_dao.set_setting(
                "cloud_llm_model", request.model, SETTINGS_CATEGORY
            )
        if request.base_url:
            await settings_dao.set_setting(
                "cloud_llm_base_url", request.base_url, SETTINGS_CATEGORY
            )
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
