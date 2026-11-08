"""Monica automated registration service using Camoufox and reCAPTCHA audio solving."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import argparse
import asyncio
import json
import logging
import os
import random
import re
import string
import subprocess
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx
from camoufox import DefaultAddons
from camoufox.async_api import AsyncCamoufox

from app.core.config import Settings, get_settings, resolve_project_path
from app.core.exceptions import RegistrationError
from app.services.email_service import EmailInbox, get_email_service
from app.services.register_proxy_pool import RegisterProxy, get_register_proxy_pool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
load_dotenv(Path(__file__).resolve().with_name(".env"))

GOOGLE_SPEECH_API_KEY = os.getenv("GOOGLE_SPEECH_API_KEY")
GOOGLE_SPEECH_URL = (
    f"https://www.google.com/speech-api/v2/recognize?client=chromium&lang=en-us&key={GOOGLE_SPEECH_API_KEY}&maxresults=1&pfilter=2"
)


async def transcribe_audio(mp3_bytes: bytes, artifact_dir: Path) -> str:
    """Convert reCAPTCHA MP3 audio challenge to FLAC and transcribe via Google Speech API."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    temp_id = int(time.time() * 1000)
    mp3_path = artifact_dir / f"recaptcha_{temp_id}.mp3"
    flac_path = artifact_dir / f"recaptcha_{temp_id}.flac"

    try:
        mp3_path.write_bytes(mp3_bytes)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1", str(flac_path)],
            check=True,
            capture_output=True,
        )
        flac_data = flac_path.read_bytes()

        headers = {"Content-Type": "audio/x-flac; rate=16000"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(GOOGLE_SPEECH_URL, content=flac_data, headers=headers)
            for line in r.text.strip().split("\n"):
                if not line.strip():
                    continue
                data = json.loads(line)
                if "result" in data and data["result"]:
                    transcript = data["result"][0]["alternative"][0]["transcript"]
                    return transcript.strip().lower()

        raise RegistrationError(f"Speech transcription returned no alternatives: {r.text[:200]}")
    finally:
        if mp3_path.exists():
            try:
                mp3_path.unlink()
            except OSError:
                pass
        if flac_path.exists():
            try:
                flac_path.unlink()
            except OSError:
                pass


async def solve_recaptcha_audio(
    page: Any,
    artifact_dir: Path,
    button_selector: Optional[str] = None,
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
                pass
    """Find and solve Google reCAPTCHA v2 / Enterprise challenge via audio with reload retry."""
    start_url = page.url or ""
    deadline = asyncio.get_running_loop().time() + timeout
    bframe = None

    # If button_selector is provided, first try to match the exact challenge frame for that button
    if button_selector:
        while asyncio.get_running_loop().time() < deadline:
            try:
                anchor_name = await page.evaluate(f'''() => {{
                    const btn = document.querySelector('{button_selector}');
                    if (!btn) return null;
                    const hmv = btn.closest('[class*="HumanMachineVerification_human-machine-verification"]');
                    if (!hmv) return null;
                    const iframe = hmv.querySelector('iframe');
                    return iframe ? iframe.getAttribute('name') : null;
                }}''')
                if anchor_name and anchor_name.startswith('a-'):
                    target_bframe_name = 'c-' + anchor_name[2:]
                    for f in page.frames:
                        if f.name == target_bframe_name:
                            bframe = f
                            break
                if bframe:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

    if not bframe:
        while asyncio.get_running_loop().time() < deadline:
            for f in page.frames:
                if "bframe" in (f.url or ""):
                    bframe = f
                    break
            if bframe:
                break
            await asyncio.sleep(0.5)

    if not bframe:
        logger.info("No reCAPTCHA bframe detected, skipping audio solve.")
        return True

    _sublog("检测到 Google reCAPTCHA 验证码，准备发起音频挑战突破...", "warn")
    try:
        audio_btn = bframe.locator("#recaptcha-audio-button")
        await audio_btn.wait_for(state="visible", timeout=8000)
        try:
            await audio_btn.click(force=True, timeout=3000)
        except Exception:
            await bframe.evaluate('() => document.getElementById("recaptcha-audio-button")?.click()')
        await asyncio.sleep(2.0)
    except Exception as exc:
        logger.warning("Could not click audio button: %s", exc)

    for attempt in range(1, max_attempts + 1):
        try:
            rc_dmessage = bframe.locator(".rc-dmessage, .rc-doscaptcha-header-text")
            if await rc_dmessage.count() > 0 and await rc_dmessage.first.is_visible():
                msg = await rc_dmessage.first.inner_text()
                logger.warning("reCAPTCHA audio blocked: %s", msg)
                return False

            audio_source = bframe.locator("#audio-source")
            await audio_source.wait_for(state="attached", timeout=8000)
            src = await audio_source.get_attribute("src")
            if not src:
                logger.warning("No audio-source src attribute found on attempt %d", attempt)
                reload_btn = bframe.locator("#recaptcha-reload-button")
                if await reload_btn.count() > 0:
                    await reload_btn.click()
                    await asyncio.sleep(2.0)
                continue

            _sublog(f"正在下载音频挑战并调用 Google 语音转录 (尝试 {attempt}/{max_attempts})...", "sys")
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(src)
                text = await transcribe_audio(res.content, artifact_dir)
                _sublog(f"音频识别结果: '{text}'，正在自动填入验证码...", "sys")

            audio_input = bframe.locator("#audio-response")
            await audio_input.wait_for(state="visible", timeout=5000)
            await audio_input.fill(text)
            await asyncio.sleep(0.5)

            verify_btn = bframe.locator("#recaptcha-verify-button")
            try:
                await verify_btn.click(force=True, timeout=3000)
            except Exception:
                await bframe.evaluate('() => document.getElementById("recaptcha-verify-button")?.click()')
            await asyncio.sleep(2.5)

            # If page redirected or input is gone/disabled, it passed
            cur_url = page.url or ""
            if cur_url != start_url and any(k in cur_url for k in ["verify-email", "home", "new-password", "login", "auth-landing"]):
                _sublog("reCAPTCHA 音频验证成功，页面已自动重定向！", "ok")
                return True

            is_hidden = await audio_input.count() == 0 or not await audio_input.is_visible()
            is_disabled = False
            try:
                is_disabled = await audio_input.is_disabled()
            except Exception:
                pass

            if is_hidden or is_disabled:
                _sublog("reCAPTCHA 音频验证突破成功！", "ok")
                return True

            logger.info("Challenge still visible after attempt %d, clicking reload...", attempt)
            reload_btn = bframe.locator("#recaptcha-reload-button")
            if await reload_btn.count() > 0:
                await reload_btn.click()
                await asyncio.sleep(2.0)
        except Exception as exc:
            logger.warning("reCAPTCHA audio attempt %d failed: %s", attempt, exc)
            try:
                reload_btn = bframe.locator("#recaptcha-reload-button")
                if await reload_btn.count() > 0:
                    await reload_btn.click()
                    await asyncio.sleep(2.0)
            except Exception:
                pass

    return False



async def _check_already_registered(page: Any) -> bool:
    try:
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        keywords = [
            "registered using with email",
            "registered using with Email",
            "already registered",
            "account that registered",
            "please log in with email",
            "please log in with Email",
            "has been registered",
            "already exists",
        ]
        text_lower = text.lower()
        for kw in keywords:
            if kw.lower() in text_lower:
                return True
    except Exception:
        pass
    return False

def _generate_password(length: int = 16) -> str:
    letters = random.choices(string.ascii_letters, k=length - 4)
    digits = random.choices(string.digits, k=2)
    specials = random.choices("!@#$%^&*", k=2)
    pwd = letters + digits + specials
    random.shuffle(pwd)
    return "".join(pwd)


def _generate_nickname() -> str:
    prefixes = ["Monica", "User", "Alex", "Jordan", "Taylor", "Sam", "Chris"]
    return f"{random.choice(prefixes)}{random.randint(1000, 99999)}"


_SAVE_LOCK = threading.Lock()


def save_account_to_json(account_data: dict, filepath: str | Path) -> None:
    path = resolve_project_path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _SAVE_LOCK:
        existing: list[dict] = []
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        existing = data
            except Exception:
                existing = []

        # Update existing or append
        idx = next((i for i, item in enumerate(existing) if item.get("email") == account_data.get("email")), None)
        if idx is not None:
            existing[idx] = account_data
        else:
            existing.append(account_data)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.info("Saved account %s to %s", account_data.get("email"), path)


@dataclass
class RegisterConfig:
    browser_backend: str = "camoufox"
    headless: bool = True
    humanize: bool = True
    locale: str = "en-US"
    timeout_sec: int = 120
    artifact_dir: str = "register/artifacts"
    signup_url: str = "https://monica.im/sign-up?redirectTo=https%3A%2F%2Fmonica.im%2Fhome"
    output_file: str = "register/monica_accounts.json"
    cookie_file: str = "data/cookies.json"
    proxy_file: str = "Webshare 10 proxies.txt"

    @classmethod
    def from_env(cls) -> "RegisterConfig":
        return cls.from_settings(get_settings())

    @classmethod
    def from_settings(cls, settings: Settings) -> "RegisterConfig":
        return cls(
            headless=getattr(settings, "camoufox_headless", True),
            humanize=getattr(settings, "camoufox_humanize", True),
            locale=getattr(settings, "camoufox_locale", "en-US"),
            timeout_sec=getattr(settings, "camoufox_timeout", 120),
            signup_url=getattr(settings, "monica_signup_url", "https://monica.im/sign-up?redirectTo=https%3A%2F%2Fmonica.im%2Fhome"),
            output_file=getattr(settings, "register_output_file", "register/monica_accounts.json"),
            cookie_file=getattr(settings, "cookie_file", "data/cookies.json"),
            proxy_file=settings.register_proxy_file,
        )


class MonicaRegister:
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
        self._proxy: RegisterProxy | None = None
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
                pass

    async def run(self) -> dict[str, Any]:
        return await self.register_single_account()


    async def recover_account(
        self,
        page: Any,
        inbox: EmailInbox,
        email: Optional[str] = None,
    ) -> dict[str, Any]:
        """Recover an already registered account via Outlook email OTP password reset and login."""
        target_email = (email or inbox.address).strip()
        self._log(f"[找回 1/6] 正在启动账号找回与密码重置流程: {target_email}...", "warn")

        existing_ids: set[str] = set()
        if hasattr(self.email_service, "get_message_ids"):
            try:
                existing_ids = await self.email_service.get_message_ids(inbox)
            except Exception:
                pass

        reset_url = f"https://monica.im/reset-password?email={urllib.parse.quote(target_email)}"
        self._log(f"[找回 2/6] 正在打开密码重置页面: {reset_url}...", "sys")
        await page.goto(reset_url, timeout=60000)
        await asyncio.sleep(2.0)

        reset_btn = page.locator('[class*="ResetPassword_action-btn"]').first
        if await reset_btn.count() == 0:
            reset_btn = page.locator('button, div').filter(has_text=re.compile(r"^\s*Reset Password\s*$", re.I)).first
        await reset_btn.click()
        self._log("[找回 2/6] 已点击重置密码提交按钮，正在检测并处理人机验证...", "sys")

        await solve_recaptcha_audio(
            page,
            self.artifact_path,
            button_selector='[class*="ResetPassword_action-btn"]',
            timeout=20.0,
            log_callback=self._log,
        )

        self._log("[找回 3/6] 等待流转至 /new-password 重置密码页面...", "sys")
        reached_new_pwd = False
        for _ in range(30):
            await asyncio.sleep(1.0)
            if "new-password" in (page.url or ""):
                reached_new_pwd = True
                break
        if not reached_new_pwd:
            raise RegistrationError(f"未能进入 /new-password 重置页 (当前URL: {page.url})")

        self._log(f"[找回 3/6] 已到达新密码设置页，正在轮询 Outlook 提取重置验证码...", "sys")
        new_otp = await self.email_service.wait_for_code(inbox, existing_ids=existing_ids)
        self._log(f"[找回 3/6] 成功提取到重置验证码: [{new_otp}]", "ok")

        new_password = _generate_password(16)
        self._log(f"[找回 4/6] 正在填入新密码并提交重置...", "sys")
        np_inputs = await page.locator("input").all()
        if len(np_inputs) < 3:
            raise RegistrationError(f"/new-password 表单输入框数量不符 (期望>=3, 实际={len(np_inputs)})")
        await np_inputs[0].fill(new_otp)
        await np_inputs[1].fill(new_password)
        await np_inputs[2].fill(new_password)
        await page.evaluate('''() => {
            document.querySelectorAll("input").forEach(i => {
                i.dispatchEvent(new Event("input", { bubbles: true }));
                i.dispatchEvent(new Event("change", { bubbles: true }));
            });
        }''')
        await asyncio.sleep(1.0)

        update_btn = page.locator('[class*="NewPassword_update-btn"]').first
        if await update_btn.count() == 0:
            update_btn = page.locator('button, div').filter(has_text=re.compile(r"^\s*Update Password\s*$", re.I)).first
        await update_btn.click()
        self._log("[找回 4/6] 已点击更新密码按钮，正在处理对应人机验证...", "sys")

        await solve_recaptcha_audio(
            page,
            self.artifact_path,
            button_selector='[class*="NewPassword_update-btn"]',
            timeout=20.0,
            log_callback=self._log,
        )

        self._log("[找回 5/6] 密码重置提交完成，等待进入登录流程...", "sys")
        for _ in range(25):
            await asyncio.sleep(1.0)
            if any(k in (page.url or "") for k in ["/login", "/home", "/auth-landing"]):
                break

        if "/login" in (page.url or ""):
            self._log(f"[找回 5/6] 正在执行自动登录: {target_email}...", "sys")
            expected_login_url = f"https://monica.im/login?email={urllib.parse.quote(target_email)}"
            if "email=" not in (page.url or ""):
                await page.goto(expected_login_url, timeout=30000)
            await asyncio.sleep(2.0)

            # Check if "Log in with Email" button is present (if landed on provider options)
            email_landing_btn = page.locator('[class*="LoginWithEmail_btn"], button:has-text("Log in with Email"), div:has-text("Log in with Email")').first
            if await email_landing_btn.count() > 0 and await email_landing_btn.is_visible():
                await email_landing_btn.click()
                await asyncio.sleep(1.5)

            # Step A: click Next if on email step
            next_btn = page.locator('[class*="SignInWithEmail_action-btn"]').filter(has_text=re.compile(r"^\s*Next\s*$", re.I)).first
            if await next_btn.count() == 0:
                next_btn = page.locator('button, div').filter(has_text=re.compile(r"^\s*Next\s*$", re.I)).first
            if await next_btn.count() > 0 and await next_btn.is_visible():
                email_inputs = await page.locator('input[type="text"], input[placeholder*="Email"]').all()
                if email_inputs:
                    val = await email_inputs[0].input_value()
                    if not val or val.strip().lower() != target_email.lower():
                        await email_inputs[0].fill(target_email)
                await next_btn.click()
                await asyncio.sleep(2.0)

            # Step B: fill password
            pwd_input = page.locator('input[type="password"]').first
            await pwd_input.wait_for(state="visible", timeout=15000)
            await pwd_input.fill(new_password)
            await asyncio.sleep(0.5)

            # Step C: click Log In
            login_btn = page.locator('[class*="SignInWithEmail_action-btn"]').filter(has_text=re.compile(r"^\s*Log in\s*$", re.I)).first
            if await login_btn.count() == 0:
                login_btn = page.locator('[class*="SignInWithEmail_action-btn"]').first
            if await login_btn.count() == 0:
                login_btn = page.locator('button, div').filter(has_text=re.compile(r"^\s*Log in\s*$", re.I)).first
            await login_btn.click()
            self._log("[找回 5/6] 已点击登录按钮，检测人机验证...", "sys")

            await solve_recaptcha_audio(
                page,
                self.artifact_path,
                button_selector='[class*="SignInWithEmail_action-btn"]',
                timeout=12.0,
                log_callback=self._log,
            )

        for _ in range(25):
            await asyncio.sleep(1.0)
            if "/home" in (page.url or ""):
                break

        if "/home" not in (page.url or ""):
            self._log("[找回 5/6] 正在流转进入 /home 控制台...", "sys")
            await page.goto("https://monica.im/home", timeout=30000)
            await asyncio.sleep(3.0)

        # Capture cookies
        all_cookies = await page.context.cookies()
        monica_cookies: dict[str, str] = {
            c["name"]: c["value"]
            for c in all_cookies
            if "monica" in c.get("domain", "")
        }
        cookie_header = "; ".join(f"{k}={v}" for k, v in monica_cookies.items())

        self._log("[找回 6/6] 正在调用 Monica 官方接口校验账号有效性...", "sys")
        user_id = ""
        async with httpx.AsyncClient(timeout=15.0, proxy=self._proxy.http_url() if self._proxy else None) as client:
            res = await client.get(
                "https://api.monica.im/api/user/me",
                headers={
                    "cookie": cookie_header,
                    "origin": "https://monica.im",
                    "referer": "https://monica.im/",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
                    "x-client-locale": "en",
                    "x-product-name": "Monica",
                    "x-client-type": "web",
                    "x-client-version": "5.4.3",
                },
            )
            if res.status_code == 200:
                user_data = res.json().get("user") or {}
                user_id = str(user_data.get("id") or user_data.get("uid") or "")
                self._log(f"[SUCCESS] 账号找回并验证成功！用户ID: {user_id}", "ok")
            else:
                self._log(f"[WARN] 接口校验返回状态码 {res.status_code}: {res.text[:100]}", "warn")

        try:
            browser_ua = await page.evaluate("navigator.userAgent")
        except Exception:
            browser_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"

        client_id = str(uuid.uuid4())
        account_record = {
            "email": target_email,
            "password": new_password,
            "cookie": cookie_header,
            "cookies": monica_cookies,
            "disabled": False,
            "is_alive": True,
            "daily_limit": getattr(self.settings, "daily_quota_limit", 40),
            "daily_used": 0,
            "quota_date": time.strftime("%Y-%m-%d"),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": {
                "client_id": client_id,
                "user_id": user_id,
                "user_agent": browser_ua,
                "daily_limit": getattr(self.settings, "daily_quota_limit", 40),
                "daily_used": 0,
                "quota_date": time.strftime("%Y-%m-%d"),
                "recovered": True,
            },
        }

        save_account_to_json(account_record, self.config.output_file)
        save_account_to_json(account_record, self.config.cookie_file)
        if hasattr(self.email_service, "blacklist"):
            try:
                await self.email_service.blacklist(inbox, "Account recovered & added to pool")
            except Exception:
                pass
        self._log(f"[SUCCESS] 找回账号 {target_email} 已成功重新放进号池！", "ok")
        return account_record

    async def register_single_account(self) -> dict[str, Any]:
        """Lease one exclusive proxy for the entire browser registration."""
        pool = get_register_proxy_pool(self.config.proxy_file)
        if pool is None:
            return await self._register_single_account()
        async with pool.lease() as proxy:
            self._proxy = proxy
            self._log(f"注册代理已分配: {proxy.server}", "sys")
            try:
                return await self._register_single_account()
            finally:
                self._proxy = None

    async def _register_single_account(self) -> dict[str, Any]:
        """Run full automated registration flow with real-time logs and error snapshots."""
        self._log(f"[1/6] 正在从邮箱池分配可用邮箱...", "sys")
        try:
            inbox = await self.email_service.create_email()
        except Exception as exc:
            self._log(f"[ERROR] 分配邮箱失败: {exc}", "err")
            raise

        test_email = inbox.address
        test_password = _generate_password(16)
        test_nickname = _generate_nickname()
        self._log(f"[1/6] 成功分配并连通邮箱: {test_email} (昵称: {test_nickname})", "ok")

        page = None
        browser = None
        try:
            self._log(f"[2/6] 正在启动 Camoufox 反反爬浏览器环境...", "sys")
            async with AsyncCamoufox(
                headless=self.config.headless,
                humanize=self.config.humanize,
                locale=self.config.locale,
                exclude_addons=[DefaultAddons.UBO],
                **({"proxy": self._proxy.browser_options()} if self._proxy else {}),
            ) as browser:
                page = await browser.new_page()
                self._log(f"[2/6] 正在导航至 Monica 注册页: {self.config.signup_url}...", "sys")
                await page.goto(self.config.signup_url, timeout=60000)
                await asyncio.sleep(2.0)

                # Click Sign Up with Email button
                self._log("[3/6] 正在切换至邮箱注册模式...", "sys")
                email_btn = page.locator('[class*="LoginWithEmail_btn"]')
                await email_btn.wait_for(state="visible", timeout=15000)
                await email_btn.click()
                await asyncio.sleep(2.0)

                # Fill in Email, Password, Nickname
                inputs = await page.locator("input").all()
                if len(inputs) < 3:
                    raise RegistrationError(f"注册表单输入框数量不符 (期望>=3, 实际={len(inputs)})")

                self._log(f"[3/6] 正在填写注册表单 (邮箱: {test_email})...", "sys")
                await inputs[0].fill(test_email)
                await inputs[1].fill(test_password)
                await inputs[2].fill(test_nickname)
                await asyncio.sleep(1.0)

                # Click Sign Up submit button
                submit_btn = page.locator('[class*="Button_brand"]').filter(has_text=re.compile(r"^\s*Sign Up\s*$", re.I)).first
                await submit_btn.wait_for(state="visible", timeout=10000)
                await submit_btn.click()
                self._log("[4/6] 表单提交完毕，正在检测并处理人机验证码...", "sys")

                await asyncio.sleep(1.0)
                if await _check_already_registered(page):
                    self._log(f"[NOTICE] 检测到账号 {test_email} 已在 Monica 注册过，转入找回流程...", "warn")
                    return await self.recover_account(page, inbox, test_email)

                # Check and solve reCAPTCHA audio challenge
                await solve_recaptcha_audio(
                    page,
                    self.artifact_path,
                    timeout=15.0,
                    log_callback=self._log,
                )

                if await _check_already_registered(page):
                    self._log(f"[NOTICE] 检测到账号 {test_email} 已在 Monica 注册过，转入找回流程...", "warn")
                    return await self.recover_account(page, inbox, test_email)

                # Wait for verify-email URL
                self._log("[5/6] 正在等待流转至 /verify-email 验证码页面...", "sys")
                reached_verify = False
                for _ in range(30):
                    await asyncio.sleep(1.0)
                    if "verify-email" in (page.url or ""):
                        reached_verify = True
                        break
                    if await _check_already_registered(page):
                        self._log(f"[NOTICE] 检测到账号 {test_email} 已在 Monica 注册过，转入找回流程...", "warn")
                        return await self.recover_account(page, inbox, test_email)

                if not reached_verify:
                    if await _check_already_registered(page):
                        self._log(f"[NOTICE] 检测到账号 {test_email} 已在 Monica 注册过，转入找回流程...", "warn")
                        return await self.recover_account(page, inbox, test_email)
                    shot_path = self.artifact_path / f"verify_email_timeout_{int(time.time())}.png"
                    try:
                        await page.screenshot(path=str(shot_path))
                        self._log(f"[WARN] 未跳转至 verify-email，已保存截图: {shot_path.name}", "warn")
                    except Exception:
                        pass
                    raise RegistrationError("未能在预期时间内流转至邮箱验证页")

                self._log(f"[5/6] 已成功进入验证码页面: {page.url}", "ok")

                # Wait for verification code in inbox
                self._log(f"[5/6] 正在轮询 Outlook 邮箱收取 6 位验证码...", "sys")
                otp_code = await self.email_service.wait_for_code(inbox)
                self._log(f"[5/6] 成功提取到验证码: [{otp_code}]，正在自动填入...", "ok")

                # Fill OTP code
                otp_inputs = await page.locator("input").all()
                if not otp_inputs:
                    raise RegistrationError("邮箱验证码页面未发现输入框")
                await otp_inputs[0].fill(otp_code)
                await asyncio.sleep(1.0)

                # Check for verification submit button
                verify_buttons = await page.locator("button, [class*='Button_brand']").all()
                for btn in verify_buttons:
                    txt = (await btn.inner_text()).strip()
                    if any(k in txt.lower() for k in ["confirm", "verify", "continue", "submit", "next"]):
                        await btn.click()
                        self._log(f"[5/6] 已点击验证提交按钮: '{txt}'", "sys")
                        break

                # Wait for redirect to /home or login completion
                self._log("[6/6] 正在等待跳转 /home 主页并提取会话 Cookies...", "sys")
                success = False
                for _ in range(30):
                    await asyncio.sleep(1.0)
                    if "/home" in (page.url or ""):
                        success = True
                        break

                if not success:
                    self._log("[6/6] 未能自动跳转 /home，尝试直接导航...", "warn")
                    await page.goto("https://monica.im/home", timeout=30000)
                    await asyncio.sleep(3.0)

                # Capture cookies
                all_cookies = await page.context.cookies()
                monica_cookies: dict[str, str] = {
                    c["name"]: c["value"]
                    for c in all_cookies
                    if "monica" in c.get("domain", "")
                }
                cookie_header = "; ".join(f"{k}={v}" for k, v in monica_cookies.items())

                # Validate account via /api/user/me
                self._log("[6/6] 正在调用 Monica 官方接口校验会话有效性...", "sys")
                user_id = ""
                async with httpx.AsyncClient(timeout=15.0, proxy=self._proxy.http_url() if self._proxy else None) as client:
                    res = await client.get(
                        "https://api.monica.im/api/user/me",
                        headers={
                            "cookie": cookie_header,
                            "origin": "https://monica.im",
                            "referer": "https://monica.im/",
                            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
                            "x-client-locale": "en",
                            "x-product-name": "Monica",
                            "x-client-type": "web",
                            "x-client-version": "5.4.3",
                        },
                    )
                    if res.status_code == 200:
                        user_data = res.json().get("user") or {}
                        user_id = str(user_data.get("id") or user_data.get("uid") or "")
                        self._log(f"[SUCCESS] 用户验证成功！用户ID: {user_id}", "ok")
                    else:
                        self._log(f"[WARN] 接口校验返回状态码 {res.status_code}: {res.text[:100]}", "warn")

                try:
                    browser_ua = await page.evaluate("navigator.userAgent")
                except Exception:
                    browser_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"

                client_id = str(uuid.uuid4())
                account_record = {
                    "email": test_email,
                    "password": test_password,
                    "cookie": cookie_header,
                    "cookies": monica_cookies,
                    "disabled": False,
                    "is_alive": True,
                    "daily_limit": getattr(self.settings, "daily_quota_limit", 40),
                    "daily_used": 0,
                    "quota_date": time.strftime("%Y-%m-%d"),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "metadata": {
                        "client_id": client_id,
                        "user_id": user_id,
                        "user_agent": browser_ua,
                        "daily_limit": getattr(self.settings, "daily_quota_limit", 40),
                        "daily_used": 0,
                        "quota_date": time.strftime("%Y-%m-%d"),
                    },
                }

                # Persist to accounts file and cookie pool
                save_account_to_json(account_record, self.config.output_file)
                save_account_to_json(account_record, self.config.cookie_file)
                if hasattr(self.email_service, "blacklist"):
                    try:
                        await self.email_service.blacklist(inbox, "Registration successful")
                    except Exception:
                        pass
                self._log(f"[SUCCESS] 账号 {test_email} 已成功保存至资产池！", "ok")
                return account_record
        except Exception as exc:
            err_text = str(exc)
            shot_file = f"fail_{int(time.time())}.png"
            shot_path = self.artifact_path / shot_file
            if page:
                try:
                    await page.screenshot(path=str(shot_path))
                    self._log(f"[ERROR] 注册发生异常，已保存失败截屏至 {shot_file}: {err_text}", "err")
                except Exception:
                    self._log(f"[ERROR] 注册发生异常: {err_text}", "err")
            else:
                self._log(f"[ERROR] 注册发生异常: {err_text}", "err")
            raise


async def register_single_account(
    config: Optional[RegisterConfig] = None,
    settings: Optional[Settings] = None,
) -> dict[str, Any]:
    register = MonicaRegister(config=config, settings=settings)
    return await register.register_single_account()


async def register_multiple_accounts(
    count: int = 1,
    config: Optional[RegisterConfig] = None,
    settings: Optional[Settings] = None,
    target_rate_per_minute: float = 20.0,
    register_all: bool = False,
    concurrency: int = 1,
) -> list[dict[str, Any]]:
    """Batch account registration with adaptive frequency control and optional multi-worker concurrency.
    
    Target rate: ~20 accounts/minute (base delay ~3.0s).
    Automatically backs off and lowers frequency when rate limits or transient errors occur.
    """
    concurrency = max(1, min(int(concurrency), 20))
    registered_target = 999999 if register_all else max(1, count)
    results: list[dict[str, Any]] = []
    lock = asyncio.Lock()
    pool_exhausted = False
    attempt_counter = 0

    if concurrency > 1:
        logger.info(
            "Starting multi-worker batch registration (workers=%d, register_all=%s, target_count=%d)",
            concurrency,
            register_all,
            registered_target if not register_all else -1,
        )

        async def worker(worker_id: int) -> None:
            nonlocal pool_exhausted, attempt_counter
            register = MonicaRegister(config=config, settings=settings)
            while True:
                async with lock:
                    if pool_exhausted or len(results) >= registered_target:
                        break
                    attempt_counter += 1
                    current_attempt = attempt_counter

                logger.info(
                    "[Worker-%d] Starting registration attempt %d (successes: %d/%d)",
                    worker_id,
                    current_attempt,
                    len(results),
                    registered_target if not register_all else -1,
                )

                try:
                    acc = await register.register_single_account()
                    async with lock:
                        results.append(acc)
                        total_done = len(results)
                    logger.info(
                        "[Worker-%d] Successfully registered: %s (total: %d)",
                        worker_id,
                        acc.get("email"),
                        total_done,
                    )
                except Exception as exc:
                    err_msg = str(exc).lower()
                    logger.error("[Worker-%d] Registration attempt %d failed: %s", worker_id, current_attempt, exc)
                    if "no available outlook accounts" in err_msg or "exhausted" in err_msg:
                        async with lock:
                            pool_exhausted = True
                        logger.info("[Worker-%d] Account pool exhausted. Worker stopping.", worker_id)
                        break
                    await asyncio.sleep(2.0)

        tasks = [asyncio.create_task(worker(w)) for w in range(1, concurrency + 1)]
        await asyncio.gather(*tasks)

    else:
        register = MonicaRegister(config=config, settings=settings)
        base_delay = max(1.0, 60.0 / target_rate_per_minute)
        current_delay = base_delay
        consecutive_successes = 0

        logger.info(
            "Starting single-worker smooth registration (target_rate=%.1f/min, base_delay=%.2fs, register_all=%s, target_count=%d)",
            target_rate_per_minute,
            base_delay,
            register_all,
            registered_target if not register_all else -1,
        )

        i = 0
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

                if consecutive_successes >= 2 and current_delay > base_delay:
                    current_delay = max(base_delay, current_delay * 0.85)
                    logger.info("Adaptive rate: smoothly recovering delay to %.2fs", current_delay)

            except Exception as exc:
                consecutive_successes = 0
                err_msg = str(exc).lower()
                logger.error("Registration attempt %d failed: %s", i, exc)

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

                if "no available outlook accounts" in err_msg or "exhausted" in err_msg:
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
    parser.add_argument("-c", "--concurrency", type=int, default=1, help="Number of concurrent registration workers (threads)")
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
            concurrency=args.concurrency,
        )
    )

if __name__ == "__main__":
    main()
