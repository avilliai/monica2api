"""FastAPI application factory and service lifecycle."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.v1 import admin, chat, models, register
from app.core.config import get_settings, resolve_project_path
from app.core.exceptions import register_exception_handlers
from app.services.cookie_manager import CookieManager
from app.services.register import RegisterService
from app.services.account_warmer import AccountWarmer

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    manager = CookieManager(
        str(resolve_project_path(settings.cookie_file)),
        refresh_concurrency=settings.refresh_concurrency,
        max_probe_retries=settings.max_probe_retries,
        probe_retry_delay=settings.probe_retry_delay,
        daily_limit=settings.daily_quota_limit,
        quota_timezone=settings.daily_quota_timezone,
        consecutive_uses=settings.account_consecutive_uses,
    )
    await manager.load(probe=settings.startup_probe)
    register_service = RegisterService(settings, manager)
    app.state.cookie_manager = manager
    app.state.register_service = register_service

    # Genspark-style smooth account warmer (pre-warms upcoming accounts ahead of round-robin cursor)
    # Strictly avoids mass concurrent keep-alive bursts
    account_warmer = AccountWarmer(settings, manager)
    if settings.account_warmup_enabled:
        account_warmer.start()
    app.state.account_warmer = account_warmer

    quota_task: asyncio.Task | None = asyncio.create_task(
        manager.quota_reset_loop(), name="monica-daily-quota-reset"
    )
    logger.info("Monica2API started: %s", manager.summary())
    try:
        yield
    finally:
        await account_warmer.stop()
        await register_service.close()
        if quota_task:
            quota_task.cancel()
            with suppress(asyncio.CancelledError):
                await quota_task
        logger.info("Monica2API stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Monica2API",
        description="Monica registration, cookie pooling and OpenAI-compatible chat API",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("HTTP request failed: %s %s", request.method, request.url.path)
            raise
        logger.info(
            "%s %s -> %s (%.3fs)",
            request.method,
            request.url.path,
            response.status_code,
            time.perf_counter() - started,
        )
        return response

    app.include_router(chat.router, prefix="/v1", tags=["chat"])
    app.include_router(models.router, prefix="/v1", tags=["models"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(register.router)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/admin/dashboard")

    @app.get("/health", tags=["health"])
    async def health():
        manager = getattr(app.state, "cookie_manager", None)
        if manager is None:
            return {
                "status": "ok",
                "service": "monica2api",
                "ready": False,
                "accounts": {"total": 0, "alive": 0, "disabled": 0, "dead": 0},
            }
        summary = manager.summary()
        return {
            "status": "ok",
            "service": "monica2api",
            "ready": summary["alive"] > 0,
            "accounts": summary,
            "cookie_file": str(manager.file_path),
        }

    register_exception_handlers(app)
    return app


app = create_app()


