from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import unittest

from src.domain.scenarios import SCENARIOS
from src.domain.state_machine import PaymentState
from src.engine.exceptions import ExceptionKind, detect_exceptions
from src.engine.reconstruction import reconstruct_state
from src.generation import generate_scenario_instance
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions


SOURCE = Path("data/raw/transactions.csv")


class DeterministicEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.source = read_source_transactions(SOURCE, version)[0]

    def test_reconstruction_uses_only_evidence_at_each_cutoff(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[2])
        at_observation = reconstruct_state(instance.events, instance.observation_cutoff)
        after_completion = reconstruct_state(instance.events, instance.events[-1].event_time)

        self.assertEqual(at_observation.state, PaymentState.ORDER_FAILED)
        self.assertEqual(after_completion.state, PaymentState.REFUNDED)
        self.assertNotIn(instance.hidden_future_events[0].event_id, {step.event_id for step in at_observation.evidence_path})

    def test_contradictory_evidence_is_reported_without_changing_valid_state(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[0])
        bad_event = replace(instance.observed_events[-1], source="MERCHANT")
        snapshot = reconstruct_state(instance.observed_events[:-1] + (bad_event,), instance.observation_cutoff)
        incidents = detect_exceptions(snapshot)

        self.assertEqual(snapshot.state, PaymentState.BANK_DEBITED)
        self.assertEqual([incident.kind for incident in incidents], [ExceptionKind.CONTRADICTORY_EVIDENCE])

    def test_window_violations_are_detected_from_observed_time_not_hidden_outcome(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[1])
        cutoff = instance.events[0].event_time + timedelta(minutes=11)
        snapshot = reconstruct_state(instance.events, cutoff)
        incidents = detect_exceptions(snapshot, instance.expected_resolution_window)

        self.assertEqual(snapshot.state, PaymentState.REVERSAL_PENDING)
        self.assertIn(ExceptionKind.DELAYED_STUCK_REVERSAL, {incident.kind for incident in incidents})
        self.assertNotIn(instance.hidden_future_events[0].event_id, {step.event_id for step in snapshot.evidence_path})

    def test_engine_does_not_need_ml_or_scenario_metadata(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[0])
        snapshot = reconstruct_state(instance.observed_events, instance.observation_cutoff)
        incidents = detect_exceptions(snapshot, instance.expected_resolution_window)

        self.assertEqual(snapshot.state, PaymentState.GATEWAY_TIMEOUT)
        self.assertEqual([incident.kind for incident in incidents], [ExceptionKind.TIMEOUT_TO_REVERSAL])

    def test_merchant_mismatch_and_stuck_refund_patterns_are_detected(self) -> None:
        mismatch = generate_scenario_instance(self.source, SCENARIOS[2])
        mismatch_snapshot = reconstruct_state(mismatch.events, mismatch.observation_cutoff)
        stuck_refund = generate_scenario_instance(self.source, SCENARIOS[3])
        cutoff = stuck_refund.events[0].event_time + timedelta(minutes=13)
        refund_snapshot = reconstruct_state(stuck_refund.events, cutoff)

        self.assertIn(ExceptionKind.STATE_MERCHANT_MISMATCH, {incident.kind for incident in detect_exceptions(mismatch_snapshot)})
        self.assertIn(
            ExceptionKind.REFUND_PENDING_STUCK,
            {incident.kind for incident in detect_exceptions(refund_snapshot, stuck_refund.expected_resolution_window)},
        )
