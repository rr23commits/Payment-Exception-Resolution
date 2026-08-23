import unittest

from src.audit import AuditRecord, AuditTrail
from src.provenance import DERIVED_STATE


class AuditTests(unittest.TestCase):
    def test_records_are_contiguous_ordered_and_replayable(self) -> None:
        trail = AuditTrail("txn-1").append("STATE", {"state": "BANK_DEBITED"}, DERIVED_STATE).append("FEATURES", {}, DERIVED_STATE)

        self.assertEqual([record.sequence_number for record in trail.replay()], [1, 2])
        self.assertEqual([record.provenance for record in trail.replay()], [DERIVED_STATE, DERIVED_STATE])

    def test_invalid_order_or_provenance_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "contiguous"):
            AuditTrail("txn-1", (AuditRecord(2, "txn-1", "STATE", {}, DERIVED_STATE),))
        with self.assertRaisesRegex(ValueError, "not recognized"):
            AuditRecord(1, "txn-1", "STATE", {}, "UNKNOWN")
