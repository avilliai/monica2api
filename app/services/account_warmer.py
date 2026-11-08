"""Background account pre-warming and single-flight token probe.

Strictly follows genspark2api architecture:
- Pre-warms upcoming accounts ahead of the round-robin selection cursor so that
  when an account is picked for a request, it has recently verified active status.
- Absolutely NO mass keep-alive bursts or bulk concurrent requests.
- Single-concurrency probe: only warms one upcoming account per iteration.
- Responds to round-robin rotation events via `_wake_event` or periodic intervals.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.core.config import Settings
from app.services.cookie_manager import CookieManager

logger = logging.getLogger(__name__)


class AccountWarmer:
    def __init__(self, settings: Settings, manager: CookieManager) -> None:
        self.settings = settings
        self.manager = manager
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._lock = asyncio.Lock()

    def notify(self) -> None:
        """Signal the warmer that accounts were rotated or selected."""
        self._wake_event.set()

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run_loop(), name="monica-account-warmer")
            self.manager.set_warmup_notifier(self.notify)
        return self._task

    async def stop(self) -> None:
        self._stopping = True
        self._wake_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run_loop(self) -> None:
        logger.info(
            "Account warmer started (ahead_count=%d, interval=%.1fs, ttl=%.1fs)",
            self.settings.warmup_ahead_count,
            self.settings.warmup_interval_seconds,
            self.settings.warmup_token_ttl_seconds,
        )
        while not self._stopping:
            try:
                await self._warm_upcoming()
            except Exception as exc:
                logger.warning("Account warmer iteration error: %s", exc)

            # Wait for next notification or periodic interval
            try:
                await asyncio.wait_for(
                    self._wake_event.wait(),
                    timeout=self.settings.warmup_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass
            finally:
                self._wake_event.clear()

    async def _warm_upcoming(self) -> None:
        if not self.settings.account_warmup_enabled:
            return

        upcoming = await self.manager.get_upcoming_entries(self.settings.warmup_ahead_count)
        if not upcoming:
            return

        now = time.time()
        for account in upcoming:
            if self._stopping:
                break

            cookie = account.get("cookie") or ""
            if not cookie or account.get("disabled"):
                continue

            last_checked = float(account.get("last_checked_at", 0) or 0)
            needs_warmup = (
                not account.get("is_alive")
                or (now - last_checked) > self.settings.warmup_token_ttl_seconds
            )

            if needs_warmup:
                account_id = account.get("id")
                email = account.get("email") or str(account_id)
                logger.info(
                    "Account warmer: smoothly pre-heating upcoming account=%s (last_checked=%.0f, age=%.0fs)",
                    email,
                    last_checked,
                    now - last_checked if last_checked > 0 else -1,
                )
                async with self._lock:
                    success, error = await self.manager.probe_single_entry(account_id)
                if success:
                    logger.info("Account warmer: successfully pre-heated account=%s", email)
                    # Once ONE account is smoothly warmed, stop this cycle to prevent upstream traffic bursts
                    break
                else:
                    logger.warning("Account warmer: failed to pre-heat account=%s error=%s", email, error)
    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.settings.account_warmup_enabled),
            "running": self._task is not None and not self._task.done(),
            "ahead_count": self.settings.warmup_ahead_count,
            "interval_seconds": self.settings.warmup_interval_seconds,
            "ttl_seconds": self.settings.warmup_token_ttl_seconds,
            "mode": "Single-Flight Smooth Pre-Warm ",
        }
