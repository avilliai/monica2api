import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

cm_file = Path("app/services/cookie_manager.py")
content = cm_file.read_text(encoding="utf-8")

# 1. 增加 _warmup_notifier 初始化
if "_warmup_notifier" not in content:
    content = content.replace("self._file_signature: tuple[int, int] | None = None",
                              "self._file_signature: tuple[int, int] | None = None\n        self._warmup_notifier = None")

# 2. 增加 set_warmup_notifier, get_upcoming_entries, probe_single_entry
methods = """
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
            is_alive = status in ("alive", "quota")
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
"""

if "def get_upcoming_entries" not in content:
    content = content.replace("    def detail(self,", methods + "\n    def detail(self,")

# 3. 在 get_next_entry 选出账号后通知 warmer
if "if self._warmup_notifier:" not in content:
    target_str = 'entry["last_used_at"] = int(time.time())'
    replacement = 'entry["last_used_at"] = int(time.time())\n                    if self._warmup_notifier:\n                        self._warmup_notifier()'
    content = content.replace(target_str, replacement, 1)

cm_file.write_text(content, encoding="utf-8")
print("Updated CookieManager with AccountWarmer support methods.")
