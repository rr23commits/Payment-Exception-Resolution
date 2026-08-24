from datetime import datetime, timezone
import unittest

from src.domain.state_machine import PaymentState
from src.engine.exceptions import ExceptionIncident, ExceptionKind
from src.engine.reconstruction import StateSnapshot
from src.policy import MoneyMovingOperation, PolicyAction, PredictionSignal, recommend


def snapshot(state: PaymentState) -> StateSnapshot:
    return StateSnapshot("txn-1", datetime(2026, 1, 1, tzinfo=timezone.utc), state, (), ())


def incident(kind: ExceptionKind, state: PaymentState) -> ExceptionIncident:
    return ExceptionIncident("txn-1", kind, state, (), kind.value)


class PolicyTests(unittest.TestCase):
    def test_model_output_is_limited_to_the_policy_catalogue(self) -> None:
        decision = recommend(snapshot(PaymentState.REVERSAL_PENDING), prediction=PredictionSignal(True, 0.8))

        self.assertEqual(decision.action, PolicyAction.RECHECK_RECONCILE)
        self.assertIn(decision.action, set(PolicyAction))

    def test_money_moving_operations_always_require_human_approval(self) -> None:
        for operation in MoneyMovingOperation:
            decision = recommend(snapshot(PaymentState.PAYMENT_SUCCESS), requested_operation=operation)
            self.assertEqual(decision.action, PolicyAction.REQUIRE_HUMAN_APPROVAL)
            self.assertEqual(decision.requested_operation, operation)

    def test_retry_requires_human_approval(self) -> None:
        decision = recommend(snapshot(PaymentState.GATEWAY_TIMEOUT), requested_operation=MoneyMovingOperation.RETRY)

        self.assertEqual(decision.action, PolicyAction.REQUIRE_HUMAN_APPROVAL)

    def test_state_truth_is_not_overridden_by_prediction(self) -> None:
        decision = recommend(snapshot(PaymentState.SETTLED), prediction=PredictionSignal(True, 0.99))

        self.assertEqual(decision.state, PaymentState.SETTLED)
        self.assertEqual(decision.action, PolicyAction.MONITOR)

    def test_deterministic_findings_take_precedence_over_prediction(self) -> None:
        decision = recommend(
            snapshot(PaymentState.REFUND_PENDING),
            (incident(ExceptionKind.REFUND_PENDING_STUCK, PaymentState.REFUND_PENDING),),
            PredictionSignal(False, 0.01),
        )

        self.assertEqual(decision.action, PolicyAction.ESCALATE)

    def test_same_inputs_produce_the_same_safe_action(self) -> None:
        inputs = (snapshot(PaymentState.GATEWAY_TIMEOUT), (incident(ExceptionKind.TIMEOUT_TO_REVERSAL, PaymentState.GATEWAY_TIMEOUT),), PredictionSignal(False, 0.2))

        self.assertEqual(recommend(*inputs), recommend(*inputs))

    def test_prediction_probability_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            PredictionSignal(True, 1.01)
