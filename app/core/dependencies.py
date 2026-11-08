"""FastAPI state dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.core.auth import verify_bearer_token
from app.services.cookie_manager import CookieManager


async def get_cookie_manager(request: Request) -> CookieManager:
    manager = getattr(request.app.state, "cookie_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Cookie manager service is initializing or not ready")
    return manager


async def get_register_service(request: Request):
    service = getattr(request.app.state, "register_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Register service is initializing or not ready")
    return service


async def get_auth_token(token: str = Depends(verify_bearer_token)) -> str:
    return token
