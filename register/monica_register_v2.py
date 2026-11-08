"""兼容入口；注册实现统一维护在 :mod:`register.monica_register`。"""

import asyncio

try:
    from .monica_register import MonicaRegister, register_multiple_accounts, register_single_account
except ImportError:
    from monica_register import MonicaRegister, register_multiple_accounts, register_single_account

__all__ = ["MonicaRegister", "register_single_account", "register_multiple_accounts"]


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(register_single_account()) else 2)
