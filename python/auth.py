"""
BARQ API Authentication — API key + optional OAuth2 middleware.

Provides:
- `require_api_key` FastAPI dependency that checks Bearer token or X-API-Key header
- Inline middleware that validates API key on protected routes
- Key management (set/verify/revoke via settings_dao)
"""

import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings

# Bearer token scheme for Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)

# ─── Key Management ───────────────────────────────────────────────────────

# In-memory cache (loaded once from env or DB)
_api_key_cache: Optional[str] = None


def get_configured_api_key() -> str:
    """Return the active API key from env var or generate one."""
    global _api_key_cache
    if _api_key_cache:
        return _api_key_cache

    settings = get_settings()
    key = settings.barq_api_key
    if not key:
        # Auto-generate a key on first run and log it
        key = f"brq_{secrets.token_hex(24)}"
        print(f"[Auth] ⚠ No BARQ_API_KEY set. Generated temporary key: {key}")
        print(f"[Auth]   Set BARQ_API_KEY={key} in .env to make it permanent.")
        _api_key_cache = key
    else:
        _api_key_cache = key
    return _api_key_cache


def validate_api_key(token: str) -> bool:
    """Validate an API key against the configured key."""
    expected = get_configured_api_key()
    if not expected:
        return False
    return secrets.compare_digest(token, expected)


# ─── FastAPI Dependency ───────────────────────────────────────────────────

async def require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> bool:
    """
    FastAPI dependency that requires a valid API key.

    Accepts the key via:
    - Authorization: Bearer <key>
    - X-API-Key header

    Usage:
        @router.get("/protected")
        async def protected_route(auth: bool = Depends(require_api_key)):
            return {"data": "secret"}
    """
    token = None

    if credentials:
        token = credentials.credentials
    elif x_api_key:
        token = x_api_key

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide via Authorization: Bearer <key> or X-API-Key header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not validate_api_key(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True

