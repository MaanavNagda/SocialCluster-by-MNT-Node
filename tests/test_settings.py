import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineProfile

from social_cluster.config import DEFAULT_CONFIG, load_config
from social_cluster.main import MainWindow


class TestEmoticonSetting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._orig_xdg = os.environ.get("XDG_CONFIG_HOME")
        self._temp = tempfile.TemporaryDirectory()
        os.environ["XDG_CONFIG_HOME"] = self._temp.name
        self.config = dict(DEFAULT_CONFIG)
        self.profile = QWebEngineProfile()
        self._ipc_patcher = patch.object(
            MainWindow,
            "_setup_ipc_server",
            lambda _window: None,
        )
        self._ipc_patcher.start()
        self.window = MainWindow(self.config, self.profile)

    def tearDown(self):
        self.window.deleteLater()
        self.profile.deleteLater()
        self._ipc_patcher.stop()
        QApplication.processEvents()
        if self._orig_xdg is not None:
            os.environ["XDG_CONFIG_HOME"] = self._orig_xdg
        else:
            os.environ.pop("XDG_CONFIG_HOME", None)
        self._temp.cleanup()

    def test_checkbox_uses_disabled_default(self):
        self.assertFalse(self.window._emoticons_check.isChecked())
        self.assertFalse(self.config["emoticons_to_emoji"])

    def test_toggling_checkbox_saves_setting(self):
        self.window._emoticons_check.setChecked(True)
        QApplication.processEvents()
        self.assertTrue(self.config["emoticons_to_emoji"])
        self.assertTrue(load_config()["emoticons_to_emoji"])

    def test_cancel_restores_setting_snapshot(self):
        self.window._stack.setCurrentIndex(2)
        self.window._emoticons_check.setChecked(True)
        QApplication.processEvents()
        self.window._cancel_settings()
        QApplication.processEvents()
        self.assertFalse(self.config["emoticons_to_emoji"])
        self.assertFalse(self.window._emoticons_check.isChecked())
        self.assertFalse(load_config()["emoticons_to_emoji"])


if __name__ == "__main__":
    unittest.main()
