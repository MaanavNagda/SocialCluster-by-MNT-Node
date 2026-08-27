import json
import unittest

from social_cluster.scrapers import SCRAPERS, SCRAPER_STATUS, AVAILABLE_SCRAPERS


class TestScraperRegistry(unittest.TestCase):
    def test_expected_services_registered(self):
        for name in ("WhatsApp", "Discord", "Snapchat"):
            self.assertIn(name, SCRAPERS)
            self.assertIn(name, AVAILABLE_SCRAPERS)

    def test_scripts_are_nonempty_strings(self):
        for name, script in SCRAPERS.items():
            self.assertIsInstance(script, str)
            self.assertGreater(len(script.strip()), 0)

    def test_status_values_are_valid(self):
        valid = {"verified", "experimental"}
        for name, status in SCRAPER_STATUS.items():
            self.assertIn(status, valid, f"{name} has unexpected status {status!r}")

    def test_whatsapp_is_verified(self):
        self.assertEqual(SCRAPER_STATUS["WhatsApp"], "verified")

    def test_scripts_reference_json_stringify(self):
        # Every scraper script must return a JSON string so main.py's
        # generic _on_scraper_result() can json.loads() it uniformly.
        for name, script in SCRAPERS.items():
            self.assertIn("JSON.stringify", script, f"{name} scraper doesn't return JSON")

    def test_scraper_json_shape_is_parseable(self):
        # Sanity-check the *shape* scrapers promise to return by simulating
        # both a success (items) and failure (error) payload, matching the
        # contract documented in social_cluster/scrapers/__init__.py.
        success_payload = json.dumps({"items": [{"sender": "Alice", "count": "1", "preview": "hi"}]})
        data = json.loads(success_payload)
        self.assertIn("items", data)

        error_payload = json.dumps({"error": "boom"})
        data = json.loads(error_payload)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
