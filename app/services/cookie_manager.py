"""Persistent Monica cookie pool with round-robin scheduling and probing."""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

try:
    from curl_cffi.requests import AsyncSession
except ImportError:  # API-only installs can still import the application.
    AsyncSession = None  # type: ignore[assignment]

from fastapi import HTTPException

logger = logging.getLogger(__name__)

USAGE_URLS = (
    "https://api.monica.im/api/user/info",
    "https://api.monica.im/api/user/me",
)
QUOTA_MODULES = [
    "basic_query", "genius_bot", "credits", "image_translate",
    "ai_content_detect", "reading_pdf", "screenshot_qa",
    "web_search", "youtube_summarize", "image_gen", "bypass",
    "podcast", "mindmap", "audio_transcription", "batch_processor",
]
PROBE_ENDPOINTS = (
    ("POST", "https://api.monica.im/api/usagev2/get_quotas", {"modules": QUOTA_MODULES}),
    ("GET", "https://api.monica.im/api/user/me", None),
)
BASE_HEADERS = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "origin": "https://monica.im",
    "referer": "https://monica.im/",
    "content-type": "application/json",
    "x-client-type": "web",
    "x-client-version": os.getenv("MONICA_CLIENT_VERSION", "5.4.3"),
    "x-client-locale": os.getenv("MONICA_CLIENT_LOCALE", "zh_CN"),
    "x-product-name": "Monica",
    "x-time-zone": f"{os.getenv('MONICA_TIMEZONE', 'Etc/GMT-8')};-480",
    "user-agent": os.getenv(
        "MONICA_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    ),
}


