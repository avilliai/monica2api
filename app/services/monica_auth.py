"""Small HTTP client for Monica's authentication endpoints.

The web sign-up page uses a browser only for the reCAPTCHA interaction.  Once a
captcha pass token is available, the remaining requests are ordinary JSON
requests.  This client keeps that transport separate from the chat client so
the API process never needs to launch a browser for normal completions.
"""

from __future__ import annotations

import json
import os
import platform
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


AUTH_BASE_URL = "https://api.monica.im"
EMAIL_STATUS_PATH = "/api/user/list_email_registered_v2"
SEND_CODE_PATH = "/api/user/send_email_verify_code_with_captcha"
REGISTER_PATH = "/api/user/register_by_email"
LOGIN_PATH = "/api/user/login_by_email_v2"
ME_PATH = "/api/user/me"
CONNECTION_TOKEN_PATH = "/agent_v1/agent.v1.AgentService/GetConnectionToken"


@dataclass(slots=True)
class MonicaAuthResult:
    """Normalised result returned by :meth:`MonicaAuthClient.register`.

    ``cookies`` contains only cookies returned by Monica.  The raw response is
    retained in ``payload`` for diagnostics, while callers can safely ignore
    it when persisting an account.
    """

    email: str
    cookies: dict[str, str]
    payload: dict[str, Any]
    connection_token: str | None = None

    @property
    def cookie_header(self) -> str:
        return "; ".join(f"{name}={value}" for name, value in self.cookies.items())


