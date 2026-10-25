"""Local channel between the running app and the Chrome native messaging host.

The app listens on a per-user Windows named pipe. A random key is written to
%APPDATA%\\PassVault\\ipc.key on each start; clients must prove they know it
(HMAC challenge built into multiprocessing.connection). Messages are JSON.
"""

import getpass
import json
import os
import secrets
import threading
from multiprocessing import AuthenticationError
from multiprocessing.connection import Client, Listener
from urllib.parse import urlsplit

from .vault import default_vault_path

PIPE_NAME = os.environ.get("PASSVAULT_PIPE") or r"\\.\pipe\PassVault-" + getpass.getuser()


class NotRunning(Exception):
    pass


def key_path():
    return default_vault_path().parent / "ipc.key"


def host_of(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def url_matches(entry_url: str, page_url: str) -> bool:
    """True if the page is on the entry's host or one of its subdomains."""
    entry_host, page_host = host_of(entry_url), host_of(page_url)
    if not entry_host or not page_host:
        return False
    return page_host == entry_host or page_host.endswith("." + entry_host)


def request(message: dict) -> dict:
    try:
        key = bytes.fromhex(key_path().read_text(encoding="ascii").strip())
        conn = Client(PIPE_NAME, family="AF_PIPE", authkey=key)
    except (OSError, ValueError, AuthenticationError) as exc:
        raise NotRunning(str(exc)) from exc
    with conn:
        conn.send_bytes(json.dumps(message).encode("utf-8"))
        return json.loads(conn.recv_bytes().decode("utf-8"))


class IpcServer:
    """Serves requests on a background thread. `handler(dict) -> dict` runs on that thread."""

    def __init__(self, handler):
        self.handler = handler
        self.listener = None
        self._closed = False

    def start(self) -> bool:
        key = secrets.token_bytes(32)
        try:
            # The first pipe instance is exclusive, so a second app instance fails here.
            self.listener = Listener(PIPE_NAME, family="AF_PIPE", authkey=key)
        except OSError:
            return False
        path = key_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key.hex(), encoding="ascii")
        threading.Thread(target=self._serve, daemon=True).start()
        return True

    def _serve(self):
        while not self._closed:
            try:
                conn = self.listener.accept()
            except (OSError, EOFError, AuthenticationError):
                continue
            with conn:
                try:
                    message = json.loads(conn.recv_bytes().decode("utf-8"))
                    reply = self.handler(message) if isinstance(message, dict) else {"error": "bad request"}
                    conn.send_bytes(json.dumps(reply).encode("utf-8"))
                except (OSError, EOFError, ValueError):
                    pass

    def close(self):
        self._closed = True
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
            try:
                key_path().unlink(missing_ok=True)
            except OSError:
                pass
