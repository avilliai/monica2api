"""Registration orchestration and background job tracking."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from copy import deepcopy
from dataclasses import replace
from typing import Any, Callable

from app.core.config import Settings, resolve_project_path
from app.services.cookie_manager import CookieManager

logger = logging.getLogger(__name__)


class RegisterService:
    """Run Monica registrations and add successful sessions to the cookie pool."""

    def __init__(
        self,
        settings: Settings,
        cookie_manager: CookieManager,
        *,
        register_factory: Callable[..., Any] | None = None,
    ):
        self.settings = settings
        self.cookie_manager = cookie_manager
        self.register_factory = register_factory
        self.jobs: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def get_pool_info(self) -> dict[str, Any]:
        """Get Outlook pool statistics (total, used/blacklisted, remaining)."""
        try:
            from app.services.email_service import get_email_service
            svc = get_email_service(self.settings)
            if hasattr(svc, "_accounts"):
                total = len(svc._accounts)
                blacklist_count = len(getattr(svc, "_blacklist", {}))
                remaining = max(0, total - blacklist_count)
                return {
                    "provider": "outlook",
                    "total": total,
                    "used_or_blacklisted": blacklist_count,
                    "remaining": remaining,
                    "total_outlook_accounts": total,
                    "unregistered_accounts": remaining,
                }
        except Exception as exc:
            return {
                "provider": "outlook",
                "error": str(exc),
                "remaining": 0,
                "total": 0,
                "used_or_blacklisted": 0,
            }
        return {"provider": "tempmail", "remaining": -1, "total": 0, "used_or_blacklisted": 0}

    def _new_client(self, **overrides: Any):
        if self.register_factory is not None:
            return self.register_factory(**overrides)
        from register.monica_register import MonicaRegister, RegisterConfig

        config = RegisterConfig.from_settings(self.settings)
        changes: dict[str, Any] = {}
        if self.settings.monica_signup_url:
            changes["signup_url"] = overrides.get("signup_url") or self.settings.monica_signup_url
        backend = overrides.get("backend") or self.settings.register_browser_backend
        if backend:
            changes["browser_backend"] = backend
        if "headless" in overrides and overrides["headless"] is not None:
            changes["headless"] = bool(overrides["headless"])
        import dataclasses
        valid_keys = {f.name for f in dataclasses.fields(config)}
        filtered_changes = {k: v for k, v in changes.items() if k in valid_keys}
        if filtered_changes:
            config = replace(config, **filtered_changes)
        log_callback = overrides.get("log_callback")
        return MonicaRegister(config=config, log_callback=log_callback)

    async def register_one(
        self,
        signup_url: str | None = None,
        *,
        backend: str | None = None,
        headless: bool | None = None,
        log_callback: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        client = self._new_client(
            signup_url=signup_url,
            backend=backend,
            headless=headless,
            log_callback=log_callback,
        )
        result = await client.run()
        if not result:
            status = getattr(client, "last_status", "failed")
            error = getattr(client, "last_error", None) or status
            raise RuntimeError(f"Monica registration failed: {error}")

        await self.cookie_manager.add([result], probe=False)
        output = resolve_project_path(self.settings.register_output_file)
        try:
            from register.monica_register import save_account_to_json

            await asyncio.to_thread(save_account_to_json, result, output)
        except Exception:
            pass
        return result

    async def start_job(
        self,
        count: int = 1,
        *,
        concurrency: int | None = None,
        rate: float = 20.0,
        register_all: bool = False,
        mode: str = "outlook",
        signup_url: str | None = None,
        backend: str | None = None,
        headless: bool | None = None,
    ) -> dict[str, Any]:
        count = max(1, min(int(count), 1000))
        if concurrency is not None:
            actual_concurrency = max(1, min(int(concurrency), 20))
        elif mode in ("multi", "concurrent"):
            actual_concurrency = max(1, min(int(self.settings.register_concurrency or 3), 20))
        else:
            actual_concurrency = max(1, min(int(self.settings.register_concurrency or 1), 20))

        target_rate = max(1.0, min(float(rate), 60.0))

        pool_info = self.get_pool_info()
        if register_all and pool_info.get("provider") == "outlook":
            count = max(1, pool_info.get("remaining", count))

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "status": "queued",
            "mode": mode,
            "concurrency": actual_concurrency,
            "rate": target_rate,
            "register_all": register_all,
            "requested": count,
            "completed": 0,
            "succeeded": 0,
            "failed": 0,
            "results": [],
            "errors": [],
            "logs": [
                f"[{time.strftime('%H:%M:%S')}] 任务已创建: 模式={mode}, 并发线程={actual_concurrency}, 请求注册={count}, 目标速率={target_rate:.1f}/min"
            ],
            "created_at": int(time.time()),
            "started_at": None,
            "finished_at": None,
        }
        async with self._lock:
            self.jobs[job_id] = job
            task = asyncio.create_task(
                self._run_job(
                    job_id,
                    count,
                    actual_concurrency,
                    target_rate,
                    register_all,
                    mode,
                    signup_url,
                    backend,
                    headless,
                ),
                name=f"monica-register-{job_id[:8]}",
            )
            self.tasks[job_id] = task
        return deepcopy(job)

    def _append_log(self, job_id: str, text: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        logs = job.setdefault("logs", [])
        logs.append(f"[{time.strftime('%H:%M:%S')}] {text}")
        if len(logs) > 100:
            del logs[: len(logs) - 100]

    async def _run_job(
        self,
        job_id: str,
        count: int,
        concurrency: int,
        rate: float,
        register_all: bool,
        mode: str,
        signup_url: str | None,
        backend: str | None,
        headless: bool | None,
    ) -> None:
        async with self._lock:
            job = self.jobs[job_id]
            job["status"] = "running"
            job["started_at"] = int(time.time())

        is_multi = (concurrency > 1) or (mode in ("multi", "concurrent"))

        if is_multi:
            actual_workers = max(1, min(concurrency, 20))
            self._append_log(
                job_id,
                f"启动多线程并发注册任务: 线程数={actual_workers}, 目标注册={count} 个",
            )
            pool_exhausted = False
            next_attempt_idx = 0

            async def concurrent_worker(worker_id: int) -> None:
                nonlocal pool_exhausted, next_attempt_idx
                while True:
                    async with self._lock:
                        if job_id not in self.tasks:
                            break
                        if pool_exhausted:
                            break
                        if self.jobs[job_id]["succeeded"] >= count or next_attempt_idx >= count:
                            break
                        next_attempt_idx += 1
                        idx = next_attempt_idx

                    self._append_log(job_id, f"[Worker-{worker_id}] 开始执行第 {idx}/{count} 个账号注册...")

                    def _worker_log(msg: str, lvl: str = "sys"):
                        self._append_log(job_id, f"[Worker-{worker_id}] {msg}")

                    try:
                        account = await self.register_one(
                            signup_url,
                            backend=backend,
                            headless=headless,
                            log_callback=_worker_log,
                        )
                        email = account.get("email", "unknown")
                        async with self._lock:
                            self.jobs[job_id]["succeeded"] += 1
                            self.jobs[job_id]["results"].append(
                                {
                                    "index": idx,
                                    "worker": worker_id,
                                    "email": email,
                                    "time": int(time.time()),
                                }
                            )
                        self._append_log(
                            job_id,
                            f"[Worker-{worker_id}] 账号注册成功并入库: {email} (当前成功: {self.jobs[job_id]['succeeded']})",
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        err_str = str(exc)
                        err_lower = err_str.lower()
                        async with self._lock:
                            self.jobs[job_id]["failed"] += 1
                            self.jobs[job_id]["errors"].append(
                                {
                                    "index": idx,
                                    "worker": worker_id,
                                    "message": err_str[:300],
                                }
                            )
                        self._append_log(job_id, f"[Worker-{worker_id}] 注册失败: {err_str[:120]}")
                        if "no available outlook accounts" in err_lower or "exhausted" in err_lower:
                            async with self._lock:
                                pool_exhausted = True
                            self._append_log(job_id, f"[Worker-{worker_id}] Outlook 邮箱池可用账号已耗尽，Worker 停止运行")
                            break
                        await asyncio.sleep(2.0)
                    finally:
                        async with self._lock:
                            self.jobs[job_id]["completed"] += 1

            try:
                worker_tasks = [
                    asyncio.create_task(concurrent_worker(w), name=f"worker-{w}")
                    for w in range(1, actual_workers + 1)
                ]
                await asyncio.gather(*worker_tasks)
                async with self._lock:
                    job = self.jobs[job_id]
                    job["status"] = (
                        "completed" if not job["failed"] else "completed_with_errors"
                    )
                    job["finished_at"] = int(time.time())
                self._append_log(
                    job_id,
                    f"多线程批量任务执行完毕: 成功 {job['succeeded']} 个, 失败 {job['failed']} 个",
                )
            except asyncio.CancelledError:
                async with self._lock:
                    job = self.jobs.get(job_id)
                    if job:
                        job["status"] = "cancelled"
                        job["finished_at"] = int(time.time())
                self._append_log(job_id, "注册任务已被管理员手动取消")
                raise
            finally:
                async with self._lock:
                    self.tasks.pop(job_id, None)

        else:
            # Single-worker smooth adaptive mode
            base_delay = max(0.5, 60.0 / rate)
            current_delay = base_delay
            consecutive_successes = 0
            self._append_log(
                job_id,
                f"启动 Outlook 批量注册任务 (初始间隔: {current_delay:.1f}s, 总计: {count} 个)",
            )

            try:
                for idx in range(1, count + 1):
                    async with self._lock:
                        if job_id not in self.tasks:
                            break

                    self._append_log(job_id, f"正在执行第 {idx}/{count} 个账号注册...")

                    def _step_log(msg: str, lvl: str = "sys"):
                        self._append_log(job_id, f"{msg}")

                    try:
                        account = await self.register_one(
                            signup_url,
                            backend=backend,
                            headless=headless,
                            log_callback=_step_log,
                        )
                        email = account.get("email", "unknown")
                        consecutive_successes += 1
                        async with self._lock:
                            self.jobs[job_id]["succeeded"] += 1
                            self.jobs[job_id]["results"].append(
                                {
                                    "index": idx,
                                    "email": email,
                                    "time": int(time.time()),
                                }
                            )
                        self._append_log(
                            job_id,
                            f"账号注册成功并入库: {email} (累计成功: {self.jobs[job_id]['succeeded']})",
                        )
                        if consecutive_successes >= 2 and current_delay > base_delay:
                            current_delay = max(base_delay, current_delay * 0.85)

                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        consecutive_successes = 0
                        err_str = str(exc)
                        err_lower = err_str.lower()
                        async with self._lock:
                            self.jobs[job_id]["failed"] += 1
                            self.jobs[job_id]["errors"].append(
                                {
                                    "index": idx,
                                    "message": err_str[:300],
                                }
                            )

                        is_rate_limit = any(
                            k in err_lower
                            for k in [
                                "rate limit",
                                "too many",
                                "429",
                                "timeout",
                                "quota",
                                "verify_email",
                                "recaptcha",
                            ]
                        )
                        if is_rate_limit:
                            current_delay = min(60.0, current_delay * 1.8 + 2.0)
                            self._append_log(
                                job_id,
                                f"遭遇频控/验证码或超时，自适应提升延迟至 {current_delay:.1f}s: {err_str[:120]}",
                            )
                        else:
                            current_delay = min(30.0, current_delay + 2.0)
                            self._append_log(job_id, f"注册失败: {err_str[:120]}")

                        if "no available outlook accounts" in err_lower or "exhausted" in err_lower:
                            self._append_log(job_id, "Outlook 邮箱池可用账号已耗尽，停止后续注册")
                            break
                    finally:
                        async with self._lock:
                            self.jobs[job_id]["completed"] += 1

                    if idx < count:
                        await asyncio.sleep(current_delay)

                async with self._lock:
                    job = self.jobs[job_id]
                    job["status"] = (
                        "completed" if not job["failed"] else "completed_with_errors"
                    )
                    job["finished_at"] = int(time.time())
                self._append_log(
                    job_id,
                    f"单线程批量任务执行完毕: 成功 {job['succeeded']} 个, 失败 {job['failed']} 个",
                )

            except asyncio.CancelledError:
                async with self._lock:
                    job = self.jobs.get(job_id)
                    if job:
                        job["status"] = "cancelled"
                        job["finished_at"] = int(time.time())
                self._append_log(job_id, "注册任务已被管理员手动取消")
                raise
            finally:
                async with self._lock:
                    self.tasks.pop(job_id, None)

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        async with self._lock:
            job = self.jobs.get(job_id)
            return deepcopy(job) if job else None

    async def list_jobs(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [deepcopy(item) for item in reversed(list(self.jobs.values()))]

    async def cancel_job(self, job_id: str) -> bool:
        async with self._lock:
            task = self.tasks.get(job_id)
        if task is None:
            return False
        task.cancel()
        return True

    async def close(self) -> None:
        async with self._lock:
            tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