class MonicaAuthError(RuntimeError):
    """Raised when an authentication endpoint returns an unexpected result."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class MonicaAuthClient:
    """HTTP transport for sign-up, session checks and connection tokens."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        base_url: str = AUTH_BASE_URL,
        locale: str | None = None,
        timezone: str | None = None,
        timeout: float | None = None,
        proxy: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client_id = client_id or str(uuid.uuid4())
        self.base_url = base_url.rstrip("/")
        self.locale = locale or os.getenv("MONICA_CLIENT_LOCALE", "zh_CN")
        self.timezone = timezone or os.getenv("MONICA_TIMEZONE", "Etc/GMT-8")
        self.timeout = timeout or float(os.getenv("MONICA_AUTH_TIMEOUT", "30"))
        self.proxy = proxy or (os.getenv("PROXY") or "").strip() or None
        self.cookies = httpx.Cookies()
        self.transport = transport

    @property
    def headers(self) -> dict[str, str]:
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://monica.im",
            "referer": "https://monica.im/",
            "x-client-id": self.client_id,
            "x-client-locale": self.locale,
            "x-client-type": "web",
            "x-client-version": os.getenv("MONICA_CLIENT_VERSION", "5.4.3"),
            "x-product-name": "Monica",
            "x-time-zone": f"{self.timezone};-480",
            "user-agent": os.getenv(
                "MONICA_USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36",
            ),
        }

    def _client(self) -> httpx.AsyncClient:
        # ``proxy`` was renamed from ``proxies`` in httpx 0.28.  Keeping this
        # in one place makes the rest of the auth code version independent.
        kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "headers": self.headers,
            "timeout": self.timeout,
            "follow_redirects": True,
            "trust_env": False,
            "cookies": self.cookies,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError):  # type: ignore[name-defined]
            value = {}
        return value if isinstance(value, dict) else {"data": value}

    async def email_status(self, email: str) -> dict[str, Any]:
        """Ask Monica whether ``email`` already exists."""
        async with self._client() as client:
            response = await client.post(EMAIL_STATUS_PATH, json={"email": email})
        self.cookies.update(response.cookies)
        data = self._decode_response(response, "email status")
        return data

    async def send_email_code(self, email: str, captcha_response: str) -> dict[str, Any]:
        """Request the sign-up OTP after a reCAPTCHA pass token."""
        if not captcha_response:
            raise MonicaAuthError("captcha_response is required")
        payload = {
            "email": email,
            "action": "register",
            "captcha_pass_token": {"captcha_response": captcha_response},
        }
        async with self._client() as client:
            response = await client.post(SEND_CODE_PATH, json=payload)
        self.cookies.update(response.cookies)
        return self._decode_response(response, "send verification code")

    async def login_by_email(
        self,
        *,
        email: str,
        password: str,
        first_entry: str = "https://monica.im/?ref=theinsaneapp.com",
        refer: str = "https://monica.im/?ref=theinsaneapp.com",
        utm: str = "aishenqi.net",
    ) -> MonicaAuthResult:
        """Login with the same JSON endpoint used by Monica Web."""
        payload = {
            "email": email,
            "password": password,
            "first_entry": first_entry,
            "first_from_platform": "web",
            "refer": refer,
            "utm": utm,
            "platform": "",
            "client_type": "web",
            "device_name": "",
            "browser_name": "edge",
            "os_name": "windows",
            "os_version": "unknown",
            "c_d": "1",
        }
        async with self._client() as client:
            response = await client.post(LOGIN_PATH, json=payload)
            data = self._decode_response(response, "login")
            self.cookies.update(client.cookies)
            cookies = _cookie_dict(self.cookies)
        return MonicaAuthResult(
            email=email,
            cookies=cookies,
            payload=data,
            connection_token=_find_token(data),
        )
    async def register_by_email(
        self,
        *,
        email: str,
        password: str,
        name: str,
        verify_code: str,
        utm: str = "",
        refer: str = "https://monica.im/",
        first_entry: str = "https://monica.im/",
    ) -> MonicaAuthResult:
        """Complete registration with the code received by email."""
        payload = {
            "verify_code": verify_code,
            "utm": utm,
            "refer": refer,
            "first_entry": first_entry,
            "locale": self.locale,
            "first_from_platform": "web",
            "client_type": "web",
            "device_name": "",
            "browser_name": "edge",
            "os_name": platform.system().lower() or "windows",
            "os_version": platform.release() or "unknown",
            "email": email,
            "password": password,
            "name": name,
        }
        async with self._client() as client:
            response = await client.post(REGISTER_PATH, json=payload)
            data = self._decode_response(response, "register account")
            cookies = _cookie_dict(client.cookies)
        token = _find_token(data)
        return MonicaAuthResult(
            email=email,
            cookies=cookies,
            payload=data,
            connection_token=token,
        )

    async def me(self, cookies: dict[str, str] | str | None = None) -> dict[str, Any]:
        """Return the current user response using a cookie header or jar."""
        headers: dict[str, str] = {}
        if cookies:
            headers["cookie"] = cookie_header(cookies)
        async with self._client() as client:
            response = await client.get(ME_PATH, headers=headers)
        return self._decode_response(response, "session check")

    async def get_connection_token(
        self, cookies: dict[str, str] | str | None = None
    ) -> dict[str, Any]:
        """Fetch the short-lived token used by Monica's agent services."""
        headers: dict[str, str] = {
            "content-type": "application/json",
            "connect-protocol-version": "1",
        }
        if cookies:
            headers["cookie"] = cookie_header(cookies)
        async with self._client() as client:
            response = await client.post(
                CONNECTION_TOKEN_PATH,
                headers=headers,
                json={"locale": "en", "timezone": self.timezone, "clientType": "web"},
            )
        return self._decode_response(response, "connection token")

    @staticmethod
    def _decode_response(response: httpx.Response, operation: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text[:500]}
        if response.status_code >= 400:
            raise MonicaAuthError(
                f"Monica {operation} returned HTTP {response.status_code}",
                response.status_code,
            )
        if isinstance(data, dict):
            # Monica uses both code=0 and code=100000 for successful legacy
            # endpoints.  Only explicit non-zero error codes are rejected.
            code = data.get("code")
            if isinstance(code, int) and code not in (0, 100000):
                message = data.get("msg") or data.get("message") or data
                raise MonicaAuthError(f"Monica {operation} failed: {message}")
            return data
        return {"data": data}


def _cookie_dict(jar: httpx.Cookies) -> dict[str, str]:
    """Flatten a cookie jar and prefer the API host's specific value."""
    selected: dict[str, tuple[int, str]] = {}
    for item in jar.jar:
        domain = str(getattr(item, "domain", "") or "").lower()
        score = 2 if domain == "api.monica.im" else 1 if domain.endswith(".monica.im") else 0
        current = selected.get(item.name)
        if current is None or score >= current[0]:
            selected[item.name] = (score, item.value)
    return {name: value for name, (_, value) in selected.items()}

def cookie_header(value: dict[str, str] | str) -> str:
    if isinstance(value, str):
        return value
    return "; ".join(f"{key}={val}" for key, val in value.items())


def _find_token(value: Any) -> str | None:
    """Find a desktop/session token without assuming one response shape."""
    if isinstance(value, dict):
        for key in ("token", "desktopToken", "access_token", "accessToken", "jwt"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for nested_key in ("data", "result", "user"):
            found = _find_token(value.get(nested_key))
            if found:
                return found
    return None










