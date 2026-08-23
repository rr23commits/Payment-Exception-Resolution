from pathlib import Path
import unittest

from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.ml.experiment import ABLATIONS, RANDOM_SEED, build_rows, run_experiment


SOURCE = Path("data/raw/transactions.csv")


class MlExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.records = read_source_transactions(SOURCE, version)

    def test_rows_use_pending_cutoff_and_exclude_targets(self) -> None:
        rows = build_rows(self.records[:8])

        self.assertTrue(rows)
        self.assertTrue(all(row.features.model_inputs["reconstructed_state"] in {"REVERSAL_PENDING", "REFUND_PENDING"} for row in rows))
        self.assertTrue(all("requires_intervention" not in row.features.model_inputs for row in rows))

    def test_experiment_is_reproducible_and_reports_all_ablations(self) -> None:
        first = run_experiment(self.records)
        second = run_experiment(self.records)

        self.assertEqual(first, second)
        self.assertEqual(set(first["models"]["ablations"]), set(ABLATIONS))
        self.assertEqual(first["models"]["parameters"]["random_state"], RANDOM_SEED)
        self.assertEqual(first["row_count"], len(self.records))
        payment_auc = first["models"]["ablations"]["payment_attributes"]["metrics"]["test"]["roc_auc"]
        history_auc = first["models"]["ablations"]["plus_event_history_timing"]["metrics"]["test"]["roc_auc"]
        self.assertGreater(history_auc, payment_auc + 0.1)
