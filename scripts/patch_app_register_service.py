from pathlib import Path

path = Path("app/services/register.py")
content = path.read_text(encoding="utf-8")

# 1. Update _new_client to pass log_callback
old_new_client = """        if changes:
            config = replace(config, **changes)
        return MonicaRegister(config=config)"""

new_new_client = """        if changes:
            config = replace(config, **changes)
        log_callback = overrides.get("log_callback")
        return MonicaRegister(config=config, log_callback=log_callback)"""

if old_new_client in content:
    content = content.replace(old_new_client, new_new_client, 1)

# 2. Update register_one signature and invocation
old_reg_one = """    async def register_one(
        self,
        signup_url: str | None = None,
        *,
        backend: str | None = None,
        headless: bool | None = None,
    ) -> dict[str, Any]:
        client = self._new_client(
            signup_url=signup_url,
            backend=backend,
            headless=headless,
        )"""

new_reg_one = """    async def register_one(
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
        )"""

if old_reg_one in content:
    content = content.replace(old_reg_one, new_reg_one, 1)

# 3. Update call in _run_job
old_job_reg = """                    self._append_log(job_id, f"正在尝试注册第 {idx}/{count} 个账号...")
                    try:
                        account = await self.register_one(
                            signup_url,
                            backend=backend,
                            headless=headless,
                        )"""

new_job_reg = """                    self._append_log(job_id, f"正在尝试注册第 {idx}/{count} 个账号...")
                    def _step_log(msg: str, lvl: str = "sys"):
                        self._append_log(job_id, f"{msg}")

                    try:
                        account = await self.register_one(
                            signup_url,
                            backend=backend,
                            headless=headless,
                            log_callback=_step_log,
                        )"""

if old_job_reg in content:
    content = content.replace(old_job_reg, new_job_reg, 1)

path.write_text(content, encoding="utf-8")
print("Successfully patched app/services/register.py")
