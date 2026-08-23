import unittest

from src.domain.state_machine import (
    EVIDENCE_REQUIREMENTS,
    TRANSITIONS,
    EvidenceType,
    InvalidTransition,
    PaymentState,
    apply_evidence,
    next_state,
)


class StateMachineTests(unittest.TestCase):
    def test_every_allowed_transition_has_required_evidence(self) -> None:
        for current, transitions in TRANSITIONS.items():
            for evidence, expected in transitions.items():
                with self.subTest(current=current, evidence=evidence):
                    self.assertIn(evidence, EVIDENCE_REQUIREMENTS)
                    self.assertEqual(next_state(current, evidence), expected)

    def test_invalid_transition_is_rejected(self) -> None:
        with self.assertRaisesRegex(InvalidTransition, "SETTLEMENT_CONFIRMED cannot transition from INITIATED"):
            next_state(PaymentState.INITIATED, EvidenceType.SETTLEMENT_CONFIRMED)
        with self.assertRaises(InvalidTransition):
            next_state(PaymentState.SETTLED, EvidenceType.REFUND_CONFIRMED)
        with self.assertRaises(InvalidTransition):
            next_state(None, "SUCCESS")  # Source CSV status is not lifecycle evidence.

    def test_normal_lifecycle_reaches_settlement(self) -> None:
        self.assertEqual(
            apply_evidence(
                [
                    EvidenceType.INITIATION_RECORDED,
                    EvidenceType.AUTHORIZATION_CONFIRMED,
                    EvidenceType.CAPTURE_CONFIRMED,
                    EvidenceType.SETTLEMENT_CONFIRMED,
                ]
            ),
            PaymentState.SETTLED,
        )

    def test_required_exception_paths_are_representable(self) -> None:
        timeout_reversal = [
            EvidenceType.INITIATION_RECORDED,
            EvidenceType.BANK_DEBIT_CONFIRMED,
            EvidenceType.GATEWAY_TIMEOUT_RECORDED,
            EvidenceType.REVERSAL_REQUESTED,
            EvidenceType.REVERSAL_CONFIRMED,
        ]
        merchant_failure_refund = [
            EvidenceType.INITIATION_RECORDED,
            EvidenceType.BANK_DEBIT_CONFIRMED,
            EvidenceType.PAYMENT_SUCCESS_CONFIRMED,
            EvidenceType.ORDER_FAILURE_CONFIRMED,
            EvidenceType.REFUND_REQUESTED,
            EvidenceType.REFUND_CONFIRMED,
        ]
        self.assertEqual(apply_evidence(timeout_reversal), PaymentState.REVERSED)
        self.assertEqual(apply_evidence(merchant_failure_refund), PaymentState.REFUNDED)
