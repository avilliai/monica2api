"""Temporary mailbox client compatible with the reference project's worker API."""

from __future__ import annotations

import asyncio
import html
import imaplib
import json
import random
import re
import string
import time
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

from app.core.config import Settings, resolve_project_path
from app.core.exceptions import RegistrationError
import logging

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmailInbox:
    address: str
    token: str
    created_at: float = 0.0


class WorkerEmailService:
    def __init__(self, settings: Settings):
        self.settings = settings
        if not all((settings.worker_domain, settings.email_domain, settings.admin_password)):
            raise RegistrationError(
                "WORKER_DOMAIN, EMAIL_DOMAIN and ADMIN_PASSWORD are required for registration"
            )
        worker = settings.worker_domain.rstrip("/")
        if worker.startswith(("http://", "https://")):
            self.base_url = worker
        else:
            self.base_url = f"{settings.email_scheme}://{worker}"

    @staticmethod
    def random_local_part() -> str:
        letters = "".join(random.choices(string.ascii_lowercase, k=random.randint(5, 8)))
        digits = "".join(random.choices(string.digits, k=random.randint(2, 4)))
        tail = "".join(random.choices(string.ascii_lowercase, k=random.randint(0, 3)))
        return letters + digits + tail

    async def create_email(self) -> EmailInbox:
        payload = {
            "enablePrefix": True,
            "name": self.random_local_part(),
            "domain": self.settings.email_domain,
        }
        headers = {
            "x-admin-auth": self.settings.admin_password,
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url}/admin/new_address",
                json=payload,
                headers=headers,
            )
        if response.status_code != 200:
            raise RegistrationError(
                f"Temporary email creation failed: HTTP {response.status_code} {response.text[:300]}"
            )
        data = response.json()
        token = data.get("jwt") or data.get("token") or (data.get("data") or {}).get("jwt")
        address = data.get("address") or (data.get("data") or {}).get("address")
        if not token or not address:
            raise RegistrationError(f"Temporary email response missing jwt/address: {data}")
        return EmailInbox(address=str(address), token=str(token))

    async def fetch_messages(self, inbox: EmailInbox) -> list[dict]:
        headers = {"authorization": f"Bearer {inbox.token}"}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(
                f"{self.base_url}/api/mails",
                params={"limit": 20, "offset": 0},
                headers=headers,
            )
        if response.status_code != 200:
            return []
        data = response.json()
        results = data.get("results") or (data.get("data") or {}).get("results") or []
        return results if isinstance(results, list) else []

    async def wait_for_code(self, inbox: EmailInbox, existing_ids: set[str] | None = None) -> str:
        deadline = asyncio.get_running_loop().time() + self.settings.email_poll_timeout
        seen: set[str] = set(existing_ids or ())
        while asyncio.get_running_loop().time() < deadline:
            for message in await self.fetch_messages(inbox):
                raw = str(message.get("raw") or message.get("content") or message)
                fingerprint = str(message.get("id") or hash(raw))
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                code = extract_verification_code(raw)
                if code:
                    return code
            await asyncio.sleep(self.settings.email_poll_interval)
        raise RegistrationError(
            f"Timed out waiting for the verification email sent to {inbox.address}"
        )


@dataclass(slots=True, frozen=True)
class OutlookAccount:
    address: str
    password: str
    client_id: str
    refresh_token: str


class OutlookImapAuthenticationError(RegistrationError):
    """The OAuth identity is valid, but Outlook rejected the IMAP session."""


