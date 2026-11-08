import sys
from pathlib import Path

path = Path('app/services/email_service.py')
content = path.read_text(encoding='utf-8')

if '_verify_imap_login' not in content:
    target = '    async def create_email(self) -> EmailInbox:'
    replacement = '''    def _verify_imap_login(self, account: OutlookAccount, access_token: str) -> None:
        hosts = self.settings.outlook_imap_hosts
        if isinstance(hosts, str):
            hosts = [h.strip() for h in hosts.split(',') if h.strip()]
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

    async def create_email(self, validate: bool = True) -> EmailInbox:'''
    content = content.replace(target, replacement, 1)

old_loop = '''        async with self._lock:
            while self._next_account < len(self._accounts):
                index = self._next_account
                self._next_account += 1
                account = self._accounts[index]
                if account.address.strip().lower() not in self._blacklist:
                    break'''

new_loop = '''        async with self._lock:
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
                    break'''

if old_loop in content:
    content = content.replace(old_loop, new_loop, 1)

path.write_text(content, encoding='utf-8')
print('Successfully updated app/services/email_service.py')
