import unittest

from passvault.autotype import VK_RETURN, VK_TAB, match_entries, parse_sequence, strip_browser_suffix


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


if __name__ == "__main__":
    unittest.main()
