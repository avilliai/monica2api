"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _csv(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [part.strip() for part in value.split(",") if part.strip()]


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


DEFAULT_FALLBACK_MODEL = os.getenv("DEFAULT_FALLBACK_MODEL", "gemini-3-flash")

DEFAULT_MODELS = [
    "gemini-3-flash",
    "gpt-6-luna",
    "deepseek-v4.1-flash",
    "gemini-3.5-flash-lite",
    "qwen3.8-flash",
    "glm-5.3-flash",
    "gemini-3.1-flash-lite",
    "claude-haiku-5-5",
]


@dataclass(slots=True)
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("PORT", 8017))
    reload: bool = field(default_factory=lambda: _bool("RELOAD", False))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))

    cookie_file: str = field(
        default_factory=lambda: os.getenv("COOKIE_FILE", "data/cookies.json")
    )
    keep_alive_minutes: int = field(
        default_factory=lambda: _int("KEEP_ALIVE_MINUTES", 30)
    )
    startup_probe: bool = field(
        default_factory=lambda: _bool("COOKIE_STARTUP_PROBE", False)
    )
    refresh_concurrency: int = field(
        default_factory=lambda: max(1, _int("REFRESH_CONCURRENCY", 10))
    )
    max_probe_retries: int = field(
        default_factory=lambda: max(1, _int("MAX_PROBE_RETRIES", 3))
    )
    probe_retry_delay: float = field(
        default_factory=lambda: max(0.0, _float("PROBE_RETRY_DELAY", 1.0))
    )

    daily_quota_limit: int = field(
        default_factory=lambda: max(1, _int("DAILY_QUOTA_LIMIT", 40))
    )
    daily_quota_timezone: str = field(
        default_factory=lambda: os.getenv("DAILY_QUOTA_TIMEZONE", "Asia/Shanghai")
    )
    request_timeout: float = field(
        default_factory=lambda: max(1.0, _float("MONICA_TIMEOUT", 180.0))
    )
    chat_max_retries: int = field(
        default_factory=lambda: max(1, _int("CHAT_MAX_RETRIES", 2))
    )
    max_messages: int = field(
        default_factory=lambda: max(0, _int('MAX_MESSAGES', _int('MAX_CHAT_MESSAGES', 0)))
    )
    safety_max_retries: int = field(
        default_factory=lambda: max(1, _int("SAFETY_MAX_RETRIES", 2))
    )
    custom_bot_enabled: bool = field(
        default_factory=lambda: _bool("ENABLE_CUSTOM_BOT_MODE", False)
    )
    bot_uid: str = field(default_factory=lambda: os.getenv("BOT_UID", ""))
    monica_api_backend: str = field(
        default_factory=lambda: os.getenv("MONICA_API_BACKEND", "httpx").strip().lower()
    )
    curl_impersonate: str = field(
        default_factory=lambda: os.getenv("CURL_IMPERSONATE", "chrome131")
    )
    strict_model_validation: bool = field(
        default_factory=lambda: _bool("STRICT_MODEL_VALIDATION", True)
    )
    default_fallback_model: str = field(default_factory=lambda: DEFAULT_FALLBACK_MODEL)
    available_models: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))

    # Account rotation policy (consecutive usage per account before rotating)
    account_consecutive_uses: int = field(
        default_factory=lambda: max(1, _int("ACCOUNT_CONSECUTIVE_USES", _int("CONSECUTIVE_REQUESTS_PER_ACCOUNT", 1)))
    )

    # Account warmer settings (smooth pre-heating, no bulk bursts)
    account_warmup_enabled: bool = field(
        default_factory=lambda: _bool("ACCOUNT_WARMUP_ENABLED", True)
    )
    warmup_ahead_count: int = field(
        default_factory=lambda: max(1, _int("WARMUP_AHEAD_COUNT", 2))
    )
    warmup_interval_seconds: float = field(
        default_factory=lambda: max(5.0, _float("WARMUP_INTERVAL_SECONDS", 60.0))
    )
    warmup_token_ttl_seconds: float = field(
        default_factory=lambda: max(60.0, _float("WARMUP_TOKEN_TTL_SECONDS", 1800.0))
    )


    # Registration settings
    monica_signup_url: str = field(
        default_factory=lambda: os.getenv(
            "MONICA_SIGNUP_URL",
            "https://monica.im/sign-up?redirectTo=https%3A%2F%2Fmonica.im%2Fhome",
        )
    )
    register_browser_backend: str = field(
        default_factory=lambda: os.getenv("REGISTER_BROWSER_BACKEND", "camoufox")
        .strip()
        .lower()
    )
    camoufox_headless: bool = field(
        default_factory=lambda: _bool("CAMOUFOX_HEADLESS", True)
    )
    camoufox_humanize: bool = field(
        default_factory=lambda: _bool("CAMOUFOX_HUMANIZE", True)
    )
    camoufox_locale: str = field(
        default_factory=lambda: os.getenv("CAMOUFOX_LOCALE", "en-US")
    )
    camoufox_timeout: int = field(
        default_factory=lambda: _int("CAMOUFOX_TIMEOUT", 120)
    )
    register_concurrency: int = field(
        default_factory=lambda: max(1, _int("REGISTER_CONCURRENCY", 1))
    )
    register_proxy_file: str = field(
        default_factory=lambda: os.getenv("REGISTER_PROXY_FILE", "Webshare 10 proxies.txt")
    )
    register_output_file: str = field(
        default_factory=lambda: os.getenv(
            "REGISTER_OUTPUT_FILE", "register/monica_accounts.json"
        )
    )

    # Mailbox configuration (Outlook or Worker)
    email_mode: str = field(
        default_factory=lambda: os.getenv("EMAIL_MODE", "outlook").strip().lower()
    )
    outlook_account_file: str = field(
        default_factory=lambda: os.getenv("OUTLOOK_ACCOUNT_FILE", "OUT-20260728-S1000-00082_Filtered.txt")
    )
    outlook_blacklist_file: str = field(
        default_factory=lambda: os.getenv("OUTLOOK_BLACKLIST_FILE", "data/outlook_email_blacklist.json")
    )
    outlook_token_url: str = field(
        default_factory=lambda: os.getenv("OUTLOOK_TOKEN_URL", "https://login.microsoftonline.com/common/oauth2/v2.0/token")
    )
    outlook_graph_url: str = field(
        default_factory=lambda: os.getenv("OUTLOOK_GRAPH_URL", "https://graph.microsoft.com/v1.0")
    )
    outlook_imap_hosts: list[str] = field(
        default_factory=lambda: _csv("OUTLOOK_IMAP_HOSTS", "outlook.office365.com,outlook.live.com,imap-mail.outlook.com")
    )
    outlook_imap_port: int = field(
        default_factory=lambda: _int("OUTLOOK_IMAP_PORT", 993)
    )
    outlook_imap_timeout: float = field(
        default_factory=lambda: _float("OUTLOOK_IMAP_TIMEOUT", 30.0)
    )
    worker_domain: str = field(
        default_factory=lambda: os.getenv("WORKER_DOMAIN", "")
    )
    email_domain: str = field(
        default_factory=lambda: os.getenv("EMAIL_DOMAIN", "")
    )
    admin_password: str = field(
        default_factory=lambda: os.getenv("ADMIN_PASSWORD", "")
    )
    email_scheme: str = field(
        default_factory=lambda: os.getenv("EMAIL_SCHEME", "https")
    )
    email_poll_timeout: int = field(
        default_factory=lambda: _int("POLL_TIMEOUT", _int("EMAIL_POLL_TIMEOUT", 120))
    )
    email_poll_interval: int = field(
        default_factory=lambda: _int("POLL_INTERVAL", _int("EMAIL_POLL_INTERVAL", 3))
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
