from pathlib import Path

path = Path("register/monica_register.py")
content = path.read_text(encoding="utf-8")

# Let's locate the entire `register_single_account` method
start_marker = "    async def register_single_account(self) -> dict[str, Any]:"
# Find the start
start_idx = content.find(start_marker)
if start_idx == -1:
    raise RuntimeError("start_marker not found")

# The method ends right before `def main():` or at the end of class
end_marker = "            return account_record"
end_idx = content.find(end_marker, start_idx)
if end_idx == -1:
    raise RuntimeError("end_marker not found")
end_idx += len(end_marker)

new_method = '''    async def register_single_account(self) -> dict[str, Any]:
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

                # Check and solve reCAPTCHA audio challenge
                await solve_recaptcha_audio(
                    page,
                    self.artifact_path,
                    timeout=15.0,
                    log_callback=self._log,
                )

                # Wait for verify-email URL
                self._log("[5/6] 正在等待流转至 /verify-email 验证码页面...", "sys")
                try:
                    await page.wait_for_url(lambda u: "verify-email" in u, timeout=30000)
                except Exception as exc:
                    shot_path = self.artifact_path / f"verify_email_timeout_{int(time.time())}.png"
                    try:
                        await page.screenshot(path=str(shot_path))
                        self._log(f"[WARN] 未跳转至 verify-email，已保存截图: {shot_path.name}", "warn")
                    except Exception:
                        pass
                    raise RegistrationError(f"未能在预期时间内流转至邮箱验证页: {exc}")

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
                async with httpx.AsyncClient(timeout=15.0) as client:
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
            raise'''

content = content[:start_idx] + new_method + content[end_idx:]
path.write_text(content, encoding="utf-8")
print("Successfully replaced register_single_account in register/monica_register.py")
