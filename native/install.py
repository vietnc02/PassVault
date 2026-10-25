"""Register (or with --uninstall, remove) the PassVault native messaging host
for Chrome and Edge, for the current Windows user only."""

import base64
import hashlib
import json
import sys
import winreg
from pathlib import Path

HOST_NAME = "com.passvault.host"
NATIVE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = NATIVE_DIR.parent
HOST_MANIFEST = NATIVE_DIR / f"{HOST_NAME}.json"
REGISTRY_KEYS = {
    "Chrome": rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
    "Edge": rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
}


def extension_id() -> str:
    """Chrome derives an unpacked extension's ID from the manifest's public key."""
    manifest = json.loads((PROJECT_DIR / "extension" / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


def install():
    ext_id = extension_id()
    HOST_MANIFEST.write_text(json.dumps({
        "name": HOST_NAME,
        "description": "PassVault autofill bridge",
        "path": str(NATIVE_DIR / "passvault_host.bat"),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }, indent=2), encoding="utf-8")
    for browser, key in REGISTRY_KEYS.items():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
            winreg.SetValueEx(handle, "", 0, winreg.REG_SZ, str(HOST_MANIFEST))
        print(f"Đã đăng ký cho {browser}")
    print(f"ID extension: {ext_id}")


def uninstall():
    for browser, key in REGISTRY_KEYS.items():
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            print(f"Đã gỡ khỏi {browser}")
        except FileNotFoundError:
            pass
    HOST_MANIFEST.unlink(missing_ok=True)


if __name__ == "__main__":
    uninstall() if "--uninstall" in sys.argv else install()
