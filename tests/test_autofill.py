import json
import os
import struct
import subprocess
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Isolate from a real running PassVault before importing ipc (it reads these at import).
_tmp = tempfile.TemporaryDirectory()
os.environ["PASSVAULT_PATH"] = str(Path(_tmp.name) / "vault.pvault")
os.environ["PASSVAULT_PIPE"] = r"\\.\pipe\PassVault-test-" + uuid.uuid4().hex

from passvault import ipc  # noqa: E402


class UrlMatchTests(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(ipc.url_matches("lms.vnu.edu.vn", "https://lms.vnu.edu.vn/login/index.php"))
        self.assertTrue(ipc.url_matches("https://www.facebook.com", "https://facebook.com/"))
        self.assertTrue(ipc.url_matches("vnu.edu.vn", "https://lms.vnu.edu.vn/"))

    def test_rejects(self):
        self.assertFalse(ipc.url_matches("lms.vnu.edu.vn", "https://lms.vnu.edu.vn.evil.com/"))
        self.assertFalse(ipc.url_matches("facebook.com", "https://notfacebook.com/"))
        self.assertFalse(ipc.url_matches("", "https://example.com/"))
        self.assertFalse(ipc.url_matches("example.com", ""))


def call_native_host(message: dict) -> dict:
    """Talk to the host exactly the way Chrome does: via the .bat, length-prefixed JSON."""
    data = json.dumps(message).encode("utf-8")
    proc = subprocess.run(
        ["cmd", "/c", str(PROJECT_DIR / "native" / "passvault_host.bat"), "chrome-extension://test/"],
        input=struct.pack("<I", len(data)) + data, capture_output=True, timeout=30,
    )
    (length,) = struct.unpack("<I", proc.stdout[:4])
    return json.loads(proc.stdout[4:4 + length])


class NativeHostTests(unittest.TestCase):
    def test_not_running(self):
        self.assertEqual(call_native_host({"action": "list", "url": "https://x.com"}), {"notRunning": True})

    def test_relays_to_server(self):
        server = ipc.IpcServer(lambda msg: {"echo": msg["action"], "url": msg["url"]})
        self.assertTrue(server.start())
        try:
            # A second server on the same pipe must fail (single instance).
            self.assertFalse(ipc.IpcServer(lambda m: {}).start())
            reply = call_native_host({"action": "list", "url": "https://lms.vnu.edu.vn/"})
            self.assertEqual(reply, {"echo": "list", "url": "https://lms.vnu.edu.vn/"})
        finally:
            server.close()

    def test_wrong_key_is_rejected(self):
        # Own pipe: a closed server's accept thread keeps the previous pipe alive until exit.
        with unittest.mock.patch.object(ipc, "PIPE_NAME", r"\\.\pipe\PassVault-test-" + uuid.uuid4().hex):
            server = ipc.IpcServer(lambda msg: {"ok": True})
            self.assertTrue(server.start())
            try:
                self.assertEqual(ipc.request({"action": "list"}), {"ok": True})
                ipc.key_path().write_text("00" * 32, encoding="ascii")
                with self.assertRaises(ipc.NotRunning):
                    ipc.request({"action": "list"})
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main()
