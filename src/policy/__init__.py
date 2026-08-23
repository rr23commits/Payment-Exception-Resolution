"""Deterministic, non-money-moving recommendations from established evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.state_machine import PaymentState
from src.engine.exceptions import ExceptionIncident, ExceptionKind
from src.engine.reconstruction import StateSnapshot
from src.provenance import MODEL_OUTPUT, POLICY_DECISION


class PolicyAction(str, Enum):
    MONITOR = "MONITOR"
    RECHECK_RECONCILE = "RECHECK / RECONCILE"
    NOTIFY = "NOTIFY"
    ESCALATE = "ESCALATE"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE HUMAN APPROVAL"


class MoneyMovingOperation(str, Enum):
    """Operations policy may gate but never execute."""

    REFUND = "REFUND"
    CAPTURE = "CAPTURE"
    TRANSFER = "TRANSFER"
    RELEASE = "RELEASE"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class PredictionSignal:
    """Optional model or baseline output; it cannot alter reconstructed state."""

    requires_intervention: bool
    probability: float | None = None
    provenance: str = MODEL_OUTPUT

    def __post_init__(self) -> None:
        if self.probability is not None and not 0 <= self.probability <= 1:
            raise ValueError("prediction probability must be between 0 and 1")


@dataclass(frozen=True)
class PolicyDecision:
    transaction_id: str
    state: PaymentState | None
    action: PolicyAction
    reasoning: str
    prediction_probability: float | None
    requested_operation: MoneyMovingOperation | None = None
    provenance: str = POLICY_DECISION


_TERMINAL_STATES = frozenset({PaymentState.SETTLED, PaymentState.REVERSED, PaymentState.REFUNDED})
_STUCK_KINDS = frozenset({ExceptionKind.DELAYED_STUCK_REVERSAL, ExceptionKind.REFUND_PENDING_STUCK})
_NOTIFY_KINDS = frozenset({ExceptionKind.TIMEOUT_TO_REVERSAL, ExceptionKind.STATE_MERCHANT_MISMATCH})


def recommend(
    snapshot: StateSnapshot,
    incidents: tuple[ExceptionIncident, ...] = (),
    prediction: PredictionSignal | None = None,
    requested_operation: MoneyMovingOperation | None = None,
) -> PolicyDecision:
    """Choose only a catalogue action from cutoff-safe state and evidence."""
    probability = prediction.probability if prediction else None
    kinds = {incident.kind for incident in incidents}

    # A requested financial operation is always handed to a person; policy has no executor.
    if requested_operation is not None:
        return _decision(snapshot, PolicyAction.REQUIRE_HUMAN_APPROVAL, f"{requested_operation.value} requires human approval", probability, requested_operation)
    if ExceptionKind.CONTRADICTORY_EVIDENCE in kinds:
        return _decision(snapshot, PolicyAction.RECHECK_RECONCILE, "contradictory evidence requires reconciliation", probability)
    # A completed authoritative state is not reopened by a model prediction alone.
    if snapshot.state in _TERMINAL_STATES:
        return _decision(snapshot, PolicyAction.MONITOR, "reconstructed state is terminal", probability)
    if kinds & _STUCK_KINDS:
        return _decision(snapshot, PolicyAction.ESCALATE, "pending resolution exceeded its expected window", probability)
    if kinds & _NOTIFY_KINDS:
        return _decision(snapshot, PolicyAction.NOTIFY, "deterministic exception requires notification", probability)
    if prediction and prediction.requires_intervention:
        return _decision(snapshot, PolicyAction.RECHECK_RECONCILE, "prediction requests a safe evidence recheck", probability)
    return _decision(snapshot, PolicyAction.MONITOR, "no deterministic exception or intervention signal", probability)


def _decision(
    snapshot: StateSnapshot,
    action: PolicyAction,
    reasoning: str,
    probability: float | None,
    requested_operation: MoneyMovingOperation | None = None,
) -> PolicyDecision:
    return PolicyDecision(snapshot.transaction_id, snapshot.state, action, reasoning, probability, requested_operation)
