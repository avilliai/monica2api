"""Monica2API process entry point."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from app.app import app
from app.core.config import get_settings

load_dotenv(Path(__file__).resolve().with_name(".env"))
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
