"""Monica registration package."""

from .email_service import EmailService

__all__ = [
    "MonicaRegister",
    "register_single_account",
    "register_multiple_accounts",
    "EmailService",
]


def __getattr__(name: str):
    if name in {"MonicaRegister", "register_single_account", "register_multiple_accounts"}:
        from .monica_register import (
            MonicaRegister,
            register_multiple_accounts,
            register_single_account,
        )

        exports = {
            "MonicaRegister": MonicaRegister,
            "register_single_account": register_single_account,
            "register_multiple_accounts": register_multiple_accounts,
        }
        return exports[name]
    raise AttributeError(name)
