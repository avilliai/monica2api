"""Exclusive, process-wide leases for Webshare registration proxies."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

from app.core.config import resolve_project_path


DEFAULT_PROXY_FILE = "Webshare 10 proxies.txt"


@dataclass(frozen=True, repr=False)
class RegisterProxy:
    server: str
    username: str = ""
    password: str = ""

    def browser_options(self) -> dict[str, str]:
        options = {"server": self.server}
        if self.username:
            options.update(username=self.username, password=self.password)
        return options

    def http_url(self) -> str:
        if not self.username:
            return self.server
        scheme, address = self.server.split("://", 1)
        return f"{scheme}://{quote(self.username, safe='')}:{quote(self.password, safe='')}@{address}"


class RegisterProxyPool:
    def __init__(self, text: str):
        self._available: deque[RegisterProxy] = deque()
        self._lock = threading.Lock()
        servers: set[str] = set()
        for line_number, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                if "://" not in line:
                    parts = line.split(":", 3)
                    if len(parts) == 4:
                        host, port, username, password = parts
                        line = f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
                    elif len(parts) == 2:
                        line = "http://" + line
                    else:
                        raise ValueError
                parsed = urlsplit(line)
                if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                        or not parsed.port or parsed.path not in {"", "/"}
                        or parsed.query or parsed.fragment):
                    raise ValueError
                host = parsed.hostname
                if ":" in host:
                    host = f"[{host}]"
                server = f"{parsed.scheme}://{host}:{parsed.port}"
                # Different credentials on one endpoint still share an exit IP.
                endpoint = f"{host}:{parsed.port}"
                if endpoint not in servers:
                    servers.add(endpoint)
                    self._available.append(RegisterProxy(
                        server, unquote(parsed.username or ""), unquote(parsed.password or "")
                    ))
            except (ValueError, TypeError):
                raise ValueError(f"Invalid registration proxy at line {line_number}") from None
        if not self._available:
            raise ValueError("Registration proxy file contains no proxies")

    @asynccontextmanager
    async def lease(self):
        # A threading lock also protects leases across event loops/OS threads.
        while True:
            with self._lock:
                proxy = self._available.popleft() if self._available else None
            if proxy is not None:
                break
            await asyncio.sleep(0.05)
        try:
            yield proxy
        finally:
            with self._lock:
                self._available.append(proxy)


_pools: dict[str, RegisterProxyPool] = {}
_pools_lock = threading.Lock()


def get_register_proxy_pool(filename: str) -> RegisterProxyPool | None:
    if not filename.strip():
        return None
    path = resolve_project_path(filename)
    with _pools_lock:
        key = str(path)
        if key not in _pools:
            if not path.exists() and filename == DEFAULT_PROXY_FILE:
                return None
            _pools[key] = RegisterProxyPool(path.read_text(encoding="utf-8-sig"))
        return _pools[key]
