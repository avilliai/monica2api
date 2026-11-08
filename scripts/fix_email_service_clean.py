from pathlib import Path

path = Path("app/services/email_service.py")
content = path.read_text(encoding="utf-8")

# Let's inspect WorkerEmailService to remove the misplaced _verify_imap_login
# and restore create_email(self) -> EmailInbox:
clean_worker_head = """class WorkerEmailService:
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
        }"""

# Find where WorkerEmailService starts
worker_idx = content.find("class WorkerEmailService:")
create_payload_idx = content.find('        payload = {\n            "enablePrefix": True,')

if worker_idx != -1 and create_payload_idx != -1:
    content = content[:worker_idx] + clean_worker_head + content[create_payload_idx + len('        payload = {\n            "enablePrefix": True,'):]

# Now let's properly add _verify_imap_login and create_email to OutlookEmailService
outlook_search = "    async def create_email(self) -> EmailInbox:"
if outlook_search not in content:
    # Check if create_email has validate
    outlook_search = "    async def create_email(self, validate: bool = True) -> EmailInbox:"

outlook_idx = content.find(outlook_search)
if outlook_idx == -1:
    # Find wherever create_email is under OutlookEmailService
    outlook_class_idx = content.find("class OutlookEmailService:")
    outlook_idx = content.find("def create_email", outlook_class_idx)
    outlook_idx = content.rfind("    async def create_email", 0, outlook_idx + 30)

# Replace the create_email section in OutlookEmailService
target_end = content.find("    def _account(self, inbox: EmailInbox) -> OutlookAccount:", outlook_idx)

new_outlook_methods = """    def _verify_imap_login(self, account: OutlookAccount, access_token: str) -> None:
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
        )

"""

content = content[:outlook_idx] + new_outlook_methods + content[target_end:]
path.write_text(content, encoding="utf-8")
print("Cleanly fixed app/services/email_service.py!")
