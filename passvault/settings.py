"""Non-secret preferences (e.g. the Auto-Type hotkey), stored as JSON next to the vault."""

import json
import os

from .vault import default_vault_path


def settings_path():
    return default_vault_path().parent / "settings.json"


def load() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update(**values) -> None:
    data = load()
    data.update(values)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
