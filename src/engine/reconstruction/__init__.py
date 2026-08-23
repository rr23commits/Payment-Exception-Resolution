"""Time-safe deterministic state reconstruction from lifecycle evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.state_machine import EVIDENCE_REQUIREMENTS, EvidenceType, InvalidTransition, PaymentState, next_state
from src.generation import PaymentEvent
from src.provenance import DERIVED_STATE


@dataclass(frozen=True)
class EvidenceConflict:
    """Observed evidence that cannot support a state transition."""

    event_id: str
    reason: str


@dataclass(frozen=True)
class StateTransition:
    event_id: str
    event_type: EvidenceType
    event_time: datetime
    resulting_state: PaymentState


@dataclass(frozen=True)
class StateSnapshot:
    transaction_id: str
    observation_cutoff: datetime
    state: PaymentState | None
    evidence_path: tuple[StateTransition, ...]
    conflicts: tuple[EvidenceConflict, ...]
    provenance: str = DERIVED_STATE


def reconstruct_state(events: tuple[PaymentEvent, ...], observation_cutoff: datetime) -> StateSnapshot:
    """Rebuild the latest valid state using only events available by the cutoff."""
    observed = sorted(
        (event for event in events if event.event_time <= observation_cutoff),
        key=lambda event: (event.event_time, event.sequence_number, event.event_id),
    )
    if not observed:
        raise ValueError("at least one observed event is required")
    transaction_id = observed[0].transaction_id
    if any(event.transaction_id != transaction_id for event in observed):
        raise ValueError("observed events must belong to one transaction")

    state = None
    path: list[StateTransition] = []
    conflicts: list[EvidenceConflict] = []
    for event in observed:
        expected_source, expected_fact = EVIDENCE_REQUIREMENTS[event.event_type]
        if event.source != expected_source or event.payload.get("evidence_fact") != expected_fact:
            conflicts.append(EvidenceConflict(event.event_id, "event authority does not match its evidence type"))
            continue
        try:
            state = next_state(state, event.event_type)
        except InvalidTransition as error:
            conflicts.append(EvidenceConflict(event.event_id, str(error)))
            continue
        path.append(StateTransition(event.event_id, event.event_type, event.event_time, state))
    return StateSnapshot(transaction_id, observation_cutoff, state, tuple(path), tuple(conflicts))