def parse_cookie_header(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        name, item = part.split("=", 1)
        name = name.strip()
        if name:
            result[name] = item.strip()
    return result


def cookie_header(value: dict[str, str] | str) -> str:
    if isinstance(value, str):
        return value.strip()
    return "; ".join(f"{key}={item}" for key, item in value.items())


class CookieManager:
    """Manage persisted Monica sessions.

    The on-disk format remains compatible with the original project::

        [{"email": "...", "password": "...", "cookie": "..."}]

    Runtime metadata (health, failures and timestamps) is intentionally kept
    in memory and is written only when a state change needs to survive a
    restart.
    """

    def __init__(
        self,
        file_path: str = "data/cookies.json",
        *,
        refresh_concurrency: int | None = None,
        max_probe_retries: int | None = None,
        probe_retry_delay: float | None = None,
        daily_limit: int | None = None,
        quota_timezone: str | None = None,
        consecutive_uses: int | None = None,
    ):
        self.file_path = str(file_path)
        self.cookies: list[dict[str, Any]] = []
        self.current_index = 0
        self.consecutive_uses = max(
            1,
            consecutive_uses
            if consecutive_uses is not None
            else int(os.getenv("ACCOUNT_CONSECUTIVE_USES", os.getenv("CONSECUTIVE_REQUESTS_PER_ACCOUNT", "1"))),
        )
        self._current_account_uses = 0
        self.lock = asyncio.Lock()
        self._file_lock = asyncio.Lock()
        self._next_id = 1
        self.refresh_concurrency = max(
            1,
            refresh_concurrency
            if refresh_concurrency is not None
            else int(os.getenv("REFRESH_CONCURRENCY", "10")),
        )
        self.max_probe_retries = max(
            1,
            max_probe_retries
            if max_probe_retries is not None
            else int(os.getenv("MAX_PROBE_RETRIES", "3")),
        )
        self.probe_retry_delay = max(
            0.0,
            probe_retry_delay
            if probe_retry_delay is not None
            else float(os.getenv("PROBE_RETRY_DELAY", "1")),
        )
        self.failure_limit = max(1, int(os.getenv("COOKIE_FAILURE_LIMIT", "3")))
        self.daily_limit = max(1, int(daily_limit if daily_limit is not None else os.getenv("DAILY_QUOTA_LIMIT", "40")))
        self.quota_timezone = quota_timezone or os.getenv("DAILY_QUOTA_TIMEZONE", "Asia/Shanghai")
        self._file_signature: tuple[int, int] | None = None
        self._warmup_notifier = None

    def _timezone(self):
        """Resolve IANA zones on minimal Windows Python installations."""
        try:
            return ZoneInfo(self.quota_timezone)
        except Exception:
            name = self.quota_timezone.strip().lower()
            if name in {"asia/shanghai", "asia/chongqing", "asia/beijing", "etc/gmt-8", "utc+8"}:
                return timezone(timedelta(hours=8))
            return timezone.utc

    def _today(self) -> str:
        return datetime.now(self._timezone()).date().isoformat()
    @staticmethod
    def _parent(path: str | Path) -> Path:
        return Path(path).expanduser().parent

    @staticmethod
    def _signature(path: str | Path) -> tuple[int, int] | None:
        try:
            stat = Path(path).stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _make_entry(
        self,
        email: str,
        password: str,
        cookie: str,
        *,
        disabled: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(metadata or {})
        metadata.setdefault("client_id", os.getenv("MONICA_CLIENT_ID") or str(uuid.uuid4()))
        metadata.setdefault("user_agent", BASE_HEADERS["user-agent"])
        try:
            limit = min(self.daily_limit, max(1, int(metadata.get("daily_limit", self.daily_limit))))
        except (TypeError, ValueError):
            limit = self.daily_limit
        try:
            used = max(0, int(metadata.get("daily_used", 0)))
        except (TypeError, ValueError):
            used = 0
        quota_date = str(metadata.get("quota_date") or self._today())
        entry = {
            "id": self._next_id,
            "email": email,
            "password": password,
            "cookie": cookie.strip(),
            "is_alive": bool(cookie.strip()) and not disabled,
            "disabled": disabled,
            "failures": 0,
            "last_error": "",
            "last_checked_at": None,
            "last_used_at": None,
            "created_at": int(time.time()),
            "daily_limit": limit,
            "daily_used": used,
            "quota_date": quota_date,
            "metadata": metadata,
        }
        self._next_id += 1
        return entry

    def _normalise_item(self, item: dict[str, Any]) -> tuple[str, str, str, bool, dict[str, Any]]:
        email = str(item.get("email") or "").strip()
        password = str(item.get("password") or "").strip()
        value = item.get("cookie")
        if value is None:
            value = item.get("cookies")
        if isinstance(value, dict):
            cookie = cookie_header({str(k): str(v) for k, v in value.items()})
        else:
            cookie = str(value or item.get("cookie_header") or "").strip()
        if not email and cookie:
            # Stable synthetic label for cookie-only imports.
            email = "cookie-" + hashlib.sha256(cookie.encode()).hexdigest()[:16]
        disabled = bool(item.get("disabled", False))
        metadata = dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {}
        for key in (
            "client_id", "user_agent", "jwt_token", "nickname",
            "daily_limit", "daily_used", "quota_date",
        ):
            if key in item and item.get(key) is not None:
                metadata[key] = item[key]
        return email, password, cookie, disabled, metadata

    def _persistent_snapshot(self) -> list[dict[str, Any]]:
        snapshot: list[dict[str, Any]] = []
        for entry in self.cookies:
            item = {
                "email": entry.get("email", ""),
                "password": entry.get("password", ""),
                "cookie": entry.get("cookie", ""),
                "disabled": bool(entry.get("disabled", False)),
                "daily_limit": int(entry.get("daily_limit", self.daily_limit) or self.daily_limit),
                "daily_used": int(entry.get("daily_used", 0) or 0),
                "quota_date": entry.get("quota_date") or self._today(),
            }
            if entry.get("metadata"):
                item["metadata"] = entry["metadata"]
            snapshot.append(item)
        return snapshot
    async def _write_snapshot(self, snapshot: list[dict[str, Any]]) -> None:
        path = Path(self.file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        async with self._file_lock:
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporary, path)
            self._file_signature = self._signature(path)

    async def _write_file_async(self) -> None:
        async with self.lock:
            snapshot = self._persistent_snapshot()
        await self._write_snapshot(snapshot)

    async def load(self, probe: bool = True) -> None:
        path = Path(self.file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            await self._write_snapshot([])
            async with self.lock:
                self.cookies = []
                self.current_index = 0
            return

        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid cookie file JSON: {exc}") from exc
        if isinstance(raw, dict):
            raw = raw.get("cookies") or raw.get("accounts") or []
        if not isinstance(raw, list):
            raise ValueError("Cookie file must contain a JSON array")

        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        self._next_id = 1
        for item in raw:
            if not isinstance(item, dict):
                continue
            email, password, cookie, disabled, metadata = self._normalise_item(item)
            if not email:
                continue
            key = email.casefold()
            if key in seen:
                continue
            seen.add(key)
            entry = self._make_entry(
                email, password, cookie, disabled=disabled, metadata=metadata
            )
            # A non-empty persisted cookie is usable immediately.  Probing can
            # later downgrade it, but startup does not create a needless outage.
            entry["is_alive"] = bool(cookie) and not disabled
            entries.append(entry)

        async with self.lock:
            self.cookies = entries
            self.current_index = 0
            self._file_signature = self._signature(path)
        # Apply a missed midnight reset immediately on startup/reload.
        await self.reset_daily_quotas(force=False)
        if probe:
            await self.refresh_all()

    async def reload_if_changed(self) -> bool:
        signature = self._signature(self.file_path)
        if signature == self._file_signature:
            return False
        await self.load(probe=False)
        return True

    async def _probe(self, entry: dict[str, Any], session: Any) -> str:
        cookie = str(entry.get("cookie") or "").strip()
        if not cookie:
            entry["is_alive"] = False
            entry["last_checked_at"] = int(time.time())
            return "dead"

        last_error = ""
        for attempt in range(1, self.max_probe_retries + 1):
            try:
                headers = {**BASE_HEADERS, "cookie": cookie}
                metadata = entry.get("metadata") or {}
                if metadata.get("client_id"):
                    headers["x-client-id"] = str(metadata["client_id"])
                if metadata.get("user_agent"):
                    headers["user-agent"] = str(metadata["user_agent"])
                result = None
                for method, url, payload in PROBE_ENDPOINTS:
                    if method == "POST":
                        result = await session.post(
                            url, headers=headers, json=payload, timeout=10
                        )
                    else:
                        result = await session.get(url, headers=headers, timeout=10)
                    if getattr(result, "status_code", 0) in (200, 401, 403):
                        break
                status = getattr(result, "status_code", 0)
                if status in (401, 403):
                    entry["is_alive"] = False
                    entry["last_error"] = f"HTTP {status}"
                    entry["last_checked_at"] = int(time.time())
                    return "dead"
                if status == 200:
                    try:
                        data = result.json()
                    except Exception:
                        data = {}
                    if _looks_authenticated(data):
                        quota = _extract_basic_query_quota(data)
                        mod_quotas = _extract_module_quotas(data)
                        if quota:
                            entry.setdefault("metadata", {})["basic_query_quota"] = quota
                        if mod_quotas:
                            entry.setdefault("metadata", {})["module_quotas"] = mod_quotas
                        # Self-healing: if basic_query has remaining quota but daily_used was marked exhausted, restore it
                        if quota and (quota.get("current") or 0) > 0:
                            limit = int(entry.get("daily_limit", self.daily_limit) or self.daily_limit)
                            if int(entry.get("daily_used", 0) or 0) >= limit:
                                logger.info(
                                    "Account %s self-healed: upstream has %s quota, resetting daily_used to 0",
                                    entry.get("email") or entry.get("id"),
                                    quota.get("current"),
                                )
                                entry["daily_used"] = 0
                                entry["last_error"] = ""
                        entry["is_alive"] = not entry.get("disabled", False)
                        entry["failures"] = 0
                        entry["last_error"] = ""
                        entry["last_checked_at"] = int(time.time())
                        return "ok"
                    last_error = f"business response: {data}"
                else:
                    last_error = f"HTTP {status}"
            except Exception as exc:  # transient network errors preserve state
                last_error = str(exc)
            if attempt < self.max_probe_retries:
                await asyncio.sleep(self.probe_retry_delay)
        entry["last_checked_at"] = int(time.time())
        entry["last_error"] = last_error[:300]
        return "skip"

    async def _session(self):
        backend = os.getenv("MONICA_API_BACKEND", "httpx").strip().lower()
        if backend == "curl_cffi" and AsyncSession is not None:
            return AsyncSession(
                impersonate=os.getenv("CURL_IMPERSONATE", "chrome131"),
                proxy=(os.getenv("PROXY") or "").strip(),
            )
        try:
            import httpx

            proxy = (os.getenv("PROXY") or "").strip() or None
            return httpx.AsyncClient(proxy=proxy, trust_env=True, timeout=15.0)
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install httpx or curl-cffi to probe cookies") from exc

    async def _run_refresh(self, targets: Iterable[dict[str, Any]], label: str) -> dict[str, int]:
        target_list = list(targets)
        counts = {"total": len(target_list), "ok": 0, "dead": 0, "skip": 0}
        semaphore = asyncio.Semaphore(self.refresh_concurrency)

        async def one(entry: dict[str, Any]) -> None:
            async with semaphore:
                session = await self._session() if entry.get("cookie") else None
                try:
                    result = await self._probe(entry, session)
                    counts[result] = counts.get(result, 0) + 1
                finally:
                    if session is not None:
                        close = getattr(session, "aclose", None) or getattr(session, "close", None)
                        if close:
                            value = close()
                            if asyncio.iscoroutine(value):
                                await value

        await asyncio.gather(*(one(entry) for entry in target_list))
        if target_list:
            await self._write_file_async()
        logger.info("Cookie refresh %s: %s", label, counts)
        return counts

    async def refresh_all(self, concurrency: int | None = None) -> dict[str, int]:
        if concurrency is not None:
            old = self.refresh_concurrency
            self.refresh_concurrency = max(1, concurrency)
        else:
            old = None
        try:
            async with self.lock:
                targets = [entry for entry in self.cookies if not entry.get("disabled")]
            return await self._run_refresh(targets, "all")
        finally:
            if old is not None:
                self.refresh_concurrency = old

    async def get_by_id(self, cookie_id: int) -> dict[str, Any] | None:
        async with self.lock:
            entry = next((item for item in self.cookies if item.get("id") == cookie_id), None)
            return deepcopy(entry) if entry else None

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        wanted = str(email or "").strip().casefold()
        async with self.lock:
            entry = next(
                (item for item in self.cookies
                 if str(item.get("email") or "").casefold() == wanted),
                None,
            )
            return deepcopy(entry) if entry else None
    async def refresh_one(self, cookie_id: int) -> dict[str, Any] | None:
        async with self.lock:
            entry = next((x for x in self.cookies if x.get("id") == cookie_id), None)
        if entry is None:
            return None
        await self._run_refresh([entry], f"id={cookie_id}")
        return entry

    def _ensure_quota_locked(self, entry: dict[str, Any]) -> bool:
        today = self._today()
        if entry.get("quota_date") != today:
            entry["quota_date"] = today
            entry["daily_used"] = 0
            return True
        return False

    @staticmethod
    def _quota_public(entry: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, int(entry.get("daily_limit", 40) or 40))
        used = max(0, int(entry.get("daily_used", 0) or 0))
        return {
            "daily_limit": limit,
            "daily_used": used,
            "remaining": max(0, limit - used),
            "quota_date": entry.get("quota_date"),
        }

    async def acquire_next(self, exclude: set[int] | None = None) -> dict[str, Any]:
        """Select account with consecutive usage batching and atomically reserve one local quota unit."""
        await self.reload_if_changed()
        excluded = exclude or set()
        changed = False
        selected: dict[str, Any] | None = None
        async with self.lock:
            if not self.cookies:
                raise HTTPException(status_code=429, detail="No Monica accounts configured")
            total = len(self.cookies)
            for _ in range(total):
                entry = self.cookies[self.current_index % total]
                changed = self._ensure_quota_locked(entry) or changed
                limit = int(entry.get("daily_limit", self.daily_limit) or self.daily_limit)
                used = int(entry.get("daily_used", 0) or 0)
                if (
                    entry.get("id") not in excluded
                    and entry.get("is_alive")
                    and not entry.get("disabled")
                    and entry.get("cookie")
                    and used < limit
                ):
                    entry["daily_used"] = used + 1
                    entry["last_used_at"] = int(time.time())
                    if self._warmup_notifier:
                        self._warmup_notifier()
                    selected = deepcopy(entry)
                    changed = True
                    self._current_account_uses += 1
                    if self._current_account_uses >= self.consecutive_uses:
                        self.current_index = (self.current_index + 1) % total
                        self._current_account_uses = 0
                    break
                else:
                    self.current_index = (self.current_index + 1) % total
                    self._current_account_uses = 0
            snapshot = self._persistent_snapshot() if changed else None
        if snapshot is not None:
            await self._write_snapshot(snapshot)
        if selected is None:
            raise HTTPException(
                status_code=429,
                detail=f"All Monica accounts are unavailable or reached today's {self.daily_limit}-call quota",
            )
        selected["quota_reserved"] = True
        return selected

    async def release_quota(self, cookie_id: int) -> None:
        async with self.lock:
            entry = next((item for item in self.cookies if item.get("id") == cookie_id), None)
            if entry is None:
                return
            self._ensure_quota_locked(entry)
            entry["daily_used"] = max(0, int(entry.get("daily_used", 0) or 0) - 1)
            snapshot = self._persistent_snapshot()
        await self._write_snapshot(snapshot)

    async def reset_daily_quotas(self, *, force: bool = False) -> int:
        today = self._today()
        changed = 0
        async with self.lock:
            self._current_account_uses = 0
            for entry in self.cookies:
                if force or entry.get("quota_date") != today:
                    entry["quota_date"] = today
                    entry["daily_used"] = 0
                    changed += 1
            snapshot = self._persistent_snapshot() if changed else None
        if snapshot is not None:
            await self._write_snapshot(snapshot)
        return changed

    async def quota_reset_loop(self) -> None:
        """Reset local counters at midnight in the configured timezone."""
        while True:
            try:
                zone = self._timezone()
                now = datetime.now(zone)
                tomorrow = now.date() + timedelta(days=1)
                next_midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=zone)
                await asyncio.sleep(max(1.0, (next_midnight - now).total_seconds()))
                await self.reset_daily_quotas(force=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Daily Monica quota reset failed")
                await asyncio.sleep(60)
    async def get_next_entry(self, exclude: set[int] | None = None) -> dict[str, Any]:
        await self.reload_if_changed()
        excluded = exclude or set()
        changed = False
        async with self.lock:
            if not self.cookies:
                raise HTTPException(status_code=429, detail="No Monica cookies configured")
            total = len(self.cookies)
            for _ in range(total):
                entry = self.cookies[self.current_index % total]
                changed = self._ensure_quota_locked(entry) or changed
                limit = int(entry.get("daily_limit", self.daily_limit) or self.daily_limit)
                used = int(entry.get("daily_used", 0) or 0)
                if (
                    entry.get("id") not in excluded
                    and entry.get("is_alive")
                    and not entry.get("disabled")
                    and entry.get("cookie")
                    and used < limit
                ):
                    entry["last_used_at"] = int(time.time())
                    selected = deepcopy(entry)
                    self._current_account_uses += 1
                    if self._current_account_uses >= self.consecutive_uses:
                        self.current_index = (self.current_index + 1) % total
                        self._current_account_uses = 0
                    break
                else:
                    self.current_index = (self.current_index + 1) % total
                    self._current_account_uses = 0
            else:
                selected = None
            snapshot = self._persistent_snapshot() if changed else None
        if snapshot is not None:
            await self._write_snapshot(snapshot)
        if selected is None:
            raise HTTPException(status_code=429, detail="All Monica cookies are unavailable or quota exhausted")
        return selected
    async def get_next(self) -> str:
        return (await self.get_next_entry())["cookie"]

    async def verify_quota_or_exhaust(self, cookie_or_id: str | int, reason: str = "") -> bool:
        """Verify real upstream quota for account when encountering 10002 Quota exceeded.

        Returns True if the account is genuinely exhausted (basic_query <= 0).
        Returns False if the account still has basic_query quota > 0 (meaning the 10002
        was caused by request-level features like genius_bot/credits, NOT daily account quota).
        """
        target = None
        async with self.lock:
            target = next(
                (
                    x for x in self.cookies
                    if (str(x.get("id")) == str(cookie_or_id)) or (x.get("cookie") == cookie_or_id)
                ),
                None,
            )
            if target is not None:
                target = deepcopy(target)

        if not target or not target.get("cookie"):
            await self.mark_quota_exhausted(cookie_or_id, reason)
            return True

        session = await self._session()
        try:
            cookie = target["cookie"]
            headers = {
                **BASE_HEADERS,
                "cookie": cookie,
                "x-client-id": str((target.get("metadata") or {}).get("client_id") or ""),
                "user-agent": str((target.get("metadata") or {}).get("user_agent") or BASE_HEADERS["user-agent"]),
            }
            resp = await session.post(
                "https://api.monica.im/api/usagev2/get_quotas",
                headers=headers,
                json={"modules": QUOTA_MODULES},
                timeout=10,
            )
            if getattr(resp, "status_code", 0) == 200:
                data = resp.json()
                quota = _extract_basic_query_quota(data)
                mod_quotas = _extract_module_quotas(data)
                if quota is not None:
                    curr = int(quota.get("current") or 0)
                    async with self.lock:
                        entry = next(
                            (
                                x for x in self.cookies
                                if (str(x.get("id")) == str(cookie_or_id)) or (x.get("cookie") == cookie_or_id)
                            ),
                            None,
                        )
                        if entry:
                            entry.setdefault("metadata", {})["basic_query_quota"] = quota
                            if mod_quotas:
                                entry.setdefault("metadata", {})["module_quotas"] = mod_quotas
                    if curr > 0:
                        logger.warning(
                            "Account %s received upstream 10002, but real basic_query quota is %d > 0. "
                            "Account is NOT exhausted; error is caused by request features/credits.",
                            target.get("email") or cookie_or_id,
                            curr,
                        )
                        return False
            # If current quota is 0 or unverified, mark exhausted
            await self.mark_quota_exhausted(cookie_or_id, reason)
            return True
        except Exception as exc:
            logger.warning("Error verifying upstream quota for account %s: %s, falling back to exhausted mark", cookie_or_id, exc)
            await self.mark_quota_exhausted(cookie_or_id, reason)
            return True
        finally:
            close = getattr(session, "aclose", None) or getattr(session, "close", None)
            if close:
                res = close()
                if asyncio.iscoroutine(res):
                    await res

    async def mark_quota_exhausted(self, cookie_or_id: str | int, reason: str = "") -> None:
        """Mark account daily quota as exhausted so acquire_next skips it for the rest of the day."""
        changed = False
        async with self.lock:
            entry = next(
                (
                    x for x in self.cookies
                    if (str(x.get("id")) == str(cookie_or_id)) or (x.get("cookie") == cookie_or_id)
                ),
                None,
            )
            if entry is not None:
                self._ensure_quota_locked(entry)
                limit = int(entry.get("daily_limit", self.daily_limit) or self.daily_limit)
                entry["daily_used"] = limit
                entry["last_error"] = reason[:300] if reason else "Quota exceeded (10002)"
                changed = True
            snapshot = self._persistent_snapshot() if changed else None
        if snapshot is not None:
            await self._write_snapshot(snapshot)

    async def mark_failure(self, cookie: str, error: str = "") -> None:
        async with self.lock:
            entry = next((x for x in self.cookies if x.get("cookie") == cookie), None)
            if entry is None:
                return
            entry["failures"] = int(entry.get("failures", 0)) + 1
            entry["last_error"] = error[:300]
            if entry["failures"] >= self.failure_limit:
                entry["is_alive"] = False
            snapshot = self._persistent_snapshot()
        await self._write_snapshot(snapshot)

    async def mark_success(self, cookie: str) -> None:
        async with self.lock:
            entry = next((x for x in self.cookies if x.get("cookie") == cookie), None)
            if entry is None:
                return
            entry["is_alive"] = not entry.get("disabled", False)
            entry["failures"] = 0
            entry["last_error"] = ""

    async def add(self, items: list[dict[str, Any]], *, probe: bool = True) -> dict[str, int]:
        added = updated = skipped = 0
        touched: list[dict[str, Any]] = []
        async with self.lock:
            by_email = {str(x.get("email", "")).casefold(): x for x in self.cookies}
            for item in items:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                email, password, cookie, disabled, metadata = self._normalise_item(item)
                if not email:
                    skipped += 1
                    continue
                existing = by_email.get(email.casefold())
                if existing is not None:
                    existing.update(
                        {
                            "password": password or existing.get("password", ""),
                            "cookie": cookie or existing.get("cookie", ""),
                            "disabled": disabled,
                            "is_alive": bool(cookie or existing.get("cookie")) and not disabled,
                            "metadata": {**existing.get("metadata", {}), **metadata},
                            "failures": 0,
                            "last_error": "",
                        }
                    )
                    if "daily_limit" in metadata:
                        try:
                            existing["daily_limit"] = min(self.daily_limit, max(1, int(metadata["daily_limit"])))
                        except (TypeError, ValueError):
                            existing["daily_limit"] = self.daily_limit
                    if "daily_used" in metadata:
                        try:
                            existing["daily_used"] = max(0, int(metadata["daily_used"]))
                        except (TypeError, ValueError):
                            existing["daily_used"] = 0
                    if "quota_date" in metadata:
                        existing["quota_date"] = str(metadata["quota_date"])
                    touched.append(existing)
                    updated += 1
                else:
                    existing = self._make_entry(
                        email, password, cookie, disabled=disabled, metadata=metadata
                    )
                    self.cookies.append(existing)
                    by_email[email.casefold()] = existing
                    touched.append(existing)
                    added += 1
            snapshot = self._persistent_snapshot()
        if added or updated:
            await self._write_snapshot(snapshot)
            if probe:
                await self._run_refresh(touched, "new/updated")
        return {"added": added, "updated": updated, "skipped": skipped}

    async def set_disabled(self, ids: list[int], disabled: bool) -> int:
        changed = 0
        async with self.lock:
            for entry in self.cookies:
                if entry.get("id") in ids and bool(entry.get("disabled")) != disabled:
                    entry["disabled"] = disabled
                    if disabled:
                        entry["is_alive"] = False
                    elif entry.get("cookie"):
                        entry["is_alive"] = True
                    changed += 1
            snapshot = self._persistent_snapshot()
        if changed:
            await self._write_snapshot(snapshot)
        return changed

    async def remove(self, cookie_id: int) -> bool:
        async with self.lock:
            before = len(self.cookies)
            self.cookies = [x for x in self.cookies if x.get("id") != cookie_id]
            changed = len(self.cookies) != before
            snapshot = self._persistent_snapshot()
        if changed:
            await self._write_snapshot(snapshot)
        return changed

    @staticmethod
    def public_info(entry: dict[str, Any]) -> dict[str, Any]:
        cookie = str(entry.get("cookie") or "")
        cookie_names = sorted(parse_cookie_header(cookie))
        hint = ", ".join(cookie_names[:4])
        if len(cookie_names) > 4:
            hint += f" +{len(cookie_names) - 4}"
        if cookie and not hint:
            hint = "cookie configured"
        limit = int(entry.get("daily_limit", 40) or 40)
        used = int(entry.get("daily_used", 0) or 0)
        return {
            "id": entry.get("id"),
            "index": entry.get("id"),
            "email": entry.get("email", ""),
            "cookie_hint": hint,
            "cookie_names": cookie_names,
            "is_alive": bool(entry.get("is_alive")) and not bool(entry.get("disabled")),
            "disabled": bool(entry.get("disabled")),
            "failures": int(entry.get("failures", 0)),
            "last_error": entry.get("last_error", ""),
            "last_checked_at": entry.get("last_checked_at"),
            "last_used_at": entry.get("last_used_at"),
            "daily_limit": limit,
            "daily_used": used,
            "daily_remaining": max(0, limit - used),
            "quota_date": entry.get("quota_date"),
            "basic_query_quota": (entry.get("metadata") or {}).get("basic_query_quota"),
        }
    def summary(self) -> dict[str, int]:
        total = len(self.cookies)
        disabled = sum(1 for x in self.cookies if x.get("disabled"))
        alive = sum(1 for x in self.cookies if x.get("is_alive") and not x.get("disabled"))
        return {
            "total": total,
            "alive": alive,
            "disabled": disabled,
            "dead": total - alive - disabled,
            "consecutive_uses": self.consecutive_uses,
        }


    def set_warmup_notifier(self, notifier) -> None:
        self._warmup_notifier = notifier

    async def get_upcoming_entries(self, count: int = 2) -> list[dict[str, Any]]:
        await self.reload_if_changed()
        async with self.lock:
            total = len(self.cookies)
            if total == 0:
                return []
            results = []
            for offset in range(min(count, total)):
                idx = (self.current_index + offset) % total
                results.append(deepcopy(self.cookies[idx]))
            return results

    async def probe_single_entry(self, entry_id: int) -> tuple[bool, str]:
        await self.reload_if_changed()
        async with self.lock:
            target = next((item for item in self.cookies if item.get("id") == entry_id), None)
            if not target:
                return False, f"Account {entry_id} not found"
            entry_copy = deepcopy(target)

        session = await self._session()
        try:
            status = await self._probe(entry_copy, session)
            is_alive = status in ("alive", "quota", "ok")
            async with self.lock:
                current = next((item for item in self.cookies if item.get("id") == entry_id), None)
                if current:
                    current["is_alive"] = is_alive
                    current["last_checked_at"] = entry_copy.get("last_checked_at", int(time.time()))
                    current["last_error"] = entry_copy.get("last_error", "")
                    if is_alive:
                        current["failures"] = 0
                    else:
                        current["failures"] = current.get("failures", 0) + 1
            return is_alive, entry_copy.get("last_error", "")
        finally:
            close = getattr(session, "aclose", None) or getattr(session, "close", None)
            if close:
                res = close()
                if asyncio.iscoroutine(res):
                    await res

    def detail(self, *, include_secrets: bool = False) -> list[dict[str, Any]]:
        if include_secrets:
            return deepcopy(self.cookies)
        return [self.public_info(entry) for entry in self.cookies]

    async def fetch_quota(self, cookie_id: int) -> dict[str, Any] | None:
        """Fetch Monica quota data for one account using ordinary HTTP."""
        async with self.lock:
            entry = next((item for item in self.cookies if item.get("id") == cookie_id), None)
        if entry is None or not entry.get("cookie"):
            return None
        session = await self._session()
        try:
            response = await session.post(
                "https://api.monica.im/api/usagev2/get_quotas",
                headers={**BASE_HEADERS, "cookie": entry["cookie"],
                         "x-client-id": str((entry.get("metadata") or {}).get("client_id") or ""),
                         "user-agent": str((entry.get("metadata") or {}).get("user_agent") or BASE_HEADERS["user-agent"])},
                json={
                    "modules": [
                        "basic_query", "genius_bot", "credits", "image_translate",
                        "ai_content_detect", "reading_pdf", "screenshot_qa",
                        "web_search", "youtube_summarize", "image_gen", "bypass",
                        "podcast", "mindmap", "audio_transcription", "batch_processor",
                    ]
                },
                timeout=15,
            )
            if getattr(response, "status_code", 0) != 200:
                return {"status": getattr(response, "status_code", 0)}
            data = response.json()
            quota = _extract_basic_query_quota(data)
            if quota:
                async with self.lock:
                    entry.setdefault("metadata", {})["basic_query_quota"] = quota
            return data if isinstance(data, dict) else {"data": data}
        finally:
            close = getattr(session, "aclose", None) or getattr(session, "close", None)
            if close:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
    async def keep_alive_loop(self, interval_minutes: int = 30) -> None:
        while interval_minutes > 0:
            await asyncio.sleep(interval_minutes * 60)
            try:
                await self.refresh_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Periodic Monica cookie refresh failed")


def _looks_authenticated(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    code = data.get("code")
    if code in (0, 100000):
        return True
    payload = data.get("data") or data.get("result") or data.get("user")
    if isinstance(payload, dict) and any(payload.get(key) for key in ("id", "uid", "email", "user_id")):
        return True
    return any(data.get(key) for key in ("id", "uid", "email", "user_id"))

def _extract_module_quotas(data: Any) -> dict[str, dict[str, Any]]:
    result = {}
    try:
        modules = (data.get("data") or {}).get("module_quotas") or []
        for item in modules:
            mod_name = item.get("module")
            if not mod_name:
                continue
            quotas = item.get("quotas") or []
            plan = next((q for q in quotas if q.get("scene") == "plan"), None) or (quotas[0] if quotas else {})
            result[mod_name] = {
                "current": plan.get("current_quota", 0),
                "default": plan.get("default_quota", 0),
                "reset_frequency": plan.get("reset_frequency"),
                "last_reset_time": plan.get("last_reset_time"),
            }
    except Exception:
        pass
    return result


def _extract_basic_query_quota(data: Any) -> dict[str, Any] | None:
    try:
        modules = (data.get("data") or {}).get("module_quotas") or []
        basic = next(item for item in modules if item.get("module") == "basic_query")
        quotas = basic.get("quotas") or []
        plan = next(item for item in quotas if item.get("scene") == "plan")
        return {
            "current": plan.get("current_quota"),
            "default": plan.get("default_quota"),
            "reset_frequency": plan.get("reset_frequency"),
            "last_reset_time": plan.get("last_reset_time"),
        }
    except (AttributeError, StopIteration, TypeError):
        return None




































