from decimal import Decimal
from pathlib import Path
import unittest

from src.evaluation import build_engine_records
from src.features import build_feature_row
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.ml.experiment import ABLATIONS, build_rows, fit_model, model_probability
from src.recovery import RecoveryStatus, apply_decision, create_opportunity, metrics, read_model, retry_policy, simulate_retry


SOURCE = Path("data/raw/transactions.csv")


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.records = build_engine_records(read_source_transactions(SOURCE, version))

    def test_only_timeout_records_create_one_policy_gated_opportunity(self) -> None:
        timeout = next(record for record in self.records if create_opportunity(record) is not None)
        non_timeout = next(record for record in self.records if create_opportunity(record) is None)
        opportunity = create_opportunity(timeout)

        self.assertIsNone(create_opportunity(non_timeout))
        self.assertEqual(opportunity.transaction_id, timeout.source.transaction_id)
        self.assertTrue(opportunity.incident_ids)
        self.assertEqual(retry_policy(timeout).action.value, "REQUIRE HUMAN APPROVAL")

    def test_rejection_and_one_approved_retry_have_correct_simulated_amounts(self) -> None:
        record = next(record for record in self.records if create_opportunity(record) is not None)
        opportunity = create_opportunity(record)
        rejected = apply_decision(opportunity, False)
        succeeded = simulate_retry(apply_decision(opportunity, True))

        self.assertEqual(rejected.status, RecoveryStatus.REJECTED)
        self.assertEqual(metrics(rejected).simulated_recovered_revenue, Decimal("0"))
        self.assertEqual(succeeded.status, RecoveryStatus.SIMULATED_SUCCEEDED)
        self.assertEqual(metrics(succeeded).simulated_recovered_revenue, record.source.amount_inr)
        with self.assertRaisesRegex(ValueError, "approved"):
            simulate_retry(succeeded)
        self.assertEqual(metrics(type(opportunity)(opportunity.opportunity_id, opportunity.transaction_id, opportunity.incident_ids, Decimal("0"), opportunity.recommended_action, opportunity.status)).simulated_recovery_rate, Decimal("0"))

    def test_recovery_prediction_uses_the_timeout_snapshot_cutoff(self) -> None:
        record = next(record for record in self.records if create_opportunity(record) is not None)
        opportunity = create_opportunity(record)
        policy = retry_policy(record)

        self.assertEqual(
            record.recovery_features,
            build_feature_row(record.source, record.instance, record.instance.observation_cutoff),
        )
        feature_names = ABLATIONS["plus_complaint_signals"]
        expected_probability = model_probability(
            fit_model(build_rows([item.source for item in self.records]), feature_names),
            record.recovery_features,
            feature_names,
        )
        self.assertEqual(record.recovery_prediction.probability, expected_probability)
        self.assertEqual(read_model(record, opportunity, policy).model_probability, record.recovery_prediction.probability)
