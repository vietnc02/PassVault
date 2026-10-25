import json
import string
import tempfile
import unittest
from pathlib import Path

from passvault.generator import SYMBOLS, generate_password
from passvault.vault import Vault, VaultError, WrongPassword


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "vault.pvault"

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        vault = Vault.create(self.path, "master-password")
        entry = vault.add(title="Gmail", username="me@example.com", password="s3cret", url="mail.google.com")
        reopened = Vault.open(self.path, "master-password")
        self.assertEqual(reopened.get(entry["id"])["password"], "s3cret")

    def test_file_has_no_plaintext(self):
        vault = Vault.create(self.path, "master-password")
        vault.add(title="Bank", username="nguyen", password="very-secret-value")
        raw = self.path.read_text(encoding="utf-8")
        for secret in ("Bank", "nguyen", "very-secret-value"):
            self.assertNotIn(secret, raw)

    def test_wrong_password(self):
        Vault.create(self.path, "master-password")
        with self.assertRaises(WrongPassword):
            Vault.open(self.path, "wrong-password")

    def test_tampered_header_is_rejected(self):
        Vault.create(self.path, "master-password")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["kdf"]["time_cost"] = 4
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(WrongPassword):
            Vault.open(self.path, "master-password")

    def test_create_refuses_to_overwrite(self):
        Vault.create(self.path, "master-password")
        with self.assertRaises(VaultError):
            Vault.create(self.path, "other-password")

    def test_update_delete_search(self):
        vault = Vault.create(self.path, "master-password")
        a = vault.add(title="Facebook", username="a")
        vault.add(title="LMS VNU", username="b", url="lms.vnu.edu.vn")
        vault.update(a["id"], password="new")
        self.assertEqual([e["title"] for e in vault.search("vnu")], ["LMS VNU"])
        vault.delete(a["id"])
        self.assertEqual(len(Vault.open(self.path, "master-password").entries), 1)

    def test_change_password(self):
        vault = Vault.create(self.path, "old-password")
        vault.add(title="X")
        vault.change_password("new-password")
        with self.assertRaises(WrongPassword):
            Vault.open(self.path, "old-password")
        self.assertEqual(Vault.open(self.path, "new-password").entries[0]["title"], "X")

    def test_unicode_password_and_data(self):
        vault = Vault.create(self.path, "mật khẩu tiếng Việt")
        vault.add(title="Tài khoản ngân hàng", notes="ghi chú")
        self.assertEqual(Vault.open(self.path, "mật khẩu tiếng Việt").entries[0]["notes"], "ghi chú")


class GeneratorTests(unittest.TestCase):
    def test_contains_every_class(self):
        for _ in range(50):
            pw = generate_password(12)
            self.assertEqual(len(pw), 12)
            self.assertTrue(any(c in string.ascii_lowercase for c in pw))
            self.assertTrue(any(c in string.ascii_uppercase for c in pw))
            self.assertTrue(any(c in string.digits for c in pw))
            self.assertTrue(any(c in SYMBOLS for c in pw))

    def test_no_symbols(self):
        self.assertTrue(generate_password(16, symbols=False).isalnum())


if __name__ == "__main__":
    unittest.main()
