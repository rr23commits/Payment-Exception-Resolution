"""Simulated timing parameters for V1 scenario experiments, not payment-service SLAs."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.scenarios import ScenarioDefinition, ScenarioId
from src.domain.state_machine import EvidenceType, next_state


@dataclass(frozen=True)
class ScenarioParameters:
    observation_cutoff_index: int
    event_offsets: tuple[timedelta, ...]
    expected_resolution_window: timedelta

    def validate(self, event_count: int) -> None:
        if not 0 <= self.observation_cutoff_index < event_count:
            raise ValueError("observation cutoff must identify a scenario event")
        if len(self.event_offsets) != event_count or self.event_offsets[0] != timedelta():
            raise ValueError("event offsets must start at zero and match the scenario event count")
        if any(later <= earlier for earlier, later in zip(self.event_offsets, self.event_offsets[1:])):
            raise ValueError("event offsets must be strictly increasing")
        if self.expected_resolution_window <= timedelta():
            raise ValueError("experimental resolution window must be positive")

    def event_timestamps(self, start_time: datetime, event_count: int) -> tuple[datetime, ...]:
        self.validate(event_count)
        return tuple(start_time + offset for offset in self.event_offsets)


def _minutes(*values: int) -> tuple[timedelta, ...]:
    return tuple(timedelta(minutes=value) for value in values)


# Controlled experimental inputs. Their offsets are the single source for generated timing.
SCENARIO_PARAMETERS = {
    ScenarioId.TIMEOUT_TO_REVERSAL: ScenarioParameters(2, _minutes(0, 1, 2, 4, 6), timedelta(minutes=10)),
    ScenarioId.DELAYED_STUCK_REVERSAL: ScenarioParameters(3, _minutes(0, 1, 2, 4, 18), timedelta(minutes=10)),
    ScenarioId.PAYMENT_SUCCESS_ORDER_FAILURE: ScenarioParameters(3, _minutes(0, 1, 2, 3, 5, 8), timedelta(minutes=12)),
    ScenarioId.REFUND_PENDING_STUCK: ScenarioParameters(4, _minutes(0, 1, 2, 3, 5, 20), timedelta(minutes=12)),
}


def parameters_for(scenario: ScenarioDefinition) -> ScenarioParameters:
    parameters = SCENARIO_PARAMETERS[scenario.scenario_id]
    parameters.validate(len(scenario.evidence))
    return parameters


def observed_evidence(
    scenario: ScenarioDefinition, parameters: ScenarioParameters | None = None
) -> tuple[EvidenceType, ...]:
    parameters = parameters or parameters_for(scenario)
    return scenario.evidence[: parameters.observation_cutoff_index + 1]


def hidden_future_evidence(
    scenario: ScenarioDefinition, parameters: ScenarioParameters | None = None
) -> tuple[EvidenceType, ...]:
    parameters = parameters or parameters_for(scenario)
    return scenario.evidence[parameters.observation_cutoff_index + 1 :]


def actual_resolution_duration(event_timestamps: tuple[datetime, ...]) -> timedelta:
    if len(event_timestamps) < 2 or any(later <= earlier for earlier, later in zip(event_timestamps, event_timestamps[1:])):
        raise ValueError("event timestamps must contain at least two strictly ordered values")
    return event_timestamps[-1] - event_timestamps[0]


def requires_intervention(
    scenario: ScenarioDefinition,
    event_timestamps: tuple[datetime, ...],
    parameters: ScenarioParameters | None = None,
) -> bool:
    """Derive controlled ground truth from generated timestamps and domain state semantics."""
    parameters = parameters or parameters_for(scenario)
    parameters.validate(len(scenario.evidence))
    if len(event_timestamps) != len(scenario.evidence):
        raise ValueError("event timestamps must match the scenario event count")
    state = None
    for evidence in scenario.evidence:
        state = next_state(state, evidence)
        if state == scenario.human_handling_state:
            return True
    return actual_resolution_duration(event_timestamps) > parameters.expected_resolution_window
