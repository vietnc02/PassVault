"""Encrypted on-disk vault.

File format (JSON):
    {"version": 1, "kdf": {...argon2id params...}, "salt": b64,
     "nonce": b64, "ciphertext": b64}

The key is derived from the master password with Argon2id and the entry list
is encrypted with AES-256-GCM. The header (version, kdf, salt) is bound to the
ciphertext as associated data, so tampering with it makes decryption fail.
"""

import base64
import json
import os
import secrets
import time
import uuid
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT_VERSION = 1
DEFAULT_KDF = {"time_cost": 3, "memory_cost": 64 * 1024, "parallelism": 4}
# window/autotype are used by Auto-Type; entries saved before they existed simply lack them.
ENTRY_FIELDS = ("title", "username", "password", "url", "notes", "window", "autotype")


class VaultError(Exception):
    pass


class WrongPassword(VaultError):
    pass


def default_vault_path() -> Path:
    override = os.environ.get("PASSVAULT_PATH")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "PassVault" / "vault.pvault"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _derive_key(password: str, salt: bytes, kdf: dict) -> bytes:
    return hash_secret_raw(
        password.encode("utf-8"),
        salt,
        time_cost=kdf["time_cost"],
        memory_cost=kdf["memory_cost"],
        parallelism=kdf["parallelism"],
        hash_len=32,
        type=Type.ID,
    )


def _header_aad(version: int, kdf: dict, salt_b64: str) -> bytes:
    header = {"version": version, "kdf": kdf, "salt": salt_b64}
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Vault:
    def __init__(self, path: Path, key: bytes, salt: bytes, kdf: dict, entries: list):
        self.path = Path(path)
        self._key = key
        self._salt = salt
        self._kdf = kdf
        self.entries = entries

    # ---- lifecycle -------------------------------------------------------

    @classmethod
    def create(cls, path: Path, password: str) -> "Vault":
        path = Path(path)
        if path.exists():
            raise VaultError(f"Vault đã tồn tại: {path}")
        salt = secrets.token_bytes(16)
        kdf = dict(DEFAULT_KDF)
        vault = cls(path, _derive_key(password, salt, kdf), salt, kdf, [])
        vault.save()
        return vault

    @classmethod
    def open(cls, path: Path, password: str) -> "Vault":
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            version = data["version"]
            kdf = data["kdf"]
            salt_b64 = data["salt"]
            nonce = _unb64(data["nonce"])
            ciphertext = _unb64(data["ciphertext"])
        except (OSError, ValueError, KeyError) as exc:
            raise VaultError(f"Không đọc được file vault: {exc}") from exc
        if version != FORMAT_VERSION:
            raise VaultError(f"Phiên bản vault không hỗ trợ: {version}")

        salt = _unb64(salt_b64)
        key = _derive_key(password, salt, kdf)
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, _header_aad(version, kdf, salt_b64))
        except InvalidTag as exc:
            raise WrongPassword("Sai mật khẩu chính hoặc file đã bị sửa") from exc
        return cls(path, key, salt, kdf, json.loads(plaintext.decode("utf-8")))

    def save(self) -> None:
        salt_b64 = _b64(self._salt)
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(self.entries, ensure_ascii=False).encode("utf-8")
        ciphertext = AESGCM(self._key).encrypt(
            nonce, plaintext, _header_aad(FORMAT_VERSION, self._kdf, salt_b64)
        )
        data = {
            "version": FORMAT_VERSION,
            "kdf": self._kdf,
            "salt": salt_b64,
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then swap, so a crash never leaves a half-written vault.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.path)

    def change_password(self, new_password: str) -> None:
        self._salt = secrets.token_bytes(16)
        self._kdf = dict(DEFAULT_KDF)
        self._key = _derive_key(new_password, self._salt, self._kdf)
        self.save()

    def lock(self) -> None:
        self._key = b""
        self.entries = []

    # ---- entries ---------------------------------------------------------

    def get(self, entry_id: str) -> dict:
        for entry in self.entries:
            if entry["id"] == entry_id:
                return entry
        raise KeyError(entry_id)

    def add(self, **fields) -> dict:
        now = time.time()
        entry = {"id": uuid.uuid4().hex, "created": now, "updated": now}
        entry.update({name: fields.get(name, "") for name in ENTRY_FIELDS})
        self.entries.append(entry)
        self.save()
        return entry

    def update(self, entry_id: str, **fields) -> dict:
        entry = self.get(entry_id)
        entry.update({name: value for name, value in fields.items() if name in ENTRY_FIELDS})
        entry["updated"] = time.time()
        self.save()
        return entry

    def delete(self, entry_id: str) -> None:
        self.entries.remove(self.get(entry_id))
        self.save()

    def search(self, query: str) -> list:
        query = query.strip().lower()
        if not query:
            return list(self.entries)
        return [
            e for e in self.entries
            if query in e["title"].lower() or query in e["username"].lower() or query in e["url"].lower()
        ]
