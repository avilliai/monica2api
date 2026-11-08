import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

cfg_file = Path("app/core/config.py")
text = cfg_file.read_text(encoding="utf-8")

warmer_fields = """
    # Account warmer settings (Genspark-style smooth pre-heating, no bulk bursts)
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
"""

if "account_warmup_enabled" not in text:
    text = text.replace("    available_models: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))",
                        "    available_models: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))\n" + warmer_fields)
    cfg_file.write_text(text, encoding="utf-8")
    print("Added warmer fields to app/core/config.py")
else:
    print("Warmer fields already exist in app/core/config.py")
