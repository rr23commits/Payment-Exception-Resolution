"""Controlled customer complaint vocabulary; never financial-state authority."""

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from src.domain.scenarios import ScenarioId


class ComplaintType(str, Enum):
    PAYMENT_CONFIRMATION_PENDING = "PAYMENT_CONFIRMATION_PENDING"
    REVERSAL_PENDING = "REVERSAL_PENDING"
    ORDER_NOT_FULFILLED = "ORDER_NOT_FULFILLED"
    REFUND_PENDING = "REFUND_PENDING"


class ComplaintSeverity(str, Enum):
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ComplaintSpecification:
    complaint_type: ComplaintType
    text: str
    severity: ComplaintSeverity
    offset: timedelta


COMPLAINTS_BY_SCENARIO = {
    ScenarioId.TIMEOUT_TO_REVERSAL: ComplaintSpecification(
        ComplaintType.PAYMENT_CONFIRMATION_PENDING,
        "My account was debited, but payment confirmation is pending.",
        ComplaintSeverity.HIGH,
        timedelta(minutes=3),
    ),
    ScenarioId.DELAYED_STUCK_REVERSAL: ComplaintSpecification(
        ComplaintType.REVERSAL_PENDING,
        "My account was debited, but reversal is still pending.",
        ComplaintSeverity.HIGH,
        timedelta(minutes=3),
    ),
    ScenarioId.PAYMENT_SUCCESS_ORDER_FAILURE: ComplaintSpecification(
        ComplaintType.ORDER_NOT_FULFILLED,
        "Payment succeeded, but my order was not fulfilled.",
        ComplaintSeverity.HIGH,
        timedelta(minutes=4),
    ),
    ScenarioId.REFUND_PENDING_STUCK: ComplaintSpecification(
        ComplaintType.REFUND_PENDING,
        "My refund is still pending.",
        ComplaintSeverity.HIGH,
        timedelta(minutes=4),
    ),
}
