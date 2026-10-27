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

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
VK_TAB, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU, VK_A = 0x09, 0x0D, 0x10, 0x11, 0x12, 0x41
VK_LWIN, VK_RWIN = 0x5B, 0x5C
MODIFIER_VKS = {VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
WM_HOTKEY, WM_QUIT, WM_APP_SET_HOTKEY = 0x0312, 0x0012, 0x8001
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x2, 0x4
SW_RESTORE = 9

DEFAULT_HOTKEY = (MOD_CONTROL | MOD_ALT, VK_A)
# Tried after the user's choice, in order, if that one is taken by another program.
FALLBACK_HOTKEYS = [DEFAULT_HOTKEY, (MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_A)]
# Keys that may be a hotkey on their own: they never produce text.
SOLO_KEYS = set(range(0x70, 0x88)) | {0x13, 0x91}  # F1–F24, Pause, Scroll Lock
KEY_NAMES = {
    0x13: "Pause", 0x91: "Scroll Lock", 0x20: "Space", 0x2D: "Insert", 0x2E: "Delete",
    0x24: "Home", 0x23: "End", 0x21: "Page Up", 0x22: "Page Down",
    0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓", 0x09: "Tab", 0x0D: "Enter", 0x08: "Backspace",
}

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


def key_name(vk: int) -> str:
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    return KEY_NAMES.get(vk, f"Phím {vk}")


def format_hotkey(mods: int, vk: int) -> str:
    names = [name for bit, name in ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))
             if mods & bit]
    return "+".join(names + [key_name(vk)])


def validate_hotkey(mods: int, vk: int):
    """Error message (Vietnamese) if this can't be a global hotkey, else None."""
    if vk in MODIFIER_VKS:
        return "Hãy nhấn thêm một phím khác ngoài Ctrl/Alt/Shift/Win."
    if not mods & (MOD_CONTROL | MOD_ALT | MOD_WIN) and vk not in SOLO_KEYS:
        # Taking a letter (or Shift+letter) globally would stop it being typed anywhere.
        return (f"Không dùng được {format_hotkey(mods, vk)}: phím này dùng để gõ chữ. "
                "Hãy chọn F1–F12, Pause, Scroll Lock, hoặc kết hợp với Ctrl/Alt.")
    return None


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
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
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


def held_modifiers() -> int:
    """MOD_* flags for the modifier keys held right now."""
    mods = 0
    for vks, bit in (((VK_CONTROL,), MOD_CONTROL), ((VK_MENU,), MOD_ALT),
                     ((VK_SHIFT,), MOD_SHIFT), ((VK_LWIN, VK_RWIN), MOD_WIN)):
        if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in vks):
            mods |= bit
    return mods


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
    """Owns the global hotkey on its own thread; `callback()` runs on that thread.

    A hotkey belongs to the thread that registered it, so changes requested
    from the UI thread are posted to this thread and applied there.
    """

    def __init__(self, callback):
        self.callback = callback
        self.current = None  # (mods, vk) actually registered
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._request = None
        self._done = threading.Event()
        self._ok = False

    @property
    def label(self):
        return format_hotkey(*self.current) if self.current else None

    def start(self, preferred=DEFAULT_HOTKEY):
        """Register `preferred`, else the first free fallback. Returns what was registered, or None."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(2)
        for candidate in [tuple(preferred)] + [h for h in FALLBACK_HOTKEYS if h != tuple(preferred)]:
            if self.set_hotkey(*candidate):
                return candidate
        return None

    def set_hotkey(self, mods: int, vk: int) -> bool:
        """Switch to a new hotkey; keeps the old one if the new one is taken."""
        if not self._thread_id:
            return False
        self._request = (mods, vk)
        self._done.clear()
        user32.PostThreadMessageW(self._thread_id, WM_APP_SET_HOTKEY, 0, 0)
        return self._done.wait(2) and self._ok

    def _apply_request(self):
        mods, vk = self._request
        old = self.current
        if old:
            user32.UnregisterHotKey(None, HOTKEY_ID)
        self._ok = bool(user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk))
        if self._ok:
            self.current = (mods, vk)
        elif old and user32.RegisterHotKey(None, HOTKEY_ID, old[0] | MOD_NOREPEAT, old[1]):
            self.current = old
        else:
            self.current = None
        self._done.set()

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        msg = wt.MSG()
        # Make sure this thread has a message queue before anyone posts to it.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._ready.set()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.callback()
            elif msg.message == WM_APP_SET_HOTKEY:
                self._apply_request()
        if self.current:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
