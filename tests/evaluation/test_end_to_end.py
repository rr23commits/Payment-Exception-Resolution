from pathlib import Path
import unittest

from src.evaluation import MODEL_ABLATION, run_engine_proof
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions


SOURCE = Path("data/raw/transactions.csv")


class EndToEndProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.records = read_source_transactions(SOURCE, version)

    def test_complete_no_ui_pipeline_is_reproducible(self) -> None:
        first = run_engine_proof(self.records)
        second = run_engine_proof(self.records)

        self.assertEqual(first, second)
        self.assertEqual(first["pipeline"]["evaluated_incidents"], len(self.records))
        self.assertEqual(first["pipeline"]["verified_resolutions"], len(self.records))
        self.assertGreater(first["pipeline"]["audit_record_count"], len(self.records))
        self.assertFalse(first["execution_scope"]["ui_required"])
        self.assertFalse(first["execution_scope"]["api_required"])
        self.assertFalse(first["execution_scope"]["money_moving_integration"])

    def test_report_compares_existing_baseline_and_model(self) -> None:
        report = run_engine_proof(self.records)
        baseline = report["performance_comparison"]["baseline_test"]
        model = report["performance_comparison"]["model_test"]

        self.assertEqual(report["definitions"]["model"]["ablation"], MODEL_ABLATION)
        self.assertGreater(model["roc_auc"], baseline["roc_auc"])
        self.assertLess(model["false_escalation_rate"], baseline["false_escalation_rate"])
        self.assertEqual(report["pipeline"]["intervention_recall"], model["recall"])
        self.assertEqual(report["pipeline"]["false_escalation_rate"], model["false_escalation_rate"])
        self.assertIn("not applicable", report["resolution_time_error"])
