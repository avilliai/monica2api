from pathlib import Path

path = Path("register/monica_register.py")
content = path.read_text(encoding="utf-8")

# Let's inspect imports: make sure Callable is imported
if "from typing import" in content:
    content = content.replace("from typing import Any, Dict, List, Optional", "from typing import Any, Callable, Dict, List, Optional")

# Update solve_recaptcha_audio signature and internal logs
old_func = """async def solve_recaptcha_audio(page: Any, artifact_dir: Path, timeout: float = 20.0, max_attempts: int = 4) -> bool:"""
new_func = """async def solve_recaptcha_audio(
    page: Any,
    artifact_dir: Path,
    timeout: float = 20.0,
    max_attempts: int = 4,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> bool:
    def _sublog(msg: str, level: str = "sys"):
        if level == "err":
            logger.error(msg)
        elif level == "warn":
            logger.warning(msg)
        else:
            logger.info(msg)
        if log_callback:
            try:
                log_callback(msg, level)
            except Exception:
                pass"""

if old_func in content:
    content = content.replace(old_func, new_func, 1)

# Now update the log messages inside solve_recaptcha_audio
content = content.replace(
    'logger.info("reCAPTCHA bframe found! Attempting audio challenge...")',
    '_sublog("检测到 Google reCAPTCHA 验证码，准备发起音频挑战突破...", "warn")',
)
content = content.replace(
    'logger.info("Downloading challenge audio (attempt %d/%d) from %s...", attempt, max_attempts, src[:60])',
    '_sublog(f"正在下载音频挑战并调用 Google 语音转录 (尝试 {attempt}/{max_attempts})...", "sys")',
)
content = content.replace(
    'logger.info("Audio challenge transcribed: \'%s\'", text)',
    '_sublog(f"音频识别结果: \'{text}\'，正在自动填入验证码...", "sys")',
)
content = content.replace(
    'logger.info("reCAPTCHA passed and page already redirected!")',
    '_sublog("reCAPTCHA 音频验证成功，页面已自动重定向！", "ok")',
)
content = content.replace(
    'logger.info("reCAPTCHA audio challenge solved successfully!")',
    '_sublog("reCAPTCHA 音频验证突破成功！", "ok")',
)

# Update MonicaRegister __init__
old_init = """class MonicaRegister:
    def __init__(
        self,
        config: Optional[RegisterConfig] = None,
        settings: Optional[Settings] = None,
        email_service: Optional[Any] = None,
    ):
        self.settings = settings or get_settings()
        self.config = config or RegisterConfig.from_settings(self.settings)
        self.email_service = email_service or get_email_service(self.settings)
        self.artifact_path = resolve_project_path(self.config.artifact_dir)
        self.artifact_path.mkdir(parents=True, exist_ok=True)"""

new_init = """class MonicaRegister:
    def __init__(
        self,
        config: Optional[RegisterConfig] = None,
        settings: Optional[Settings] = None,
        email_service: Optional[Any] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.settings = settings or get_settings()
        self.config = config or RegisterConfig.from_settings(self.settings)
        self.email_service = email_service or get_email_service(self.settings)
        self.log_callback = log_callback
        self.artifact_path = resolve_project_path(self.config.artifact_dir)
        self.artifact_path.mkdir(parents=True, exist_ok=True)

    def _log(self, message: str, level: str = "sys") -> None:
        if level == "err":
            logger.error(message)
        elif level == "warn":
            logger.warning(message)
        else:
            logger.info(message)
        if self.log_callback:
            try:
                self.log_callback(message, level)
            except Exception:
                pass"""

if old_init in content:
    content = content.replace(old_init, new_init, 1)

path.write_text(content, encoding="utf-8")
print("Updated solve_recaptcha_audio & MonicaRegister __init__")
