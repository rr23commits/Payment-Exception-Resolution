"""Deterministic V1 scenario contracts; no generation or model decisions."""

from dataclasses import dataclass
from enum import Enum

from src.domain.state_machine import EVIDENCE_REQUIREMENTS, EvidenceType, PaymentState, apply_evidence


class ScenarioId(str, Enum):
    TIMEOUT_TO_REVERSAL = "timeout_to_reversal"
    DELAYED_STUCK_REVERSAL = "delayed_stuck_reversal"
    PAYMENT_SUCCESS_ORDER_FAILURE = "payment_success_order_failure"
    REFUND_PENDING_STUCK = "refund_pending_stuck"


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: ScenarioId
    evidence: tuple[EvidenceType, ...]
    human_handling_state: PaymentState | None = None

    @property
    def final_outcome(self) -> PaymentState:
        return apply_evidence(list(self.evidence))

    @property
    def event_sources(self) -> tuple[tuple[EvidenceType, str], ...]:
        return tuple((evidence, EVIDENCE_REQUIREMENTS[evidence][0]) for evidence in self.evidence)

    @property
    def merchant_evidence(self) -> tuple[EvidenceType, ...]:
        return tuple(evidence for evidence, source in self.event_sources if source == "MERCHANT")

SCENARIOS = (
    ScenarioDefinition(
        ScenarioId.TIMEOUT_TO_REVERSAL,
        (
            EvidenceType.INITIATION_RECORDED,
            EvidenceType.BANK_DEBIT_CONFIRMED,
            EvidenceType.GATEWAY_TIMEOUT_RECORDED,
            EvidenceType.REVERSAL_REQUESTED,
            EvidenceType.REVERSAL_CONFIRMED,
        ),
    ),
    ScenarioDefinition(
        ScenarioId.DELAYED_STUCK_REVERSAL,
        (
            EvidenceType.INITIATION_RECORDED,
            EvidenceType.BANK_DEBIT_CONFIRMED,
            EvidenceType.GATEWAY_TIMEOUT_RECORDED,
            EvidenceType.REVERSAL_REQUESTED,
            EvidenceType.REVERSAL_CONFIRMED,
        ),
    ),
    ScenarioDefinition(
        ScenarioId.PAYMENT_SUCCESS_ORDER_FAILURE,
        (
            EvidenceType.INITIATION_RECORDED,
            EvidenceType.BANK_DEBIT_CONFIRMED,
            EvidenceType.PAYMENT_SUCCESS_CONFIRMED,
            EvidenceType.ORDER_FAILURE_CONFIRMED,
            EvidenceType.REFUND_REQUESTED,
            EvidenceType.REFUND_CONFIRMED,
        ),
    ),
    ScenarioDefinition(
        ScenarioId.REFUND_PENDING_STUCK,
        (
            EvidenceType.INITIATION_RECORDED,
            EvidenceType.BANK_DEBIT_CONFIRMED,
            EvidenceType.PAYMENT_SUCCESS_CONFIRMED,
            EvidenceType.ORDER_FAILURE_CONFIRMED,
            EvidenceType.REFUND_REQUESTED,
            EvidenceType.REFUND_CONFIRMED,
        ),
    ),
)

SCENARIO_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}
