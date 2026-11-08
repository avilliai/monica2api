import asyncio
import sys
from pathlib import Path
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from app.core.config import get_settings
from register.monica_register import RegisterConfig, MonicaRegister

async def test():
    settings = get_settings()
    config = RegisterConfig.from_settings(settings)
    config.headless = True
    print(f"Artifact path: {config.artifact_dir}")
    print(f"Output file: {config.output_file}")
    print(f"Cookie file: {config.cookie_file}")
    reg = MonicaRegister(config=config, settings=settings)
    print("Calling register_single_account...")
    try:
        acc = await reg.register_single_account()
        print("Registration success! Email:", acc.get("email"))
    except Exception as e:
        print("Registration exception:", type(e), e)
        import traceback
        traceback.print_exc()

asyncio.run(test())
