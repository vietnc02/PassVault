"""Auto-Type: a global hotkey that types an entry's username/password into the
window that was active when the hotkey was pressed (Windows only).

Text is sent as Unicode characters (KEYEVENTF_UNICODE) rather than key
presses, so keyboard layouts and Vietnamese input methods (Telex/VNI) don't
rewrite it.
"""

import ctypes
import re
import threading
import time
from ctypes import wintypes as wt

from .ipc import host_of

DEFAULT_SEQUENCE = "{USERNAME}{TAB}{PASSWORD}"
HOTKEY_ID = 0x5056  # arbitrary, unique within this process

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
VK_TAB, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU, VK_A = 0x09, 0x0D, 0x10, 0x11, 0x12, 0x41
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x2, 0x4
SW_RESTORE = 9

# Tried in order; the first one not taken by another program wins.
HOTKEYS = [
    (MOD_CONTROL | MOD_ALT, "Ctrl+Alt+A"),
    (MOD_CONTROL | MOD_ALT | MOD_SHIFT, "Ctrl+Alt+Shift+A"),
]

BROWSER_SUFFIXES = ("google chrome", "microsoft edge", "microsoft​ edge", "cốc cốc", "mozilla firefox", "brave", "opera")
COMMON_HOST_PARTS = {"www", "com", "net", "org", "edu", "gov", "vn", "io", "app", "login", "accounts"}


class AutoTypeError(Exception):
    pass


# ---- pure helpers (testable) ---------------------------------------------

_TOKEN = re.compile(r"\{(USERNAME|PASSWORD|TAB|ENTER)\}", re.IGNORECASE)


def parse_sequence(sequence: str) -> list:
    """'{USERNAME}{TAB}{PASSWORD}' -> [('field','username'), ('key',VK_TAB), ('field','password')]."""
    steps, pos = [], 0
    for match in _TOKEN.finditer(sequence):
        if match.start() > pos:
            steps.append(("text", sequence[pos:match.start()]))
        name = match.group(1).upper()
        if name in ("USERNAME", "PASSWORD"):
            steps.append(("field", name.lower()))
        else:
            steps.append(("key", VK_TAB if name == "TAB" else VK_RETURN))
        pos = match.end()
    if pos < len(sequence):
        steps.append(("text", sequence[pos:]))
    return steps


def strip_browser_suffix(title: str) -> str:
    """'Đăng nhập - Google Chrome' -> 'Đăng nhập', so every Chrome window doesn't match 'google'."""
    for sep in (" - ", " — "):
        head, _, tail = title.rpartition(sep)
        if head and any(tail.strip().lower().startswith(name) for name in BROWSER_SUFFIXES):
            return head
    return title


def match_entries(entries: list, window_title: str) -> list:
    """Entries that fit the window, best first: explicit window text, then title, then host words."""
    title = strip_browser_suffix(window_title).lower()

    def score(entry):
        window = entry.get("window", "").strip().lower()
        if window:
            return 3 if window in title else 0
        name = entry.get("title", "").strip().lower()
        if name and name in title:
            return 2
        parts = re.split(r"[.\-]", host_of(entry.get("url", "")))
        if any(len(p) >= 4 and p not in COMMON_HOST_PARTS and p in title for p in parts):
            return 1
        return 0

    scored = [(score(e), e) for e in entries]
    return [e for s, e in sorted(scored, key=lambda x: (-x[0], x[1]["title"].lower())) if s > 0]


# ---- Win32 ---------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    # Only here so the INPUT union has the size Windows expects.
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


def foreground_window():
    """(hwnd, title, pid) of the window the user is in."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, "", 0
    buf = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return hwnd, buf.value, pid.value


def _activate(hwnd) -> bool:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    for _ in range(40):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.025)
    return False


def _send(*events):
    inputs = (INPUT * len(events))(*events)
    if user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT)) != len(events):
        raise AutoTypeError("Windows chặn việc gõ phím.")


def _key_event(vk=0, scan=0, flags=0):
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def _type_text(text: str):
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], "little")
        _send(_key_event(scan=unit, flags=KEYEVENTF_UNICODE),
              _key_event(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        time.sleep(0.008)  # some web forms drop characters that arrive too fast


def _press(vk: int):
    _send(_key_event(vk=vk), _key_event(vk=vk, flags=KEYEVENTF_KEYUP))


def _wait_for_modifiers_released(timeout=3.0):
    # Typing while Ctrl/Alt from the hotkey are still held would send shortcuts.
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_SHIFT, VK_CONTROL, VK_MENU)):
            return
        time.sleep(0.03)


def perform(hwnd, sequence: str, username: str, password: str) -> None:
    """Type the sequence into hwnd. Stops if the user switches to another window."""
    steps = parse_sequence(sequence or DEFAULT_SEQUENCE)
    _wait_for_modifiers_released()
    if not _activate(hwnd):
        raise AutoTypeError("Không quay lại được cửa sổ cần gõ.")
    time.sleep(0.1)
    for kind, value in steps:
        if user32.GetForegroundWindow() != hwnd:
            raise AutoTypeError("Cửa sổ đã thay đổi nên đã dừng gõ.")
        if kind == "field":
            _type_text(username if value == "username" else password)
        elif kind == "key":
            _press(value)
        else:
            _type_text(value)
        time.sleep(0.05)


class HotkeyListener:
    """Registers the global hotkey on its own thread; `callback()` runs on that thread."""

    def __init__(self, callback):
        self.callback = callback
        self.label = None
        self._thread_id = None
        self._ready = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(2)
        return self.label

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        for mods, label in HOTKEYS:
            if user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, VK_A):
                self.label = label
                break
        self._ready.set()
        if self.label is None:
            return
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.callback()
        user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
