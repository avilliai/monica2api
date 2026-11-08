import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

reg_file = Path("register/monica_register.py")
text = reg_file.read_text(encoding="utf-8")

new_multiple_reg = """async def register_multiple_accounts(
    count: int = 1,
    config: Optional[RegisterConfig] = None,
    settings: Optional[Settings] = None,
    target_rate_per_minute: float = 20.0,
    register_all: bool = False,
) -> list[dict[str, Any]]:
    \"\"\"Batch account registration with adaptive frequency control.
    
    Target rate: ~20 accounts/minute (base delay ~3.0s).
    Automatically backs off and lowers frequency when rate limits or transient errors occur.
    \"\"\"
    register = MonicaRegister(config=config, settings=settings)
    base_delay = max(1.0, 60.0 / target_rate_per_minute)  # e.g. 60 / 20 = 3.0s
    current_delay = base_delay
    consecutive_successes = 0

    results = []
    registered_target = 999999 if register_all else count
    i = 0

    logger.info(
        "Starting batch registration (target_rate=%.1f/min, base_delay=%.2fs, register_all=%s, target_count=%d)",
        target_rate_per_minute,
        base_delay,
        register_all,
        registered_target if not register_all else -1,
    )

    while len(results) < registered_target:
        i += 1
        logger.info(
            "=== Starting Registration attempt %d (successes so far: %d, current_delay=%.2fs) ===",
            i,
            len(results),
            current_delay,
        )
        try:
            acc = await register.register_single_account()
            results.append(acc)
            consecutive_successes += 1
            logger.info("Account successfully registered: %s (total: %d)", acc.get("email"), len(results))

            # Gradually recover back towards base_delay on consecutive successes
            if consecutive_successes >= 2 and current_delay > base_delay:
                current_delay = max(base_delay, current_delay * 0.85)
                logger.info("Adaptive rate: smoothly recovering delay to %.2fs", current_delay)

        except Exception as exc:
            consecutive_successes = 0
            err_msg = str(exc).lower()
            logger.error("Registration attempt %d failed: %s", i, exc)

            # Adaptive backoff when hitting rate limits, captcha blocks or cooldowns
            is_rate_limited = any(
                k in err_msg
                for k in ["rate limit", "too many", "429", "timeout", "quota", "verify_email", "recaptcha"]
            )
            if is_rate_limited:
                current_delay = min(60.0, current_delay * 1.8 + 2.0)
                logger.warning(
                    "Adaptive rate: detected rate limit / transient friction! Backing off delay to %.2fs",
                    current_delay,
                )
            else:
                current_delay = min(30.0, current_delay + 2.0)

            # If mailbox pool is completely exhausted, stop loop
            if "no available outlook accounts" in err_msg:
                logger.info("All Outlook accounts have been processed or registered. Stopping.")
                break

        if len(results) < registered_target:
            logger.info("Pacing delay: sleeping %.2fs before next registration...", current_delay)
            await asyncio.sleep(current_delay)

    logger.info("Batch registration finished! Successfully registered %d accounts.", len(results))
    return results


def main():
    parser = argparse.ArgumentParser(description="Monica Automated Account Register")
    parser.add_argument("--count", type=int, default=1, help="Number of accounts to register")
    parser.add_argument("--all", action="store_true", default=False, help="Register all remaining Outlook accounts")
    parser.add_argument("--rate", type=float, default=20.0, help="Target registration rate per minute (default 20)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run browser with visible UI")
    args = parser.parse_args()

    settings = get_settings()
    config = RegisterConfig.from_settings(settings)
    config.headless = args.headless

    asyncio.run(
        register_multiple_accounts(
            count=args.count,
            config=config,
            settings=settings,
            target_rate_per_minute=args.rate,
            register_all=args.all,
        )
    )
"""

# 替换 register_multiple_accounts 到 main 的实现
idx = text.find("async def register_multiple_accounts")
text = text[:idx] + new_multiple_reg
reg_file.write_text(text, encoding="utf-8")
print("Updated register/monica_register.py with adaptive rate limiter and batch registry.")
