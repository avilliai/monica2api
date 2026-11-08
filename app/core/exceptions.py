"""Global exceptions and handlers."""

from __future__ import annotations

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class CookieExhaustedException(AppException):
    def __init__(self, message: str = "All cookies exhausted or invalid"):
        super().__init__(message, status_code=429)


class MonicaAPIException(AppException):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message, status_code)


class MonicaUpstreamServerException(MonicaAPIException):
    """Raised when Monica upstream returns internal server errors (such as 1011).
    This indicates upstream service/model failure, NOT account credential invalidation.
    """
    def __init__(self, message: str, status_code: int = 502, err_code: str | int | None = None):
        super().__init__(message, status_code)
        self.err_code = err_code


class MonicaQuotaExceededException(MonicaAPIException):
    def __init__(self, message: str = "Monica account quota exceeded", status_code: int = 429):
        super().__init__(message, status_code)


class MonicaSafetyRefusalException(MonicaAPIException):
    def __init__(self, message: str = "Sorry, I can't help with content that goes against safety guidelines.", status_code: int = 200, raw_error: dict | None = None):
        super().__init__(message, status_code)
        self.raw_error = raw_error


class RegistrationError(AppException):
    def __init__(self, message: str = "Registration error", status_code: int = 500):
        super().__init__(message, status_code)


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "type": "app_error",
                    "code": exc.status_code
                }
            }
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": str(exc.detail),
                    "type": "http_error",
                    "code": exc.status_code
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": "Validation error",
                    "type": "validation_error",
                    "code": 422,
                    "details": exc.errors()
                }
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "type": "internal_error",
                    "code": 500
                }
            }
        )
