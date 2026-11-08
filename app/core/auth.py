"""Bearer token authentication used by the OpenAI and admin routes."""

from __future__ import annotations

import hmac
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Header, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

load_dotenv()
security = HTTPBearer(auto_error=False)
API_KEY = os.getenv("API_KEY", "")


def _expected_key() -> str:
    return os.getenv("API_KEY", get_settings().api_key)


async def verify_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> str:
    """Validate an Authorization Bearer token or x-api-key header."""
    expected = _expected_key()
    if not expected:
        return "dev-mode"
    supplied = credentials.credentials if credentials else x_api_key
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return supplied


async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> None:
    """Route dependency alias used by the registration/admin endpoints."""
    await verify_bearer_token(credentials, x_api_key)
