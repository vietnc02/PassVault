import unittest

from passvault.autotype import (
    MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, VK_RETURN, VK_TAB, HotkeyListener,
    format_hotkey, match_entries, parse_sequence, strip_browser_suffix, validate_hotkey,
)

VK_F9, VK_PAUSE, VK_A, VK_1, VK_SPACE = 0x78, 0x13, 0x41, 0x31, 0x20


def entry(title, url="", window="", username="u"):
    return {"id": title, "title": title, "url": url, "window": window, "username": username}


class SequenceTests(unittest.TestCase):
    def test_default(self):
        self.assertEqual(parse_sequence("{USERNAME}{TAB}{PASSWORD}"),
                         [("field", "username"), ("key", VK_TAB), ("field", "password")])

    def test_literal_text_and_case(self):
        self.assertEqual(parse_sequence("id:{username}{Enter}x"),
                         [("text", "id:"), ("field", "username"), ("key", VK_RETURN), ("text", "x")])

    def test_unknown_braces_are_typed_literally(self):
        self.assertEqual(parse_sequence("{FOO}"), [("text", "{FOO}")])


class MatchTests(unittest.TestCase):
    def test_strip_browser_suffix(self):
        self.assertEqual(strip_browser_suffix("Đăng nhập - Google Chrome"), "Đăng nhập")
        self.assertEqual(strip_browser_suffix("Inbox - Gmail - Microsoft​ Edge"), "Inbox - Gmail")
        self.assertEqual(strip_browser_suffix("Zalo"), "Zalo")

    def test_every_chrome_window_does_not_match_google(self):
        entries = [entry("Gmail", url="accounts.google.com")]
        self.assertEqual(match_entries(entries, "Đăng nhập - Google Chrome"), [])

    def test_priority(self):
        entries = [
            entry("SIS", url="ctt-sis.hust.edu.vn"),            # host word "hust"
            entry("HUST"),                                       # title in window title
            entry("Cổng SV", window="hệ thống quản lý đào tạo"),  # explicit window text
            entry("Facebook", url="facebook.com"),
        ]
        found = match_entries(entries, "HỆ THỐNG QUẢN LÝ ĐÀO TẠO - HUST - Google Chrome")
        self.assertEqual([e["title"] for e in found], ["Cổng SV", "HUST", "SIS"])

    def test_explicit_window_text_must_match(self):
        # An entry with window text set only matches by that text, not by its title.
        self.assertEqual(match_entries([entry("Zalo", window="zalo pc")], "Zalo"), [])


class HotkeyChoiceTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_hotkey(MOD_CONTROL | MOD_ALT, VK_A), "Ctrl+Alt+A")
        self.assertEqual(format_hotkey(0, VK_F9), "F9")
        self.assertEqual(format_hotkey(MOD_WIN | MOD_SHIFT, VK_SPACE), "Shift+Win+Space")

    def test_allowed(self):
        for mods, vk in [(0, VK_F9), (0, VK_PAUSE), (MOD_SHIFT, VK_F9), (MOD_CONTROL, VK_A),
                         (MOD_ALT, VK_1), (MOD_WIN, VK_A), (MOD_CONTROL | MOD_SHIFT, VK_SPACE)]:
            self.assertIsNone(validate_hotkey(mods, vk), format_hotkey(mods, vk))

    def test_rejected_typing_keys(self):
        for mods, vk in [(0, VK_A), (MOD_SHIFT, VK_A), (0, VK_1), (0, VK_SPACE), (0, VK_RETURN), (0, VK_TAB)]:
            self.assertIsNotNone(validate_hotkey(mods, vk), format_hotkey(mods, vk))

    def test_rejected_modifier_only(self):
        self.assertIsNotNone(validate_hotkey(MOD_CONTROL, 0x11))


class HotkeyListenerTests(unittest.TestCase):
    # Unusual combos so the test doesn't collide with real shortcuts.
    FIRST = (MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x87)   # Ctrl+Alt+Shift+F24
    SECOND = (MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x86)  # Ctrl+Alt+Shift+F23

    def test_change_and_conflict(self):
        a, b = HotkeyListener(lambda: None), HotkeyListener(lambda: None)
        try:
            self.assertEqual(a.start(self.FIRST), self.FIRST)
            self.assertTrue(a.set_hotkey(*self.SECOND))
            self.assertEqual(a.current, self.SECOND)
            b.start(self.FIRST)
            # SECOND is a's: b can't take it and keeps what it had.
            before = b.current
            self.assertFalse(b.set_hotkey(*self.SECOND))
            self.assertEqual(b.current, before)
        finally:
            a.stop()
            b.stop()


if __name__ == "__main__":
    unittest.main()
