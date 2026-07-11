"""
FastAPI routes for API key and authentication management.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import get_configured_api_key, require_api_key, validate_api_key

router = APIRouter()


class ApiKeyStatus(BaseModel):
    configured: bool
    key_preview: str = ""


@router.get("/auth/status")
async def auth_status(auth: bool = Depends(require_api_key)):
    """Check if API auth is configured and return key info."""
    key = get_configured_api_key()
    return {
        "configured": bool(key),
        "auth_required": True,
        "key_preview": f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "set",
    }


@router.post("/auth/verify")
async def verify_api_key_route(x_api_key: str):
    """Verify a given API key is valid."""
    is_valid = validate_api_key(x_api_key)
    return {
        "valid": is_valid,
        "message": "API key is valid" if is_valid else "Invalid API key",
    }


@router.get("/auth/check")
async def check_auth_status():
    """Public endpoint to check if auth is required and get a hint."""
    key = get_configured_api_key()
    return {
        "auth_required": True,
        "configured": bool(key),
        "hint": "Use Authorization: Bearer <key> or X-API-Key header from your .env BARQ_API_KEY",
    }
