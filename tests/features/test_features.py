from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import unittest

from src.domain.scenarios import SCENARIOS
from src.features import FEATURE_DEFINITION_VERSION, build_feature_row
from src.generation import generate_scenario_instance
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions


SOURCE = Path("data/raw/transactions.csv")


class FeatureConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.source = read_source_transactions(SOURCE, version)[0]

    def test_feature_row_is_repeatable_and_contains_only_model_inputs(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[3])
        first = build_feature_row(self.source, instance, instance.observation_cutoff)
        second = build_feature_row(self.source, instance, instance.observation_cutoff)

        self.assertEqual(first, second)
        self.assertEqual(first.feature_version, FEATURE_DEFINITION_VERSION)
        self.assertEqual(first.values, first.model_inputs)
        self.assertEqual(first.values["reconstructed_state"], "REFUND_PENDING")
        self.assertEqual(first.values["observed_complaint_count"], 1)
        self.assertEqual(first.values["observed_high_severity_complaint_count"], 1)
        self.assertNotIn("scenario_id", first.values)
        self.assertNotIn("final_outcome", first.values)
        self.assertNotIn("requires_intervention", first.values)
        self.assertNotIn("status", first.values)

    def test_features_change_with_the_observation_cutoff(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[2])
        at_cutoff = build_feature_row(self.source, instance, instance.observation_cutoff)
        after_completion = build_feature_row(self.source, instance, instance.events[-1].event_time)

        self.assertEqual(at_cutoff.values["observed_event_count"], 4)
        self.assertEqual(after_completion.values["observed_event_count"], 6)
        self.assertEqual(at_cutoff.values["reconstructed_state"], "ORDER_FAILED")
        self.assertEqual(after_completion.values["reconstructed_state"], "REFUNDED")
        self.assertLess(at_cutoff.values["elapsed_seconds"], after_completion.values["elapsed_seconds"])

    def test_hidden_future_events_and_complaints_cannot_change_cutoff_features(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[0])
        expected = build_feature_row(self.source, instance, instance.observation_cutoff)
        changed_hidden_event = replace(instance.hidden_future_events[0], source="MERCHANT")
        changed_hidden_complaint = replace(instance.hidden_future_complaints[0], text="future-only mutation")
        altered = replace(
            instance,
            events=instance.events[:-1] + (changed_hidden_event,),
            complaints=(changed_hidden_complaint,),
        )

        self.assertEqual(expected, build_feature_row(self.source, altered, altered.observation_cutoff))
        self.assertEqual(expected.values["observed_complaint_count"], 0)

    def test_source_and_instance_identity_must_match(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[0])
        unrelated = replace(self.source, transaction_id="different")

        with self.assertRaisesRegex(ValueError, "must match"):
            build_feature_row(unrelated, instance, instance.observation_cutoff)
