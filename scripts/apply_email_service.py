from pathlib import Path
import re

src = Path(r"C:\Users\Administrator\PycharmProjects\genspark2api\app\services\email_service.py").read_text(encoding="utf-8")

# 1. Replace genspark references
src = src.replace("Already present in Genspark account pool", "Already present in Monica account pool")

# 2. Add logger
if "logger = logging.getLogger(__name__)" not in src:
    src = src.replace(
        "from app.core.exceptions import RegistrationError",
        "from app.core.exceptions import RegistrationError\nimport logging\n\nlogger = logging.getLogger(__name__)"
    )

# 3. Add _verify_imap_login and pre-check to create_email
old_create = """    async def create_email(self) -> EmailInbox:
        async with self._lock:
            while self._next_account < len(self._accounts):
                index = self._next_account
                self._next_account += 1
                account = self._accounts[index]
                if account.address.strip().lower() not in self._blacklist:
                    break
            else:
                raise RegistrationError(
                    "Outlook account pool is exhausted (blacklisted accounts were skipped)"
                )
        return EmailInbox(
            address=account.address,
            token=str(index),
            created_at=time.time(),
        )"""

new_create = """    def _verify_imap_login(self, account: OutlookAccount, access_token: str) -> None:
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
                auth = (f"user={account.address}\\x01auth=Bearer {access_token}\\x01\\x01").encode("utf-8")
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
                        await asyncio.to_thread(self._verify_imap_login, account, access_token)
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
        )"""

if old_create in src:
    src = src.replace(old_create, new_create)
else:
    print("WARNING: old_create not found exactly")

# 4. Add get_email_service factory if missing
if "def get_email_service(" not in src:
    src += \"\"\"

def get_email_service(settings=None):
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()
    mode = (getattr(settings, "email_mode", None) or "outlook").strip().lower()
    if mode == "outlook":
        return OutlookEmailService(settings)
    return WorkerEmailService(settings)
\"\"\"

Path("app/services/email_service.py").write_text(src, encoding="utf-8")
print("app/services/email_service.py successfully generated and written!")