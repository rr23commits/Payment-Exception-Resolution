"""Deterministic payment-state semantics; independent of ML and source status."""

from enum import Enum


STATE_MACHINE_VERSION = "v1"


class PaymentState(str, Enum):
    INITIATED = "INITIATED"
    AUTHORIZED = "AUTHORIZED"
    BANK_DEBITED = "BANK_DEBITED"
    GATEWAY_TIMEOUT = "GATEWAY_TIMEOUT"
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    ORDER_FAILED = "ORDER_FAILED"
    CAPTURED = "CAPTURED"
    SETTLED = "SETTLED"
    REVERSAL_PENDING = "REVERSAL_PENDING"
    REVERSED = "REVERSED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class EvidenceType(str, Enum):
    INITIATION_RECORDED = "INITIATION_RECORDED"
    AUTHORIZATION_CONFIRMED = "AUTHORIZATION_CONFIRMED"
    BANK_DEBIT_CONFIRMED = "BANK_DEBIT_CONFIRMED"
    GATEWAY_TIMEOUT_RECORDED = "GATEWAY_TIMEOUT_RECORDED"
    PAYMENT_SUCCESS_CONFIRMED = "PAYMENT_SUCCESS_CONFIRMED"
    CAPTURE_CONFIRMED = "CAPTURE_CONFIRMED"
    SETTLEMENT_CONFIRMED = "SETTLEMENT_CONFIRMED"
    REVERSAL_REQUESTED = "REVERSAL_REQUESTED"
    REVERSAL_CONFIRMED = "REVERSAL_CONFIRMED"
    ORDER_FAILURE_CONFIRMED = "ORDER_FAILURE_CONFIRMED"
    REFUND_REQUESTED = "REFUND_REQUESTED"
    REFUND_CONFIRMED = "REFUND_CONFIRMED"


class InvalidTransition(ValueError):
    """Raised when evidence cannot deterministically justify the next state."""


# Each transition is authority-bearing only when the listed source supplies the fact.
EVIDENCE_REQUIREMENTS = {
    EvidenceType.INITIATION_RECORDED: ("PAYMENT EVENT HISTORY", "payment initiation"),
    EvidenceType.AUTHORIZATION_CONFIRMED: ("BANK / PAYMENT NETWORK", "authorization confirmation"),
    EvidenceType.BANK_DEBIT_CONFIRMED: ("BANK / PAYMENT NETWORK", "debit confirmation"),
    EvidenceType.GATEWAY_TIMEOUT_RECORDED: ("GATEWAY", "timeout record"),
    EvidenceType.PAYMENT_SUCCESS_CONFIRMED: ("BANK / PAYMENT NETWORK", "payment-success confirmation"),
    EvidenceType.CAPTURE_CONFIRMED: ("GATEWAY", "capture confirmation"),
    EvidenceType.SETTLEMENT_CONFIRMED: ("BANK / PAYMENT NETWORK", "settlement confirmation"),
    EvidenceType.REVERSAL_REQUESTED: ("GATEWAY", "reversal request"),
    EvidenceType.REVERSAL_CONFIRMED: ("BANK / PAYMENT NETWORK", "reversal confirmation"),
    EvidenceType.ORDER_FAILURE_CONFIRMED: ("MERCHANT", "order failure confirmation"),
    EvidenceType.REFUND_REQUESTED: ("MERCHANT", "refund request"),
    EvidenceType.REFUND_CONFIRMED: ("BANK / PAYMENT NETWORK", "refund confirmation"),
}


TRANSITIONS = {
    None: {EvidenceType.INITIATION_RECORDED: PaymentState.INITIATED},
    PaymentState.INITIATED: {
        EvidenceType.AUTHORIZATION_CONFIRMED: PaymentState.AUTHORIZED,
        EvidenceType.BANK_DEBIT_CONFIRMED: PaymentState.BANK_DEBITED,
    },
    PaymentState.AUTHORIZED: {EvidenceType.CAPTURE_CONFIRMED: PaymentState.CAPTURED},
    PaymentState.BANK_DEBITED: {
        EvidenceType.GATEWAY_TIMEOUT_RECORDED: PaymentState.GATEWAY_TIMEOUT,
        EvidenceType.PAYMENT_SUCCESS_CONFIRMED: PaymentState.PAYMENT_SUCCESS,
    },
    PaymentState.GATEWAY_TIMEOUT: {EvidenceType.REVERSAL_REQUESTED: PaymentState.REVERSAL_PENDING},
    PaymentState.REVERSAL_PENDING: {EvidenceType.REVERSAL_CONFIRMED: PaymentState.REVERSED},
    PaymentState.PAYMENT_SUCCESS: {EvidenceType.ORDER_FAILURE_CONFIRMED: PaymentState.ORDER_FAILED},
    PaymentState.ORDER_FAILED: {EvidenceType.REFUND_REQUESTED: PaymentState.REFUND_PENDING},
    PaymentState.REFUND_PENDING: {EvidenceType.REFUND_CONFIRMED: PaymentState.REFUNDED},
    PaymentState.CAPTURED: {EvidenceType.SETTLEMENT_CONFIRMED: PaymentState.SETTLED},
}


def next_state(current: PaymentState | None, evidence: EvidenceType) -> PaymentState:
    """Return the only valid next state; source CSV status is never accepted as evidence."""
    target = TRANSITIONS.get(current, {}).get(evidence)
    if target is None:
        current_name = current.value if isinstance(current, PaymentState) else "START"
        evidence_name = evidence.value if isinstance(evidence, EvidenceType) else repr(evidence)
        raise InvalidTransition(f"{evidence_name} cannot transition from {current_name}")
    return target


def apply_evidence(evidence_sequence: list[EvidenceType]) -> PaymentState:
    """Apply ordered, validated evidence to reconstruct one deterministic state."""
    state = None
    for evidence in evidence_sequence:
        state = next_state(state, evidence)
    if state is None:
        raise InvalidTransition("at least one initiation record is required")
    return state
