from pathlib import Path
import unittest

from src.baseline import pending_observation_cutoff
from src.domain.scenarios import SCENARIOS
from src.engine.exceptions import detect_exceptions
from src.engine.reconstruction import reconstruct_state
from src.features import build_feature_row
from src.generation import generate_scenario_instance
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.policy import MoneyMovingOperation, PredictionSignal, recommend
from src.provenance import ALL_PROVENANCE, HUMAN_DECISION, RESOLUTION_RESULT
from src.resolution import HumanDecision, ModeledHumanDecision, VersionedPrediction, open_resolution_case


SOURCE = Path("data/raw/transactions.csv")


class ResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.source = read_source_transactions(SOURCE, version)[0]

    def _case(self, requires_human: bool = False):
        instance = generate_scenario_instance(self.source, SCENARIOS[1])
        cutoff = pending_observation_cutoff(instance)
        snapshot = reconstruct_state(instance.events, cutoff)
        incidents = detect_exceptions(snapshot, instance.expected_resolution_window)
        features = build_feature_row(self.source, instance, cutoff)
        prediction = PredictionSignal(True, 0.8)
        policy = recommend(
            snapshot,
            incidents,
            prediction,
            MoneyMovingOperation.REFUND if requires_human else None,
        )
        versioned_prediction = VersionedPrediction("phase10-logistic-v1", prediction)
        return instance, open_resolution_case(instance, snapshot, incidents, features, (versioned_prediction,), policy)

    def test_complete_incident_is_replayable_and_verified_after_reveal(self) -> None:
        instance, case = self._case()
        verified = case.reveal_and_verify(instance)

        self.assertEqual(verified.audit_trail.replay(), verified.audit_trail.records)
        self.assertEqual(verified.verification.final_outcome, instance.final_outcome)
        self.assertEqual(verified.verification.requires_intervention, instance.requires_intervention)
        self.assertEqual(verified.audit_trail.records[-1].provenance, RESOLUTION_RESULT)
        prediction_record = next(record for record in verified.audit_trail.records if record.record_type == "PREDICTION")
        self.assertEqual(prediction_record.payload.model_version, "phase10-logistic-v1")
        self.assertIn("OBSERVED_COMPLAINT", [record.record_type for record in verified.audit_trail.records])

    def test_audit_preserves_ordering_and_provenance(self) -> None:
        instance, case = self._case()
        verified = case.reveal_and_verify(instance)

        self.assertEqual([record.sequence_number for record in verified.audit_trail.records], list(range(1, len(verified.audit_trail.records) + 1)))
        self.assertTrue(all(record.provenance in ALL_PROVENANCE for record in verified.audit_trail.records))

    def test_human_decision_is_recorded_without_a_payment_executor(self) -> None:
        for decision in HumanDecision:
            instance, case = self._case(requires_human=True)
            with_human = case.record_human_decision(ModeledHumanDecision(decision, "reviewed evidence"))
            verified = with_human.reveal_and_verify(instance)

            self.assertEqual(with_human.human_decision.decision, decision)
            self.assertIn(HUMAN_DECISION, [record.provenance for record in verified.audit_trail.records])
            self.assertFalse(hasattr(with_human, "execute_payment"))

    def test_revealed_truth_does_not_change_earlier_feature_snapshot(self) -> None:
        instance, case = self._case()
        before_reveal = case.feature_snapshot.model_inputs
        verified = case.reveal_and_verify(instance)
        feature_index = next(index for index, record in enumerate(verified.audit_trail.records) if record.record_type == "FEATURE_SNAPSHOT")
        reveal_index = next(index for index, record in enumerate(verified.audit_trail.records) if record.record_type == "REVEALED_FUTURE_EVENT")

        self.assertEqual(verified.feature_snapshot.model_inputs, before_reveal)
        self.assertLess(feature_index, reveal_index)
