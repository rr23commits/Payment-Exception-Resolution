"""Deterministic V1 exception detection from reconstructed state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from uuid import NAMESPACE_URL, uuid5

from src.domain.state_machine import EvidenceType, PaymentState
from src.engine.reconstruction import StateSnapshot
from src.provenance import DERIVED_STATE


class ExceptionKind(str, Enum):
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    TIMEOUT_TO_REVERSAL = "TIMEOUT_TO_REVERSAL"
    STATE_MERCHANT_MISMATCH = "STATE_MERCHANT_MISMATCH"
    DELAYED_STUCK_REVERSAL = "DELAYED_STUCK_REVERSAL"
    REFUND_PENDING_STUCK = "REFUND_PENDING_STUCK"


@dataclass(frozen=True)
class ExceptionIncident:
    transaction_id: str
    kind: ExceptionKind
    state: PaymentState | None
    evidence_ids: tuple[str, ...]
    reasoning: str
    provenance: str = DERIVED_STATE

    @property
    def incident_id(self) -> str:
        """Stable identifier for linking downstream records without changing incident truth."""
        return str(uuid5(NAMESPACE_URL, f"exception:{self.transaction_id}:{self.kind.value}:{','.join(self.evidence_ids)}"))


def detect_exceptions(
    snapshot: StateSnapshot, expected_resolution_window: timedelta | None = None
) -> tuple[ExceptionIncident, ...]:
    """Report V1 findings without selecting a policy action or using future evidence."""
    incidents = [
        ExceptionIncident(snapshot.transaction_id, ExceptionKind.CONTRADICTORY_EVIDENCE, snapshot.state, (conflict.event_id,), conflict.reason)
        for conflict in snapshot.conflicts
    ]
    evidence_ids = tuple(step.event_id for step in snapshot.evidence_path)
    evidence_types = {step.event_type for step in snapshot.evidence_path}
    if snapshot.state == PaymentState.GATEWAY_TIMEOUT:
        incidents.append(ExceptionIncident(snapshot.transaction_id, ExceptionKind.TIMEOUT_TO_REVERSAL, snapshot.state, evidence_ids, "bank debit is followed by a gateway timeout"))
    if snapshot.state in {PaymentState.ORDER_FAILED, PaymentState.REFUND_PENDING} and EvidenceType.PAYMENT_SUCCESS_CONFIRMED in evidence_types:
        incidents.append(ExceptionIncident(snapshot.transaction_id, ExceptionKind.STATE_MERCHANT_MISMATCH, snapshot.state, evidence_ids, "financial success conflicts with merchant order failure"))
    if expected_resolution_window is not None and snapshot.evidence_path:
        elapsed = snapshot.observation_cutoff - snapshot.evidence_path[0].event_time
        if elapsed > expected_resolution_window and snapshot.state == PaymentState.REVERSAL_PENDING:
            incidents.append(ExceptionIncident(snapshot.transaction_id, ExceptionKind.DELAYED_STUCK_REVERSAL, snapshot.state, evidence_ids, "reversal remains pending beyond the simulated resolution window"))
        if elapsed > expected_resolution_window and snapshot.state == PaymentState.REFUND_PENDING:
            incidents.append(ExceptionIncident(snapshot.transaction_id, ExceptionKind.REFUND_PENDING_STUCK, snapshot.state, evidence_ids, "refund remains pending beyond the simulated resolution window"))
    return tuple(incidents)
