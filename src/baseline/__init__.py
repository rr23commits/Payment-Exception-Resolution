"""Controlled targets and a time-safe deterministic rules baseline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from src.domain.state_machine import EvidenceType, PaymentState
from src.features import FeatureRow
from src.generation import ScenarioInstance


TARGET_DEFINITION_VERSION = "pending-window-v2"
OBSERVATION_PLAN_VERSION = "first-pending-state-v1"


@dataclass(frozen=True)
class ControlledTarget:
    """Labels derived from controlled future ground truth, never model inputs."""

    requires_intervention: bool


@dataclass(frozen=True)
class BaselinePrediction:
    requires_intervention: bool
    intervention_probability: float


@dataclass(frozen=True)
class StateRateBaseline:
    """A conventional baseline that knows only the observed pending state rate."""

    intervention_rate_by_state: dict[str, float]

    def predict(self, features: FeatureRow) -> BaselinePrediction:
        state = features.model_inputs["reconstructed_state"]
        probability = self.intervention_rate_by_state.get(state)
        if probability is None:
            raise ValueError(f"baseline has no pending-state rate for {state!r}")
        return BaselinePrediction(probability >= 0.5, probability)


def pending_observation_cutoff(instance: ScenarioInstance) -> datetime:
    """Return the lifecycle instant that first establishes a reversal/refund pending state."""
    for event in instance.events:
        if event.event_type in {EvidenceType.REVERSAL_REQUESTED, EvidenceType.REFUND_REQUESTED}:
            return event.event_time
    raise ValueError("V1 intervention target requires a pending lifecycle event")


def derive_target(instance: ScenarioInstance, observation_cutoff: datetime) -> ControlledTarget:
    """Read controlled future timing only as the window-violation label."""
    if observation_cutoff != pending_observation_cutoff(instance):
        raise ValueError("intervention target must use the first pending-state cutoff")
    return ControlledTarget(instance.requires_intervention)


def fit(features: list[FeatureRow], targets: list[ControlledTarget]) -> StateRateBaseline:
    """Estimate intervention prevalence by state using training labels only."""
    if len(features) != len(targets) or not features:
        raise ValueError("baseline fitting requires equally sized non-empty feature and target lists")
    labels_by_state: dict[str, list[bool]] = defaultdict(list)
    for feature, target in zip(features, targets):
        state = feature.model_inputs["reconstructed_state"]
        if state not in {PaymentState.REVERSAL_PENDING.value, PaymentState.REFUND_PENDING.value}:
            raise ValueError("intervention baseline requires a pending reconstructed state")
        labels_by_state[state].append(target.requires_intervention)
    return StateRateBaseline({state: sum(labels) / len(labels) for state, labels in labels_by_state.items()})
