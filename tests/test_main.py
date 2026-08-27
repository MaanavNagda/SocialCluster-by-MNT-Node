import unittest

from social_cluster.main import parse_notification_count


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


if __name__ == "__main__":
    unittest.main()
