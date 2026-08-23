import unittest
from pathlib import Path

from src.ingestion.inspect import inspect_csv


class DatasetInspectionTests(unittest.TestCase):
    def test_source_profile_is_reproducible_and_complete(self) -> None:
        source = Path("data/raw/transactions.csv")
        first = inspect_csv(source)
        second = inspect_csv(source)
        self.assertEqual(first, second)
        self.assertEqual(first["source"]["row_count"], 1000)
        self.assertTrue(first["transaction_id"]["unique"])
        self.assertFalse(first["lifecycle_event_fields_present"])
        self.assertEqual(set(first["columns"]), set(first["source_transaction_mapping"].values()))
