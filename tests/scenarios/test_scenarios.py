import unittest
from datetime import datetime, timedelta

from src.domain.scenarios import SCENARIOS, ScenarioId
from src.domain.scenarios.config import (
    ScenarioParameters,
    actual_resolution_duration,
    hidden_future_evidence,
    observed_evidence,
    parameters_for,
    requires_intervention,
)
from src.domain.state_machine import PaymentState, apply_evidence


class ScenarioTests(unittest.TestCase):
    def test_exactly_four_complete_valid_scenarios(self) -> None:
        self.assertEqual({scenario.scenario_id for scenario in SCENARIOS}, set(ScenarioId))
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.scenario_id):
                parameters = parameters_for(scenario)
                self.assertTrue(observed_evidence(scenario, parameters))
                self.assertTrue(hidden_future_evidence(scenario, parameters))
                self.assertEqual(
                    observed_evidence(scenario, parameters) + hidden_future_evidence(scenario, parameters),
                    scenario.evidence,
                )
                self.assertEqual(scenario.final_outcome, apply_evidence(list(scenario.evidence)))
                self.assertIn(scenario.final_outcome, {PaymentState.REVERSED, PaymentState.REFUNDED})

    def test_timestamps_derive_resolution_duration_and_intervention_ground_truth(self) -> None:
        start = datetime(2026, 1, 1, 9, 0)
        expected = {
            ScenarioId.TIMEOUT_TO_REVERSAL: False,
            ScenarioId.DELAYED_STUCK_REVERSAL: True,
            ScenarioId.PAYMENT_SUCCESS_ORDER_FAILURE: False,
            ScenarioId.REFUND_PENDING_STUCK: True,
        }
        timestamps = {
            scenario.scenario_id: parameters_for(scenario).event_timestamps(start, len(scenario.evidence))
            for scenario in SCENARIOS
        }
        self.assertEqual(
            {scenario.scenario_id: requires_intervention(scenario, timestamps[scenario.scenario_id]) for scenario in SCENARIOS},
            expected,
        )
        self.assertEqual(actual_resolution_duration(timestamps[ScenarioId.TIMEOUT_TO_REVERSAL]), timedelta(minutes=6))
        self.assertEqual(actual_resolution_duration(timestamps[ScenarioId.DELAYED_STUCK_REVERSAL]), timedelta(minutes=18))
        self.assertFalse(hasattr(SCENARIOS[0], "simulated_resolution_duration"))

    def test_experimental_window_remains_configurable(self) -> None:
        scenario = SCENARIOS[0]
        defaults = parameters_for(scenario)
        parameters = ScenarioParameters(
            defaults.observation_cutoff_index,
            defaults.event_offsets,
            timedelta(minutes=5),
        )
        self.assertEqual(
            requires_intervention(
                scenario,
                parameters.event_timestamps(datetime(2026, 1, 1), len(scenario.evidence)),
                parameters,
            ),
            True,
        )
        with self.assertRaises(ValueError):
            ScenarioParameters(0, (timedelta(), timedelta(minutes=1)), timedelta()).validate(2)

    def test_merchant_evidence_is_present_only_for_order_failure_paths(self) -> None:
        merchant_scenarios = {scenario.scenario_id for scenario in SCENARIOS if scenario.merchant_evidence}
        self.assertEqual(
            merchant_scenarios,
            {ScenarioId.PAYMENT_SUCCESS_ORDER_FAILURE, ScenarioId.REFUND_PENDING_STUCK},
        )
