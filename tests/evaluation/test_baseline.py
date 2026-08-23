from collections import defaultdict
from dataclasses import replace
from pathlib import Path
import unittest

from src.baseline import TARGET_DEFINITION_VERSION, derive_target, fit, pending_observation_cutoff
from src.baseline.evaluate import evaluate
from src.domain.scenarios import SCENARIOS
from src.domain.state_machine import apply_evidence
from src.engine.reconstruction import reconstruct_state
from src.features import build_feature_row
from src.generation import generate_scenario_instance
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.ml import DatasetSplit, split_for_transaction


SOURCE = Path("data/raw/transactions.csv")


class BaselineEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.records = read_source_transactions(SOURCE, version)
        cls.source = cls.records[0]

    def test_pending_targets_are_controlled_deterministic_and_baseline_uses_same_cutoff(self) -> None:
        features = []
        targets = []
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.scenario_id):
                instance = generate_scenario_instance(self.source, scenario)
                cutoff = pending_observation_cutoff(instance)
                feature = build_feature_row(self.source, instance, cutoff)
                target = derive_target(instance, cutoff)

                self.assertEqual(target, derive_target(instance, cutoff))
                self.assertIn(feature.model_inputs["reconstructed_state"], {"REVERSAL_PENDING", "REFUND_PENDING"})
                self.assertNotIn("requires_intervention", feature.model_inputs)
                self.assertEqual(feature.model_inputs["observed_complaint_count"], 1)
                self.assertEqual(feature.model_inputs["observed_high_severity_complaint_count"], 1)
                features.append(feature)
                targets.append(target)
        self.assertEqual(TARGET_DEFINITION_VERSION, "pending-window-v2")
        self.assertIn(fit(features, targets).predict(features[0]).intervention_probability, {0.5})

    def test_split_is_stable_and_report_records_versions_and_metrics(self) -> None:
        report = evaluate(self.records)

        self.assertEqual(split_for_transaction(self.source.transaction_id), split_for_transaction(self.source.transaction_id))
        self.assertIn(split_for_transaction(self.source.transaction_id), set(DatasetSplit))
        self.assertEqual(report["row_count"], len(self.records))
        self.assertEqual(set(report["versions"]), {"dataset", "scenario_assignment", "state_machine", "feature_definition", "target_definition", "observation_plan", "split"})
        self.assertLess(report["metrics"]["all"]["intervention_accuracy"], 1.0)
        self.assertIn("brier_score", report["metrics"]["all"])
        self.assertGreater(
            report["target_distribution"]["intervention_rate_by_amount_band"]["high_amount"],
            report["target_distribution"]["intervention_rate_by_amount_band"]["low_amount"],
        )

    def test_friction_timing_varies_without_turning_elapsed_time_into_a_label(self) -> None:
        elapsed_by_state_and_label = defaultdict(lambda: defaultdict(set))
        for source in self.records:
            instance = generate_scenario_instance(source)
            cutoff = pending_observation_cutoff(instance)
            feature = build_feature_row(source, instance, cutoff)
            state = feature.model_inputs["reconstructed_state"]
            target = derive_target(instance, cutoff)

            self.assertTrue(all(later.event_time > earlier.event_time for earlier, later in zip(instance.events, instance.events[1:])))
            self.assertEqual(apply_evidence([event.event_type for event in instance.events]), instance.final_outcome)
            self.assertEqual(reconstruct_state(instance.events, cutoff).state.value, state)
            elapsed_by_state_and_label[state][target.requires_intervention].add(feature.model_inputs["elapsed_seconds"])

        for labels in elapsed_by_state_and_label.values():
            self.assertTrue(labels[True])
            self.assertTrue(labels[False])
            self.assertGreater(len(labels[True] | labels[False]), 1)
            self.assertTrue(labels[True] & labels[False])

    def test_hidden_confirmation_mutation_cannot_change_pending_features(self) -> None:
        source = self.source
        instance = generate_scenario_instance(source)
        cutoff = pending_observation_cutoff(instance)
        expected = build_feature_row(source, instance, cutoff)
        hidden_confirmation = next(event for event in instance.events if event.event_time > cutoff)
        altered = replace(instance, events=instance.events[:-1] + (replace(hidden_confirmation, source="MERCHANT"),))

        self.assertEqual(expected, build_feature_row(source, altered, cutoff))
