"""Controlled resolution tracking; this module records decisions but executes nothing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.audit import AuditTrail
from src.domain.state_machine import PaymentState
from src.engine.exceptions import ExceptionIncident
from src.engine.reconstruction import StateSnapshot, reconstruct_state
from src.features import FeatureRow
from src.generation import ScenarioInstance
from src.policy import PolicyAction, PolicyDecision, PredictionSignal
from src.provenance import DERIVED_STATE, HUMAN_DECISION, MODEL_OUTPUT, RESOLUTION_RESULT, SIMULATED_RECOVERY


_UNSET = object()


class HumanDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ModeledHumanDecision:
    decision: HumanDecision
    reasoning: str
    provenance: str = HUMAN_DECISION


@dataclass(frozen=True)
class VersionedPrediction:
    """Keep the producing baseline/model version separate from its safe signal."""

    model_version: str
    signal: PredictionSignal
    provenance: str = MODEL_OUTPUT

    def __post_init__(self) -> None:
        if not self.model_version:
            raise ValueError("prediction model version is required")


@dataclass(frozen=True)
class ResolutionVerification:
    final_outcome: PaymentState
    requires_intervention: bool
    revealed_event_ids: tuple[str, ...]
    provenance: str = RESOLUTION_RESULT


@dataclass(frozen=True)
class ResolutionCase:
    """An append-only evidence-to-resolution record for one controlled incident."""

    transaction_id: str
    observation_cutoff: datetime
    feature_snapshot: FeatureRow
    policy_decision: PolicyDecision
    audit_trail: AuditTrail
    human_decision: ModeledHumanDecision | None = None
    verification: ResolutionVerification | None = None

    def record_human_decision(self, decision: ModeledHumanDecision, approval_policy: PolicyDecision | None = None) -> ResolutionCase:
        """Model an approval/rejection record only; no payment operation is available here."""
        policy = approval_policy or self.policy_decision
        if policy.action != PolicyAction.REQUIRE_HUMAN_APPROVAL:
            raise ValueError("human decision is only required by the current policy action")
        if self.human_decision is not None:
            raise ValueError("human decision is already recorded")
        return _replace_case(self, self.audit_trail.append("HUMAN_DECISION", decision, decision.provenance), decision)

    def record_recovery_opportunity(self, opportunity: object) -> ResolutionCase:
        """Append a separate simulated-recovery record without changing historical verification."""
        if any(record.record_type == "RECOVERY_OPPORTUNITY" for record in self.audit_trail.records):
            raise ValueError("recovery opportunity is already recorded")
        return _replace_case(self, self.audit_trail.append("RECOVERY_OPPORTUNITY", opportunity, SIMULATED_RECOVERY))

    def record_simulated_recovery(self, outcome: object) -> ResolutionCase:
        """Append one controlled retry result; this is never lifecycle evidence."""
        if any(record.record_type == "SIMULATED_RECOVERY_OUTCOME" for record in self.audit_trail.records):
            raise ValueError("simulated recovery is already recorded")
        return _replace_case(self, self.audit_trail.append("SIMULATED_RECOVERY_OUTCOME", outcome, SIMULATED_RECOVERY))

    def reveal_and_verify(self, instance: ScenarioInstance) -> ResolutionCase:
        """Reveal only post-cutoff evidence, then verify the complete controlled outcome."""
        if self.verification is not None:
            raise ValueError("resolution is already verified")
        if instance.transaction_id != self.transaction_id:
            raise ValueError("resolution instance must match the recorded transaction")
        if self.policy_decision.action == PolicyAction.REQUIRE_HUMAN_APPROVAL and self.human_decision is None:
            raise ValueError("human approval decision is required before verification")

        revealed = tuple(event for event in instance.events if event.event_time > self.observation_cutoff)
        full_snapshot = reconstruct_state(instance.events, instance.events[-1].event_time)
        if full_snapshot.state != instance.final_outcome:
            raise ValueError("revealed evidence does not verify the controlled final outcome")
        verification = ResolutionVerification(instance.final_outcome, instance.requires_intervention, tuple(event.event_id for event in revealed))
        trail = self.audit_trail
        for event in revealed:
            trail = trail.append("REVEALED_FUTURE_EVENT", event, event.generation_origin)
        for complaint in instance.complaints:
            if complaint.event_time > self.observation_cutoff:
                trail = trail.append("REVEALED_FUTURE_COMPLAINT", complaint, complaint.generation_origin)
        trail = trail.append("RESOLUTION_VERIFICATION", verification, verification.provenance)
        return _replace_case(self, trail, verification=verification)


def open_resolution_case(
    instance: ScenarioInstance,
    snapshot: StateSnapshot,
    incidents: tuple[ExceptionIncident, ...],
    features: FeatureRow,
    predictions: tuple[VersionedPrediction, ...],
    policy_decision: PolicyDecision,
) -> ResolutionCase:
    """Store only cutoff-visible inputs; future evidence is added exclusively during verification."""
    cutoff = features.observation_cutoff
    if snapshot.transaction_id != instance.transaction_id or snapshot.observation_cutoff != cutoff:
        raise ValueError("snapshot must match the feature transaction and cutoff")
    if policy_decision.transaction_id != instance.transaction_id or policy_decision.state != snapshot.state:
        raise ValueError("policy decision must preserve reconstructed state")
    if any(incident.transaction_id != instance.transaction_id for incident in incidents):
        raise ValueError("incidents must match the resolution transaction")

    trail = AuditTrail(instance.transaction_id)
    for event in instance.events:
        if event.event_time <= cutoff:
            trail = trail.append("OBSERVED_EVIDENCE", event, event.generation_origin)
    for complaint in instance.complaints:
        if complaint.event_time <= cutoff:
            trail = trail.append("OBSERVED_COMPLAINT", complaint, complaint.generation_origin)
    trail = trail.append("RECONSTRUCTED_STATE", snapshot, snapshot.provenance)
    for incident in incidents:
        trail = trail.append("DETECTED_EXCEPTION", incident, incident.provenance)
    trail = trail.append("FEATURE_SNAPSHOT", features, DERIVED_STATE)
    for prediction in predictions:
        trail = trail.append("PREDICTION", prediction, prediction.provenance)
    trail = trail.append("POLICY_DECISION", policy_decision, policy_decision.provenance)
    return ResolutionCase(instance.transaction_id, cutoff, features, policy_decision, trail)


def _replace_case(
    case: ResolutionCase,
    trail: AuditTrail,
    human_decision: ModeledHumanDecision | None = None,
    verification: ResolutionVerification | None | object = _UNSET,
) -> ResolutionCase:
    return ResolutionCase(
        case.transaction_id,
        case.observation_cutoff,
        case.feature_snapshot,
        case.policy_decision,
        trail,
        case.human_decision if human_decision is None else human_decision,
        case.verification if verification is _UNSET else verification,
    )
