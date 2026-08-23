from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class UiTests(unittest.TestCase):
    def test_demo_uses_only_existing_read_only_api_records(self) -> None:
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")

        for endpoint in ("/incidents", "/state", "/predictions", "/resolution", "/audit", "/evaluation"):
            self.assertIn(endpoint, script)
        self.assertNotIn("POST", script)
        self.assertNotIn("refund", script.lower())

    def test_demo_labels_generated_data_and_has_no_money_controls(self) -> None:
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")

        self.assertIn("Simulated controlled data only", html)
        self.assertIn("cannot move money", html)
        self.assertNotIn("<button", html)
        self.assertNotIn("<form", html)