def load_outlook_accounts(path: str) -> list[OutlookAccount]:
    """Load email----password----client_id----refresh_token account lines."""
    account_path = resolve_project_path(path)
    if not account_path.is_file():
        raise RegistrationError(f"Outlook account file not found: {account_path}")
    accounts: list[OutlookAccount] = []
    for line_number, raw_line in enumerate(
        account_path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("----", 3)
        if len(parts) != 4 or not all(part.strip() for part in parts):
            raise RegistrationError(
                f"Invalid Outlook account format at line {line_number}; expected "
                "email----password----client_id----refresh_token"
            )
        address, password, client_id, refresh_token = (part.strip() for part in parts)
        if "@" not in address:
            raise RegistrationError(f"Invalid Outlook email at line {line_number}")
        accounts.append(OutlookAccount(address, password, client_id, refresh_token))
    if not accounts:
        raise RegistrationError(f"Outlook account file is empty: {account_path}")
    return accounts


class OutlookEmailService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._accounts = load_outlook_accounts(settings.outlook_account_file)
        self._blacklist_path = resolve_project_path(settings.outlook_blacklist_file)
        self._blacklist = self._load_blacklist()
        self._next_account = 0
        self._lock = asyncio.Lock()
        self._sync_registered_accounts()

    def _sync_registered_accounts(self) -> None:
        files = [
            getattr(self.settings, 'cookie_file', 'data/cookies.json'),
            getattr(self.settings, 'register_output_file', 'register/monica_accounts.json'),
        ]
        registered_emails = set()
        for f in files:
            path = resolve_project_path(f)
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get('email'):
                                registered_emails.add(str(item['email']).strip().lower())
                except Exception:
                    pass
        changed = False
        for em in registered_emails:
            if em not in self._blacklist:
                self._blacklist[em] = {
                    'reason': 'Already present in Monica account pool',
                    'blacklisted_at': int(time.time()),
                }
                changed = True
        if changed:
            self._save_blacklist()

    def _load_blacklist(self) -> dict[str, dict]:
        if not self._blacklist_path.is_file():
            return {}
        try:
            data = json.loads(self._blacklist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistrationError(
                f"Invalid Outlook blacklist file {self._blacklist_path}: {exc}"
            ) from exc
        if isinstance(data, list):
            return {str(address).strip().lower(): {} for address in data if str(address).strip()}
        if not isinstance(data, dict):
            raise RegistrationError(
                f"Invalid Outlook blacklist file {self._blacklist_path}: expected JSON object"
            )
        return {
            str(address).strip().lower(): details if isinstance(details, dict) else {}
            for address, details in data.items()
            if str(address).strip()
        }

    def _save_blacklist(self) -> None:
        self._blacklist_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._blacklist_path.with_suffix(self._blacklist_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._blacklist, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._blacklist_path)

    async def blacklist(self, inbox: EmailInbox, reason: str) -> None:
        async with self._lock:
            self._blacklist[inbox.address.strip().lower()] = {
                "reason": reason[:1000],
                "blacklisted_at": int(time.time()),
            }
            self._save_blacklist()

    async def blacklist_registered(self, addresses: set[str]) -> int:
        source_addresses = {account.address.strip().lower() for account in self._accounts}
        matches = source_addresses.intersection(
            address.strip().lower() for address in addresses if address.strip()
        )
        async with self._lock:
            new_addresses = matches.difference(self._blacklist)
            for address in new_addresses:
                self._blacklist[address] = {
                    "reason": "Already present in Monica account pool",
                    "blacklisted_at": int(time.time()),
                }
            if new_addresses:
                self._save_blacklist()
        return len(new_addresses)

    def _verify_imap_login(self, account: OutlookAccount, access_token: str) -> None:
        hosts = self.settings.outlook_imap_hosts
        if isinstance(hosts, str):
            hosts = [h.strip() for h in hosts.split(",") if h.strip()]
        last_error = None
        for host in hosts:
            client = None
            try:
                client = imaplib.IMAP4_SSL(
                    host,
                    self.settings.outlook_imap_port,
                    timeout=8.0,
                )
                auth = (f"user={account.address}\x01auth=Bearer {access_token}\x01\x01").encode("utf-8")
                client.authenticate("XOAUTH2", lambda _challenge: auth)
                return
            except Exception as exc:
                last_error = exc
            finally:
                if client is not None:
                    try:
                        client.logout()
                    except Exception:
                        pass
        raise OutlookImapAuthenticationError(f"IMAP pre-check failed: {last_error}")

    async def create_email(self, validate: bool = True) -> EmailInbox:
        async with self._lock:
            while self._next_account < len(self._accounts):
                index = self._next_account
                self._next_account += 1
                account = self._accounts[index]
                addr_lower = account.address.strip().lower()
                if addr_lower in self._blacklist:
                    continue
                if validate:
                    try:
                        access_token = await self._access_token(account)
                        try:
                            await asyncio.to_thread(self._verify_imap_login, account, access_token)
                        except Exception:
                            await self._check_rest_api(account, access_token)
                        break
                    except Exception as exc:
                        logger.warning("Outlook account %s failed pre-check (%s), blacklisting", account.address, exc)
                        self._blacklist[addr_lower] = {
                            "reason": f"Pre-check failed: {exc}"[:500],
                            "blacklisted_at": int(time.time()),
                        }
                        self._save_blacklist()
                        continue
                else:
                    break
            else:
                raise RegistrationError(
                    "Outlook account pool is exhausted (blacklisted accounts were skipped)"
                )
        return EmailInbox(
            address=account.address,
            token=str(index),
            created_at=time.time(),
        )

    def _account(self, inbox: EmailInbox) -> OutlookAccount:
        try:
            account = self._accounts[int(inbox.token)]
        except (ValueError, IndexError):
            raise RegistrationError("Invalid Outlook inbox handle") from None
        if account.address != inbox.address:
            raise RegistrationError("Outlook inbox handle does not match its email")
        return account

    async def _access_token(self, account: OutlookAccount) -> str:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.post(
                self.settings.outlook_token_url,
                data={
                    "client_id": account.client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": account.refresh_token,
                },
            )
        if response.status_code != 200:
            raise RegistrationError(
                f"Outlook OAuth refresh failed for {account.address}: HTTP {response.status_code}"
            )
        token = response.json().get("access_token")
        if not token:
            raise RegistrationError(
                f"Outlook OAuth response missing access_token for {account.address}"
            )
        return str(token)

    async def _check_rest_api(self, account: OutlookAccount, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://outlook.office.com/api/v2.0/me/messages?$top=1&$select=Id",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise RegistrationError(f"REST API pre-check failed: HTTP {resp.status_code}")

    async def _fetch_rest_messages(
        self, account: OutlookAccount, access_token: str
    ) -> list[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://outlook.office.com/api/v2.0/me/messages?$top=15&$select=Id,Subject,BodyPreview,Body,DateTimeReceived",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return []
            items = resp.json().get("value", [])
            messages: list[dict] = []
            for item in items:
                body = item.get("Body") or {}
                content = body.get("Content") if isinstance(body, dict) else str(body)
                raw = f"{item.get('Subject', '')}\n{item.get('BodyPreview', '')}\n{content}"
                messages.append(
                    {
                        "id": str(item.get("Id") or ""),
                        "receivedDateTime": str(item.get("DateTimeReceived") or item.get("receivedDateTime") or ""),
                        "subject": str(item.get("Subject") or ""),
                        "bodyPreview": str(item.get("BodyPreview") or ""),
                        "raw": raw,
                    }
                )
            return messages

    async def get_message_ids(self, inbox: EmailInbox) -> set[str]:
        try:
            msgs = await self.fetch_messages(inbox)
            return {str(m.get("id")) for m in msgs if m.get("id")}
        except Exception:
            return set()
    async def fetch_messages(self, inbox: EmailInbox) -> list[dict]:
        account = self._account(inbox)
        access_token = await self._access_token(account)
        try:
            return await asyncio.to_thread(self._fetch_imap_messages, account, access_token)
        except Exception as exc:
            try:
                rest_msgs = await self._fetch_rest_messages(account, access_token)
                if rest_msgs is not None:
                    return rest_msgs
            except Exception:
                pass
            raise

    def _fetch_imap_messages(
        self, account: OutlookAccount, access_token: str
    ) -> list[dict]:
        errors: list[str] = []
        authentication_failed = False
        for host in self.settings.outlook_imap_hosts:
            client: imaplib.IMAP4_SSL | None = None
            try:
                client = imaplib.IMAP4_SSL(
                    host,
                    self.settings.outlook_imap_port,
                    timeout=self.settings.outlook_imap_timeout,
                )
                auth = (
                    f"user={account.address}\x01auth=Bearer {access_token}\x01\x01"
                ).encode("utf-8")
                client.authenticate("XOAUTH2", lambda _challenge: auth)
                messages: list[dict] = []
                for folder in ("INBOX", "Junk"):
                    status, _ = client.select(folder, readonly=True)
                    if status != "OK":
                        continue
                    status, data = client.search(None, "ALL")
                    if status != "OK" or not data:
                        continue
                    message_ids = data[0].split()[-25:]
                    for message_id in reversed(message_ids):
                        status, fetched = client.fetch(message_id, "(RFC822)")
                        if status != "OK" or not fetched:
                            continue
                        raw_bytes = next(
                            (
                                item[1]
                                for item in fetched
                                if isinstance(item, tuple)
                                and len(item) > 1
                                and isinstance(item[1], bytes)
                            ),
                            None,
                        )
                        if raw_bytes is None:
                            continue
                        raw = raw_bytes.decode("utf-8", "replace")
                        parsed = BytesParser(policy=policy.default).parsebytes(raw_bytes)
                        received = ""
                        if parsed.get("Date"):
                            try:
                                received = parsedate_to_datetime(parsed["Date"]).isoformat()
                            except (TypeError, ValueError, OverflowError):
                                pass
                        messages.append(
                            {
                                "id": f"{folder}:{message_id.decode('ascii', 'replace')}",
                                "receivedDateTime": received,
                                "raw": raw,
                            }
                        )
                return messages
            except imaplib.IMAP4.error as exc:
                authentication_failed = True
                errors.append(f"{host}: {str(exc)[:160]}")
            except OSError as exc:
                errors.append(f"{host}: {str(exc)[:160]}")
            finally:
                if client is not None:
                    try:
                        client.logout()
                    except (OSError, imaplib.IMAP4.error):
                        pass
        detail = "; ".join(errors) or "no IMAP hosts configured"
        message = f"Outlook IMAP authentication/fetch failed for {account.address}: {detail}"
        if authentication_failed:
            raise OutlookImapAuthenticationError(message)
        raise RegistrationError(message)

    async def wait_for_code(self, inbox: EmailInbox, existing_ids: set[str] | None = None) -> str:
        deadline = asyncio.get_running_loop().time() + self.settings.email_poll_timeout
        seen: set[str] = set(existing_ids or ())
        while asyncio.get_running_loop().time() < deadline:
            for message in await self.fetch_messages(inbox):
                received = str(message.get("receivedDateTime") or "")
                body = message.get("body") or {}
                raw = str(message.get("raw") or "\n".join(
                    (
                        str(message.get("subject") or ""),
                        str(message.get("bodyPreview") or ""),
                        str(body.get("content") if isinstance(body, dict) else body),
                    )
                ))
                fingerprint = str(message.get("id") or hash(raw))
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                # A newly allocated inbox must not consume an old verification code.
                if received:
                    try:
                        from datetime import datetime

                        timestamp = datetime.fromisoformat(received.replace("Z", "+00:00")).timestamp()
                        if timestamp < inbox.created_at - 30:
                            continue
                    except ValueError:
                        pass
                code = extract_verification_code(raw)
                if code:
                    return code
            await asyncio.sleep(self.settings.email_poll_interval)
        raise RegistrationError(
            f"Timed out waiting for the verification email sent to {inbox.address}"
        )


# Backward-compatible name for callers that directly use the Worker client.
EmailService = WorkerEmailService


def _decode_mime(raw_email: str) -> str:
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw_email.encode("utf-8", "replace"))
    except Exception:
        return raw_email
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() not in {"text/plain", "text/html"}:
                continue
            try:
                parts.append(part.get_content())
            except Exception:
                payload = part.get_payload(decode=True) or b""
                parts.append(payload.decode(part.get_content_charset() or "utf-8", "replace"))
    else:
        try:
            parts.append(message.get_content())
        except Exception:
            parts.append(raw_email)
    return "\n".join(parts)


def extract_verification_code(raw_email: str) -> str | None:
    content = html.unescape(_decode_mime(raw_email))
    content = BeautifulSoup(content, "html.parser").get_text(" ")
    content = re.sub(r"\s+", " ", content)
    preferred = [
        r"(?:verification|security|confirmation|one[- ]time|OTP)\s*(?:code)?\s*[:：-]?\s*([0-9]{6})",
        r"(?:验证码|驗證碼)\s*[:：-]?\s*([0-9]{6})",
        r"\b([0-9]{6})\b",
    ]
    for pattern in preferred:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def get_email_service(settings=None):
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()
    mode = (getattr(settings, "email_mode", None) or "outlook").strip().lower()
    if mode == "outlook":
        return OutlookEmailService(settings)
    return WorkerEmailService(settings)
