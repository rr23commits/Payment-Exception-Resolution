"""Deterministic controlled lifecycle generation for the four V1 scenarios."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from src.domain.scenarios import SCENARIOS, ScenarioDefinition, ScenarioId
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
from src.provenance import GENERATED_LIFECYCLE


ASSIGNMENT_VERSION = "sha256-transaction-id-mod-4-v1"


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
class ScenarioInstance:
    scenario_instance_id: str
    transaction_id: str
    scenario_id: ScenarioId
    events: tuple[PaymentEvent, ...]
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
    def merchant_evidence(self) -> tuple[PaymentEvent, ...]:
        return tuple(event for event in self.events if event.source == "MERCHANT")

    @property
    def actual_resolution_duration(self) -> timedelta:
        return actual_resolution_duration(tuple(event.event_time for event in self.events))


def assign_scenario(transaction_id: str) -> ScenarioDefinition:
    """Assign independently of source status and without a random seed."""
    position = int.from_bytes(hashlib.sha256(transaction_id.encode("utf-8")).digest()[:8]) % len(SCENARIOS)
    return SCENARIOS[position]


def generate_scenario_instance(
    source: SourceTransaction,
    scenario: ScenarioDefinition | None = None,
    parameters: ScenarioParameters | None = None,
) -> ScenarioInstance:
    """Materialize the complete controlled trajectory while retaining its hidden suffix."""
    scenario = scenario or assign_scenario(source.transaction_id)
    parameters = parameters or parameters_for(scenario)
    event_times = parameters.event_timestamps(source.timestamp, len(scenario.evidence))
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
    return ScenarioInstance(
        scenario_instance_id=instance_id,
        transaction_id=source.transaction_id,
        scenario_id=scenario.scenario_id,
        events=events,
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
        "observation_cutoff": instance.observation_cutoff.isoformat(sep=" "),
        "hidden_future_event_ids": instance.hidden_future_event_ids,
        "expected_resolution_window_seconds": instance.expected_resolution_window.total_seconds(),
        "final_outcome": instance.final_outcome.value,
        "requires_intervention": instance.requires_intervention,
    }
