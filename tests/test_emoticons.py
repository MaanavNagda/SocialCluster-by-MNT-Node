import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from social_cluster.config import DEFAULT_CONFIG
from social_cluster.emoticons import (
    EMOTICON_MAP,
    find_emoticon_replacement,
    match_emoticon_at_end,
    python_index_for_utf16_offset,
    utf16_offset_for_python_index,
)
from social_cluster.emoticon_input import EmoticonLineEditConverter


class TestEmoticonMap(unittest.TestCase):
    def test_common_mappings(self):
        self.assertEqual(EMOTICON_MAP[":)"], "🙂")
        self.assertEqual(EMOTICON_MAP[":("], "🙁")
        self.assertEqual(EMOTICON_MAP[":D"], "😃")
        self.assertEqual(EMOTICON_MAP["<3"], "❤️")

    def test_disabled_by_default(self):
        self.assertFalse(DEFAULT_CONFIG["emoticons_to_emoji"])


class TestEmoticonMatching(unittest.TestCase):
    def test_match_at_end(self):
        self.assertEqual(match_emoticon_at_end("hello :)"), (":)", "🙂"))

    def test_match_variant_at_end(self):
        self.assertEqual(match_emoticon_at_end("sad :-("), (":-(", "🙁"))

    def test_no_match(self):
        self.assertIsNone(match_emoticon_at_end("plain text"))
        self.assertIsNone(match_emoticon_at_end(""))

    def test_find_replacement_at_cursor(self):
        text = "hello :)"
        self.assertEqual(
            find_emoticon_replacement(text, len(text)),
            (6, 8, ":)", "🙂"),
        )

    def test_find_replacement_in_middle(self):
        text = "say :) now"
        cursor = len("say :)")
        self.assertEqual(
            find_emoticon_replacement(text, cursor),
            (4, 6, ":)", "🙂"),
        )

    def test_find_replacement_requires_emoticon_before_cursor(self):
        self.assertIsNone(find_emoticon_replacement("say :) now", len("say ")))
        self.assertIsNone(find_emoticon_replacement("plain", 5))

    def test_find_replacement_rejects_invalid_cursor(self):
        self.assertIsNone(find_emoticon_replacement(":)", -1))
        self.assertIsNone(find_emoticon_replacement(":)", 3))

    def test_find_replacement_rejects_emoticon_embedded_in_word(self):
        self.assertIsNone(find_emoticon_replacement("hello:)", len("hello:)")))
        self.assertIsNone(find_emoticon_replacement("https:/", len("https:/")))

    def test_find_replacement_allows_non_word_boundary(self):
        self.assertIsNotNone(find_emoticon_replacement("😀:)", len("😀:)")))
        self.assertIsNotNone(find_emoticon_replacement("(:)", len("(:)")))


class TestUtf16Offsets(unittest.TestCase):
    def test_python_index_for_utf16_offset(self):
        text = "😀:)"
        self.assertEqual(python_index_for_utf16_offset(text, 0), 0)
        self.assertEqual(python_index_for_utf16_offset(text, 2), 1)
        self.assertEqual(python_index_for_utf16_offset(text, 4), 3)

    def test_python_index_rejects_invalid_utf16_offset(self):
        self.assertIsNone(python_index_for_utf16_offset("😀:)", 1))
        self.assertIsNone(python_index_for_utf16_offset("😀:)", -1))
        self.assertIsNone(python_index_for_utf16_offset("😀:)", 5))

    def test_utf16_offset_for_python_index(self):
        text = "😀:)"
        self.assertEqual(utf16_offset_for_python_index(text, 0), 0)
        self.assertEqual(utf16_offset_for_python_index(text, 1), 2)
        self.assertEqual(utf16_offset_for_python_index(text, 3), 4)

    def test_utf16_offset_rejects_invalid_python_index(self):
        self.assertIsNone(utf16_offset_for_python_index("😀:)", -1))
        self.assertIsNone(utf16_offset_for_python_index("😀:)", 4))


class TestEmoticonLineEditConverter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.config = dict(DEFAULT_CONFIG)
        self.config["emoticons_to_emoji"] = True
        self.converter = EmoticonLineEditConverter(self.config)
        self.edit = QLineEdit()
        self.converter.install_on(self.edit)

    def tearDown(self):
        self.edit.removeEventFilter(self.converter)
        self.edit.deleteLater()

    def _type(self, chars):
        for c in chars:
            key = ord(c.upper()) if c.isalpha() else ord(c)
            event = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, c)
            QApplication.sendEvent(self.edit, event)
            QApplication.processEvents()

    def test_enabled_converts_smiley(self):
        self._type(":)")
        self.assertEqual(self.edit.text(), "🙂")

    def test_disabled_leaves_emoticon(self):
        self.config["emoticons_to_emoji"] = False
        self._type(":)")
        self.assertEqual(self.edit.text(), ":)")

    def test_converts_at_cursor_in_middle(self):
        self.edit.setText("hello  world")
        self.edit.setCursorPosition(6)
        self._type(":)")
        self.assertEqual(self.edit.text(), "hello 🙂 world")

    def test_converts_heart(self):
        self._type("<3")
        self.assertEqual(self.edit.text(), "❤️")

    def test_converts_after_astral_unicode_character(self):
        self.edit.setText("😀")
        self._type(":)")
        self.assertEqual(self.edit.text(), "😀🙂")

    def test_url_scheme_not_converted(self):
        self._type("https://")
        self.assertEqual(self.edit.text(), "https://")

    def test_undo_restores_emoticon_without_reconverting(self):
        self._type(":)")
        self.edit.undo()
        QApplication.processEvents()
        self.assertEqual(self.edit.text(), ":)")

    def test_password_field_not_converted(self):
        self.edit.setEchoMode(QLineEdit.Password)
        self._type(":)")
        self.assertEqual(self.edit.text(), ":)")

    def test_readonly_programmatic_text_not_converted(self):
        self.edit.setReadOnly(True)
        self.edit.setText(":)")
        self.assertEqual(self.edit.text(), ":)")


if __name__ == "__main__":
    unittest.main()
