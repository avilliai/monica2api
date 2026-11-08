import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

app_file = Path("app/app.py")
text = app_file.read_text(encoding="utf-8")

# 引入 AccountWarmer
text = text.replace(
    "from app.services.register import RegisterService",
    "from app.services.register import RegisterService\nfrom app.services.account_warmer import AccountWarmer"
)

# 替换 keep_alive_task 逻辑
old_block = """    keep_alive_task: asyncio.Task | None = None
    quota_task: asyncio.Task | None = asyncio.create_task(
        manager.quota_reset_loop(), name="monica-daily-quota-reset"
    )
    if settings.keep_alive_minutes > 0:
        keep_alive_task = asyncio.create_task(
            manager.keep_alive_loop(settings.keep_alive_minutes),
            name="monica-cookie-keep-alive",
        )"""

new_block = """    # Genspark-style smooth account warmer (pre-warms upcoming accounts ahead of round-robin cursor)
    # Strictly avoids mass concurrent keep-alive bursts
    account_warmer = AccountWarmer(settings, manager)
    if settings.account_warmup_enabled:
        account_warmer.start()
    app.state.account_warmer = account_warmer

    quota_task: asyncio.Task | None = asyncio.create_task(
        manager.quota_reset_loop(), name="monica-daily-quota-reset"
    )"""

text = text.replace(old_block, new_block)

old_cleanup = """        await register_service.close()
        if keep_alive_task:
            keep_alive_task.cancel()
            with suppress(asyncio.CancelledError):
                await keep_alive_task"""

new_cleanup = """        await account_warmer.stop()
        await register_service.close()"""

text = text.replace(old_cleanup, new_cleanup)

app_file.write_text(text, encoding="utf-8")
print("Updated app/app.py with Genspark-style AccountWarmer.")
