"""Chrome native messaging host: relays one extension message to the running app.

Chrome starts this process per message, writes a length-prefixed JSON message
to stdin and reads a length-prefixed JSON reply from stdout.
"""

import json
import struct
import subprocess
import sys
from pathlib import Path

from . import ipc

PROJECT_DIR = Path(__file__).resolve().parent.parent
MAX_MESSAGE = 1024 * 1024


def read_message():
    header = sys.stdin.buffer.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    if length > MAX_MESSAGE:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def write_message(message: dict) -> None:
    data = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def app_command() -> tuple[list, Path]:
    if getattr(sys, "frozen", False):
        # Packaged build: PassVault.exe sits next to this host executable.
        exe_dir = Path(sys.executable).parent
        return [str(exe_dir / "PassVault.exe")], exe_dir
    return [str(PROJECT_DIR / ".venv" / "Scripts" / "pythonw.exe"), "-m", "passvault.app"], PROJECT_DIR


def launch_app() -> None:
    command, cwd = app_command()
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    args = dict(cwd=cwd, close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Break out of Chrome's job object so the app outlives this host process.
        subprocess.Popen(command, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **args)
    except OSError:
        subprocess.Popen(command, creationflags=flags, **args)


def handle(message: dict) -> dict:
    try:
        return ipc.request(message)
    except ipc.NotRunning:
        if message.get("action") == "show":
            launch_app()
            return {"ok": True, "launched": True}
        return {"notRunning": True}


def main():
    try:
        message = read_message()
    except ValueError:
        message = None
    if not isinstance(message, dict):
        write_message({"error": "bad request"})
        return
    write_message(handle(message))


if __name__ == "__main__":
    main()
