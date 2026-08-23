"""Physical source-only transaction record loaded from the inspected CSV."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.provenance import SOURCE_DATASET


@dataclass(frozen=True)
class SourceTransaction:
    transaction_id: str
    timestamp: datetime
    sender_name: str
    sender_upi_id: str
    receiver_name: str
    receiver_upi_id: str
    amount_inr: Decimal
    status: str
    dataset_version: str
    provenance: str = SOURCE_DATASET
