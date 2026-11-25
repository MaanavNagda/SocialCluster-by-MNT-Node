import unittest

from social_cluster.main import (
    _is_external_host,
    parse_notification_count,
    run_js_in_all_frames,
)


class TestParseNotificationCount(unittest.TestCase):
    def test_float_from_js_number(self):
        # QWebEnginePage.runJavaScript() marshals JS numbers to Python
        # float, never int. This is the exact shape of a real result.
        self.assertEqual(parse_notification_count(3.0), 3)

    def test_int_result(self):
        self.assertEqual(parse_notification_count(5), 5)

    def test_zero(self):
        self.assertEqual(parse_notification_count(0.0), 0)

    def test_none_result(self):
        self.assertEqual(parse_notification_count(None), 0)

    def test_non_numeric_string(self):
        self.assertEqual(parse_notification_count("undefined"), 0)

    def test_numeric_string(self):
        self.assertEqual(parse_notification_count("7"), 7)


class TestRunJsInAllFrames(unittest.TestCase):
    class FakeFrame:
        def __init__(self, children=()):
            self._children = list(children)
            self.scripts = []

        def runJavaScript(self, script, callback):
            self.scripts.append(script)

        def children(self):
            return self._children

    class FakePage:
        def __init__(self, frame):
            self._frame = frame
            self.scripts = []

        def mainFrame(self):
            return self._frame

        def runJavaScript(self, script):
            self.scripts.append(script)

    def test_runs_in_main_and_child_frames(self):
        grandchild = self.FakeFrame()
        child = self.FakeFrame([grandchild])
        root = self.FakeFrame([child])
        page = self.FakePage(root)
        run_js_in_all_frames(page, "test-script")
        self.assertEqual(root.scripts, ["test-script"])
        self.assertEqual(child.scripts, ["test-script"])
        self.assertEqual(grandchild.scripts, ["test-script"])
        self.assertEqual(page.scripts, [])

    def test_falls_back_to_page_for_older_qt(self):
        class PageWithoutFrames:
            def __init__(self):
                self.scripts = []

            def runJavaScript(self, script):
                self.scripts.append(script)

        page = PageWithoutFrames()
        run_js_in_all_frames(page, "test-script")
        self.assertEqual(page.scripts, ["test-script"])


class TestIsExternalHost(unittest.TestCase):
    def test_same_host(self):
        self.assertFalse(_is_external_host("web.whatsapp.com", "web.whatsapp.com"))

    def test_link_is_subdomain_of_base(self):
        self.assertFalse(
            _is_external_host("accounts.web.whatsapp.com", "web.whatsapp.com")
        )

    def test_base_is_subdomain_of_link(self):
        # web.whatsapp.com -> whatsapp.com stays in-app, like a browser tab.
        self.assertFalse(_is_external_host("whatsapp.com", "web.whatsapp.com"))

    def test_sibling_subdomains_same_site(self):
        self.assertFalse(_is_external_host("mail.google.com", "google.com"))

    def test_different_domain_is_external(self):
        self.assertTrue(_is_external_host("youtube.com", "web.whatsapp.com"))

    def test_lookalike_domain_is_external(self):
        self.assertTrue(_is_external_host("notyoutube.com", "youtube.com"))
        self.assertTrue(_is_external_host("evil-youtube.com", "youtube.com"))

    def test_case_insensitive(self):
        self.assertFalse(_is_external_host("YouTube.com", "youtube.com"))

    def test_empty_hosts_are_external(self):
        self.assertTrue(_is_external_host("", "youtube.com"))
        self.assertTrue(_is_external_host("youtube.com", ""))
        self.assertTrue(_is_external_host("", ""))


if __name__ == "__main__":
    unittest.main()
