import os
import tempfile
import unittest

from social_cluster import APP_NAME, __version__
from social_cluster.config import DEFAULT_CONFIG, load_config, save_config
from social_cluster.services import get_default_services, get_service_by_name
from social_cluster.themes import get_stylesheet, get_theme, get_theme_names
from social_cluster.tray import render_tray_icon


class TestServices(unittest.TestCase):
    def test_default_services_not_empty(self):
        services = get_default_services()
        self.assertGreater(len(services), 0)

    def test_get_service_by_name(self):
        s = get_service_by_name("Facebook")
        self.assertIsNotNone(s)
        self.assertEqual(s["name"], "Facebook")
        self.assertTrue(s["url"].startswith("https://"))

    def test_get_service_by_name_missing(self):
        self.assertIsNone(get_service_by_name("DoesNotExist"))


class TestThemes(unittest.TestCase):
    def test_names(self):
        names = get_theme_names()
        self.assertIn("amethyst", names)
        self.assertIn("ruby", names)

    def test_theme_keys(self):
        t = get_theme("sapphire", dark=True)
        self.assertEqual(t["name"], "sapphire")
        self.assertTrue(t["dark"])
        for key in ("primary", "secondary", "bg", "fg", "panel"):
            self.assertIn(key, t)

    def test_stylesheet(self):
        t = get_theme("emerald", dark=False)
        sheet = get_stylesheet(t)
        self.assertIn("QTabWidget", sheet)
        self.assertIn(t["primary"], sheet)


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._orig_xdg = os.environ.get("XDG_CONFIG_HOME")
        self._temp = tempfile.TemporaryDirectory()
        os.environ["XDG_CONFIG_HOME"] = self._temp.name

    def tearDown(self):
        if self._orig_xdg is not None:
            os.environ["XDG_CONFIG_HOME"] = self._orig_xdg
        else:
            os.environ.pop("XDG_CONFIG_HOME", None)
        self._temp.cleanup()

    def test_load_defaults(self):
        c = load_config()
        for key, value in DEFAULT_CONFIG.items():
            self.assertEqual(c[key], value)

    def test_save_and_load(self):
        c = load_config()
        c["theme"] = "ruby"
        c["dark_mode"] = True
        save_config(c)
        c2 = load_config()
        self.assertEqual(c2["theme"], "ruby")
        self.assertTrue(c2["dark_mode"])


class TestTray(unittest.TestCase):
    def test_tray_icon(self):
        svg = render_tray_icon(5, "#3498db")
        self.assertIn("SC", svg)
        self.assertIn("5", svg)
        self.assertIn("<svg", svg)

    def test_tray_no_badge(self):
        svg = render_tray_icon(0, "#2ecc71")
        self.assertNotIn("<circle", svg)
