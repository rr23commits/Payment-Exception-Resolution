"""Deterministic controlled lifecycle generation for the four V1 scenarios."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from src.domain.complaints import COMPLAINTS_BY_SCENARIO, ComplaintSeverity, ComplaintType
from src.domain.scenarios import SCENARIO_BY_ID, SCENARIOS, ScenarioDefinition, ScenarioId
from src.domain.scenarios.config import (
    ScenarioParameters,
    actual_resolution_duration,
    hidden_future_evidence,
    observed_evidence,
    parameters_for,
    requires_intervention,
)
from src.domain.source_transaction import SourceTransaction
from src.domain.state_machine import EVIDENCE_REQUIREMENTS, EvidenceType, PaymentState
from src.provenance import GENERATED_COMPLAINT, GENERATED_LIFECYCLE


ASSIGNMENT_VERSION = "source-risk-friction-timing-v3"


@dataclass(frozen=True)
class PaymentEvent:
    event_id: str
    transaction_id: str
    scenario_instance_id: str
    event_time: datetime
    source: str
    event_type: EvidenceType
    payload: dict[str, str]
    generation_origin: str
    sequence_number: int


@dataclass(frozen=True)
class ComplaintEvent:
    event_id: str
    transaction_id: str
    scenario_instance_id: str
    event_time: datetime
    complaint_type: ComplaintType
    text: str
    severity: ComplaintSeverity
    generation_origin: str = GENERATED_COMPLAINT


@dataclass(frozen=True)
class ScenarioInstance:
    scenario_instance_id: str
    transaction_id: str
    scenario_id: ScenarioId
    events: tuple[PaymentEvent, ...]
    complaints: tuple[ComplaintEvent, ...]
    observation_cutoff: datetime
    hidden_future_event_ids: tuple[str, ...]
    expected_resolution_window: timedelta
    final_outcome: PaymentState
    requires_intervention: bool

    @property
    def observed_events(self) -> tuple[PaymentEvent, ...]:
        return tuple(event for event in self.events if event.event_time <= self.observation_cutoff)

    @property
    def hidden_future_events(self) -> tuple[PaymentEvent, ...]:
        return tuple(event for event in self.events if event.event_id in self.hidden_future_event_ids)

    @property
    def observed_complaints(self) -> tuple[ComplaintEvent, ...]:
        return tuple(complaint for complaint in self.complaints if complaint.event_time <= self.observation_cutoff)

    @property
    def hidden_future_complaints(self) -> tuple[ComplaintEvent, ...]:
        return tuple(complaint for complaint in self.complaints if complaint.event_time > self.observation_cutoff)

    @property
    def merchant_evidence(self) -> tuple[PaymentEvent, ...]:
        return tuple(event for event in self.events if event.source == "MERCHANT")

    @property
    def actual_resolution_duration(self) -> timedelta:
        return actual_resolution_duration(tuple(event.event_time for event in self.events))


def assign_scenario(source: SourceTransaction) -> ScenarioDefinition:
    """Choose an on-time/delayed path from source risk plus hidden stable friction."""
    timeout_path = _unit_interval(source.transaction_id, "branch") < 0.5
    delayed = _latent_friction(source) >= 0.5
    if timeout_path:
        scenario_id = ScenarioId.DELAYED_STUCK_REVERSAL if delayed else ScenarioId.TIMEOUT_TO_REVERSAL
    else:
        scenario_id = ScenarioId.REFUND_PENDING_STUCK if delayed else ScenarioId.PAYMENT_SUCCESS_ORDER_FAILURE
    return SCENARIO_BY_ID[scenario_id]


def _intervention_probability(source: SourceTransaction) -> float:
    """Simulate observable risk while retaining irreducible hidden variation for evaluation."""
    probability = 0.2
    if source.amount_inr >= 1000:
        probability += 0.25
    if source.timestamp.hour < 6 or source.timestamp.hour >= 18:
        probability += 0.15
    if _upi_provider(source.sender_upi_id) != _upi_provider(source.receiver_upi_id):
        probability += 0.1
    return min(probability, 0.8)


def _latent_friction(source: SourceTransaction) -> float:
    """Keep reproducible hidden variation while making observable risk informative, not decisive."""
    return 0.65 * _intervention_probability(source) + 0.35 * _unit_interval(source.transaction_id, "friction")


def _unit_interval(transaction_id: str, purpose: str) -> float:
    digest = hashlib.sha256(f"{ASSIGNMENT_VERSION}:{purpose}:{transaction_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8]) / 2**64


def _upi_provider(upi_id: str) -> str:
    return upi_id.rsplit("@", 1)[-1]


def _event_timestamps(
    source: SourceTransaction, scenario: ScenarioDefinition, parameters: ScenarioParameters
) -> tuple[datetime, ...]:
    """Vary observed pending entry and hidden confirmation timing without changing lifecycle evidence."""
    parameters.validate(len(scenario.evidence))
    offsets = list(parameters.event_offsets)
    pending_index = next(
        index
        for index, evidence in enumerate(scenario.evidence)
        if evidence in {EvidenceType.REVERSAL_REQUESTED, EvidenceType.REFUND_REQUESTED}
    )
    # Entry timing is observed at the target cutoff; its overlap between labels prevents a threshold shortcut.
    entry_minutes = int(offsets[pending_index - 1].total_seconds() // 60) + 1 + round(_latent_friction(source) * 4)
    offsets[pending_index] = timedelta(minutes=entry_minutes)

    window_minutes = int(parameters.expected_resolution_window.total_seconds() // 60)
    residual = _unit_interval(source.transaction_id, "confirmation-residual")
    if scenario.scenario_id in {ScenarioId.DELAYED_STUCK_REVERSAL, ScenarioId.REFUND_PENDING_STUCK}:
        confirmation_minutes = window_minutes + 1 + int(residual * 8)
    else:
        earliest_confirmation = entry_minutes + 1
        confirmation_minutes = earliest_confirmation + int(residual * (window_minutes - earliest_confirmation + 1))
    offsets[-1] = timedelta(minutes=confirmation_minutes)
    return tuple(source.timestamp + offset for offset in offsets)


def generate_scenario_instance(
    source: SourceTransaction,
    scenario: ScenarioDefinition | None = None,
    parameters: ScenarioParameters | None = None,
) -> ScenarioInstance:
    """Materialize the complete controlled trajectory while retaining its hidden suffix."""
    scenario = scenario or assign_scenario(source)
    parameters = parameters or parameters_for(scenario)
    event_times = _event_timestamps(source, scenario, parameters)
    instance_id = str(uuid5(NAMESPACE_URL, f"{ASSIGNMENT_VERSION}:{source.transaction_id}:{scenario.scenario_id.value}"))
    events = tuple(
        PaymentEvent(
            event_id=str(uuid5(NAMESPACE_URL, f"{instance_id}:{sequence_number}")),
            transaction_id=source.transaction_id,
            scenario_instance_id=instance_id,
            event_time=event_time,
            source=EVIDENCE_REQUIREMENTS[evidence][0],
            event_type=evidence,
            payload={"evidence_fact": EVIDENCE_REQUIREMENTS[evidence][1]},
            generation_origin=GENERATED_LIFECYCLE,
            sequence_number=sequence_number,
        )
        for sequence_number, (evidence, event_time) in enumerate(zip(scenario.evidence, event_times), start=1)
    )
    visible_count = len(observed_evidence(scenario, parameters))
    hidden = hidden_future_evidence(scenario, parameters)
    complaint = COMPLAINTS_BY_SCENARIO[scenario.scenario_id]
    return ScenarioInstance(
        scenario_instance_id=instance_id,
        transaction_id=source.transaction_id,
        scenario_id=scenario.scenario_id,
        events=events,
        complaints=(
            ComplaintEvent(
                event_id=str(uuid5(NAMESPACE_URL, f"{instance_id}:complaint")),
                transaction_id=source.transaction_id,
                scenario_instance_id=instance_id,
                event_time=source.timestamp + complaint.offset,
                complaint_type=complaint.complaint_type,
                text=complaint.text,
                severity=complaint.severity,
            ),
        ),
        observation_cutoff=events[visible_count - 1].event_time,
        hidden_future_event_ids=tuple(event.event_id for event in events[-len(hidden) :]),
        expected_resolution_window=parameters.expected_resolution_window,
        final_outcome=scenario.final_outcome,
        requires_intervention=requires_intervention(scenario, event_times, parameters),
    )


def write_ground_truth(instance: ScenarioInstance, directory: Path) -> Path:
    """Persist generated ground truth separately from the immutable source dataset."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{instance.scenario_instance_id}.json"
    path.write_text(json.dumps(_as_dict(instance), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _as_dict(instance: ScenarioInstance) -> dict[str, object]:
    return {
        "scenario_instance_id": instance.scenario_instance_id,
        "transaction_id": instance.transaction_id,
        "scenario_id": instance.scenario_id.value,
        "events": [
            {
                "event_id": event.event_id,
                "transaction_id": event.transaction_id,
                "scenario_instance_id": event.scenario_instance_id,
                "event_time": event.event_time.isoformat(sep=" "),
                "source": event.source,
                "event_type": event.event_type.value,
                "payload": event.payload,
                "generation_origin": event.generation_origin,
                "sequence_number": event.sequence_number,
            }
            for event in instance.events
        ],
        "complaints": [
            {
                "event_id": complaint.event_id,
                "transaction_id": complaint.transaction_id,
                "scenario_instance_id": complaint.scenario_instance_id,
                "event_time": complaint.event_time.isoformat(sep=" "),
                "complaint_type": complaint.complaint_type.value,
                "text": complaint.text,
                "severity": complaint.severity.value,
                "generation_origin": complaint.generation_origin,
            }
            for complaint in instance.complaints
        ],
        "observation_cutoff": instance.observation_cutoff.isoformat(sep=" "),
        "hidden_future_event_ids": instance.hidden_future_event_ids,
        "expected_resolution_window_seconds": instance.expected_resolution_window.total_seconds(),
        "final_outcome": instance.final_outcome.value,
        "requires_intervention": instance.requires_intervention,
    }
