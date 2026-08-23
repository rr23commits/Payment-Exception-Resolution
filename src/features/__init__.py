"""Versioned, leakage-safe feature construction for controlled lifecycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.complaints import ComplaintSeverity
from src.domain.source_transaction import SourceTransaction
from src.domain.state_machine import EvidenceType
from src.engine.reconstruction import reconstruct_state
from src.generation import ScenarioInstance


FEATURE_DEFINITION_VERSION = "v1"


@dataclass(frozen=True)
class FeatureRow:
    """Feature values plus non-model metadata needed to reproduce the row."""

    transaction_id: str
    observation_cutoff: datetime
    feature_version: str
    values: dict[str, str | int | float | bool]

    @property
    def model_inputs(self) -> dict[str, str | int | float | bool]:
        """Return only values eligible for baseline or ML input."""
        return self.values.copy()


def build_feature_row(
    source: SourceTransaction, instance: ScenarioInstance, observation_cutoff: datetime
) -> FeatureRow:
    """Build one row from data available at the supplied prediction cutoff."""
    if source.transaction_id != instance.transaction_id:
        raise ValueError("source transaction and scenario instance must match")

    snapshot = reconstruct_state(instance.events, observation_cutoff)
    observed_events = tuple(event for event in instance.events if event.event_time <= observation_cutoff)
    observed_complaints = tuple(
        complaint for complaint in instance.complaints if complaint.event_time <= observation_cutoff
    )
    first_event_time = observed_events[0].event_time

    # The source Status may reflect an outcome recorded after this cutoff, so it is never a feature.
    values: dict[str, str | int | float | bool] = {
        "amount_inr": float(source.amount_inr),
        "sender_upi_provider": _upi_provider(source.sender_upi_id),
        "receiver_upi_provider": _upi_provider(source.receiver_upi_id),
        "source_hour": source.timestamp.hour,
        "source_weekday": source.timestamp.weekday(),
        "reconstructed_state": snapshot.state.value if snapshot.state else "UNKNOWN",
        "observed_event_count": len(observed_events),
        "last_event_type": observed_events[-1].event_type.value,
        "elapsed_seconds": int((observation_cutoff - first_event_time).total_seconds()),
        "merchant_event_count": sum(event.source == "MERCHANT" for event in observed_events),
        "merchant_order_failure_observed": any(
            event.event_type == EvidenceType.ORDER_FAILURE_CONFIRMED for event in observed_events
        ),
        "observed_complaint_count": len(observed_complaints),
        "observed_high_severity_complaint_count": sum(
            complaint.severity == ComplaintSeverity.HIGH for complaint in observed_complaints
        ),
    }
    return FeatureRow(source.transaction_id, observation_cutoff, FEATURE_DEFINITION_VERSION, values)


def _upi_provider(upi_id: str) -> str:
    """Keep the provider portion while excluding the account-like UPI local part."""
    return upi_id.rsplit("@", 1)[-1]
