import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from social_cluster.config import DEFAULT_CONFIG
from social_cluster.unicode_input import (
    UNICODE_INPUT_JS,
    UnicodeLineEditFilter,
    hex_to_char,
)

_TEST_THEME = {"panel": "#222222", "fg": "#eeeeee", "primary": "#3498db"}


def _key(key, modifiers=Qt.NoModifier, text=""):
    return QKeyEvent(QEvent.KeyPress, key, modifiers, text)


class TestHexToChar(unittest.TestCase):
    def test_emoji(self):
        self.assertEqual(hex_to_char("1f600"), "\U0001F600")

    def test_short_code(self):
        self.assertEqual(hex_to_char("e9"), "\u00e9")

    def test_uppercase_hex(self):
        self.assertEqual(hex_to_char("1F600"), "\U0001F600")

    def test_single_digit(self):
        self.assertEqual(hex_to_char("a"), "\n")

    def test_empty(self):
        self.assertIsNone(hex_to_char(""))

    def test_too_long(self):
        self.assertIsNone(hex_to_char("1f60000"))

    def test_non_hex(self):
        self.assertIsNone(hex_to_char("g1"))
        self.assertIsNone(hex_to_char("xyz"))

    def test_out_of_range(self):
        self.assertIsNone(hex_to_char("110000"))
        self.assertIsNone(hex_to_char("ffffff"))

    def test_surrogates_rejected(self):
        self.assertIsNone(hex_to_char("d800"))
        self.assertIsNone(hex_to_char("dfff"))

    def test_surrogate_boundaries_ok(self):
        self.assertEqual(hex_to_char("d7ff"), chr(0xD7FF))
        self.assertEqual(hex_to_char("e000"), chr(0xE000))

    def test_max_codepoint(self):
        self.assertEqual(hex_to_char("10ffff"), chr(0x10FFFF))


class TestInjectedScript(unittest.TestCase):
    def test_script_pieces(self):
        for needle in (
            "__scUnicodeEnabled",
            "KeyU",
            "keydown",
            "insertText",
            "setRangeText",
            "attachShadow",
        ):
            self.assertIn(needle, UNICODE_INPUT_JS)

    def test_config_default(self):
        self.assertTrue(DEFAULT_CONFIG["unicode_input"])


class TestUnicodeLineEditFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.config = dict(DEFAULT_CONFIG)
        self.filter = UnicodeLineEditFilter(self.config, _TEST_THEME)
        self.edit = QLineEdit()
        self.filter.install_on(self.edit)

    def tearDown(self):
        self.filter._cancel()
        self.edit.removeEventFilter(self.filter)
        self.edit.deleteLater()

    def _send(self, key, modifiers=Qt.NoModifier, text=""):
        return QApplication.sendEvent(self.edit, _key(key, modifiers, text))

    def _trigger(self):
        return self._send(Qt.Key_U, Qt.ControlModifier | Qt.ShiftModifier, "U")

    def _type(self, chars):
        for c in chars:
            self._send(ord(c.upper()), Qt.NoModifier, c)

    def test_insert_emoji_on_enter(self):
        self._trigger()
        self._type("1f600")
        self._send(Qt.Key_Return, Qt.NoModifier, "\r")
        self.assertEqual(self.edit.text(), "\U0001F600")

    def test_insert_on_space(self):
        self._trigger()
        self._type("e9")
        self._send(Qt.Key_Space, Qt.NoModifier, " ")
        self.assertEqual(self.edit.text(), "\u00e9")

    def test_escape_cancels(self):
        self._trigger()
        self._type("e9")
        self._send(Qt.Key_Escape, Qt.NoModifier, "")
        self.assertEqual(self.edit.text(), "")
        self.assertIsNone(self.filter._target)

    def test_empty_enter_cancels(self):
        self._trigger()
        self._send(Qt.Key_Return, Qt.NoModifier, "\r")
        self.assertEqual(self.edit.text(), "")
        self.assertIsNone(self.filter._target)

    def test_invalid_codepoint_not_inserted(self):
        self._trigger()
        self._type("d800")
        self._send(Qt.Key_Return, Qt.NoModifier, "\r")
        self.assertEqual(self.edit.text(), "")
        self.assertIsNone(self.filter._target)

    def test_non_hex_key_cancels_and_passes_through(self):
        self._trigger()
        self._type("1f")
        self._send(Qt.Key_G, Qt.NoModifier, "g")
        self.assertEqual(self.edit.text(), "g")
        self.assertIsNone(self.filter._target)

    def test_backspace_removes_digit(self):
        self._trigger()
        self._type("1f")
        self._send(Qt.Key_Backspace, Qt.NoModifier, "")
        self._type("600")
        self._send(Qt.Key_Return, Qt.NoModifier, "\r")
        self.assertEqual(self.edit.text(), chr(0x1600))

    def test_seventh_hex_digit_cancels_and_types(self):
        self._trigger()
        self._type("1f6000")
        self._send(Qt.Key_0, Qt.NoModifier, "0")
        self.assertEqual(self.edit.text(), "0")
        self.assertIsNone(self.filter._target)

    def test_retrigger_ignored_inside_session(self):
        self._trigger()
        self._trigger()
        self._type("e9")
        self._send(Qt.Key_Return, Qt.NoModifier, "\r")
        self.assertEqual(self.edit.text(), "\u00e9")

    def test_ctrl_combo_cancels_and_passes_through(self):
        self._trigger()
        self._type("1f")
        self._send(Qt.Key_C, Qt.ControlModifier, "")
        self.assertIsNone(self.filter._target)
        self._send(Qt.Key_X, Qt.NoModifier, "x")
        self.assertEqual(self.edit.text(), "x")

    def test_no_session_without_shift(self):
        self._send(Qt.Key_U, Qt.ControlModifier, "u")
        self.assertIsNone(self.filter._target)

    def test_no_session_without_ctrl(self):
        self._send(Qt.Key_U, Qt.ShiftModifier, "U")
        self.assertIsNone(self.filter._target)

    def test_disabled_in_config(self):
        self.config["unicode_input"] = False
        self._trigger()
        self.assertIsNone(self.filter._target)
        # Keys typed afterwards land in the field normally.
        self._type("e9")
        self.assertEqual(self.edit.text(), "e9")

    def test_readonly_lineedit_ignored(self):
        self.edit.setReadOnly(True)
        self._trigger()
        self.assertIsNone(self.filter._target)

    def test_insert_at_cursor(self):
        self.edit.setText("ab")
        self.edit.setCursorPosition(1)
        self._trigger()
        self._type("e9")
        self._send(Qt.Key_Return, Qt.NoModifier, "\r")
        self.assertEqual(self.edit.text(), "a\u00e9b")

    def test_focus_out_cancels(self):
        self._trigger()
        self._type("1f")
        QApplication.sendEvent(self.edit, QEvent(QEvent.FocusOut))
        self.assertIsNone(self.filter._target)

    def test_key_for_other_filtered_widget_cancels(self):
        other = QLineEdit()
        self.filter.install_on(other)
        try:
            self._trigger()
            QApplication.sendEvent(other, _key(Qt.Key_X, Qt.NoModifier, "x"))
            self.assertIsNone(self.filter._target)
        finally:
            other.deleteLater()


if __name__ == "__main__":
    unittest.main()
