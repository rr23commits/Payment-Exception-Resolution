from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class UiTests(unittest.TestCase):
    def test_demo_uses_existing_records_and_only_the_recovery_write_route(self) -> None:
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")

        for endpoint in ("/incidents", "/state", "/audit"):
            self.assertIn(endpoint, script)
        self.assertIn("/recovery", script)
        self.assertIn("/recovery/decision", script)
        self.assertIn("Retry recovery available", script)
        self.assertIn('method: "POST"', script)
        self.assertNotIn("refund", script.lower())

    def test_demo_labels_generated_data_and_limits_controls_to_simulated_recovery(self) -> None:
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")

        self.assertIn("Simulated controlled data only", html)
        self.assertIn("cannot move money", html)
        self.assertIn('id="recovery"', html)
        self.assertNotIn("<form", html)

    def test_demo_has_queue_investigation_and_customer_views_without_emojis(self) -> None:
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")

        for text in ("Professional work queue", "What happened", "Customer status", "Recovery status"):
            self.assertIn(text, html)
        self.assertIn("queue-search", script)
        self.assertIn("View Raw Payload (JSON)", html)
        self.assertNotIn("Audit history", html)
        self.assertNotIn("😀", html + script)
