"""Ordered, provenance-tagged records for a single evaluated incident."""

from __future__ import annotations

from dataclasses import dataclass

from src.provenance import ALL_PROVENANCE


@dataclass(frozen=True)
class AuditRecord:
    sequence_number: int
    transaction_id: str
    record_type: str
    payload: object
    provenance: str

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("audit sequence numbers start at 1")
        if not self.record_type:
            raise ValueError("audit record type is required")
        if self.provenance not in ALL_PROVENANCE:
            raise ValueError("audit record provenance is not recognized")


@dataclass(frozen=True)
class AuditTrail:
    transaction_id: str
    records: tuple[AuditRecord, ...] = ()

    def __post_init__(self) -> None:
        if any(record.transaction_id != self.transaction_id for record in self.records):
            raise ValueError("audit records must belong to one transaction")
        if tuple(record.sequence_number for record in self.records) != tuple(range(1, len(self.records) + 1)):
            raise ValueError("audit records must be contiguous and ordered")

    def append(self, record_type: str, payload: object, provenance: str) -> AuditTrail:
        """Return a new trail; stored records are never reordered or overwritten."""
        record = AuditRecord(len(self.records) + 1, self.transaction_id, record_type, payload, provenance)
        return AuditTrail(self.transaction_id, self.records + (record,))

    def replay(self) -> tuple[AuditRecord, ...]:
        """Return the complete stored sequence for deterministic inspection."""
        return self.records
