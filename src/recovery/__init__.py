"""One bounded, deterministic recovery workflow beside immutable engine records."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from src.engine.exceptions import ExceptionKind
from src.engine.exceptions import detect_exceptions
from src.engine.reconstruction import reconstruct_state
from src.policy import MoneyMovingOperation, PolicyDecision, recommend
from src.provenance import SIMULATED_RECOVERY

if TYPE_CHECKING:
    from src.evaluation import EngineRecord


class RecoveryStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SIMULATED_SUCCEEDED = "SIMULATED_SUCCEEDED"


@dataclass(frozen=True)
class RecoveryOpportunity:
    opportunity_id: str
    transaction_id: str
    incident_ids: tuple[str, ...]
    amount: Decimal
    recommended_action: MoneyMovingOperation
    status: RecoveryStatus
    origin: str = SIMULATED_RECOVERY


@dataclass(frozen=True)
class RecoveryMetrics:
    revenue_at_risk: Decimal
    recoverable_revenue: Decimal
    simulated_recovered_revenue: Decimal
    simulated_recovery_rate: Decimal


@dataclass(frozen=True)
class RecoveryReadModel:
    opportunity: RecoveryOpportunity
    state: object
    timeout_reasoning: tuple[str, ...]
    model_probability: float | None
    policy_decision: PolicyDecision
    recommendation_reason: str
    metrics: RecoveryMetrics
    simulated: bool = True


def create_opportunity(record: EngineRecord) -> RecoveryOpportunity | None:
    """Create the only V1 opportunity: a cutoff-visible timeout incident."""
    _, timeout_incidents = _timeout_evidence(record)
    if not timeout_incidents:
        return None
    return RecoveryOpportunity(
        str(uuid5(NAMESPACE_URL, f"recovery-opportunity:{record.source.transaction_id}")),
        record.source.transaction_id,
        tuple(incident.incident_id for incident in timeout_incidents),
        record.source.amount_inr,
        MoneyMovingOperation.RETRY,
        RecoveryStatus.PENDING_APPROVAL,
    )


def retry_policy(record: EngineRecord) -> PolicyDecision:
    snapshot, incidents = _timeout_evidence(record)
    return recommend(snapshot, incidents, record.recovery_prediction, MoneyMovingOperation.RETRY)


def apply_decision(opportunity: RecoveryOpportunity, approve: bool) -> RecoveryOpportunity:
    if opportunity.status != RecoveryStatus.PENDING_APPROVAL:
        raise ValueError("recovery decision is already recorded")
    return replace(opportunity, status=RecoveryStatus.APPROVED if approve else RecoveryStatus.REJECTED)


def simulate_retry(opportunity: RecoveryOpportunity) -> RecoveryOpportunity:
    """The V1 demo rule: one approved timeout retry succeeds deterministically."""
    if opportunity.status != RecoveryStatus.APPROVED:
        raise ValueError("simulated retry requires one approved opportunity")
    return replace(opportunity, status=RecoveryStatus.SIMULATED_SUCCEEDED)


def metrics(opportunity: RecoveryOpportunity) -> RecoveryMetrics:
    recoverable = opportunity.amount
    recovered = opportunity.amount if opportunity.status == RecoveryStatus.SIMULATED_SUCCEEDED else Decimal("0")
    at_risk = opportunity.amount if opportunity.status == RecoveryStatus.PENDING_APPROVAL else Decimal("0")
    return RecoveryMetrics(at_risk, recoverable, recovered, recovered / recoverable if recoverable else Decimal("0"))


def read_model(record: EngineRecord, opportunity: RecoveryOpportunity, policy: PolicyDecision) -> RecoveryReadModel:
    snapshot, incidents = _timeout_evidence(record)
    reasons = tuple(incident.reasoning for incident in incidents if incident.kind == ExceptionKind.TIMEOUT_TO_REVERSAL)
    return RecoveryReadModel(opportunity, snapshot.state, reasons, record.recovery_prediction.probability, policy, policy.reasoning, metrics(opportunity))


def _timeout_evidence(record: EngineRecord):
    """Recovery observes the historical engine trajectory only at its original timeout cutoff."""
    snapshot = reconstruct_state(record.instance.events, record.instance.observation_cutoff)
    incidents = detect_exceptions(snapshot, record.instance.expected_resolution_window)
    return snapshot, tuple(incident for incident in incidents if incident.kind == ExceptionKind.TIMEOUT_TO_REVERSAL)
