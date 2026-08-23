import csv
import tempfile
import unittest
from pathlib import Path

from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import (
    connect,
    create_source_transactions_table,
    get_source_transaction,
    load_source_transactions,
    read_source_transactions,
)
from src.provenance import SOURCE_DATASET


SOURCE = Path("data/raw/transactions.csv")


class SourceTransactionIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = connect()
        create_source_transactions_table(cls.connection)
        cls.connection.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def setUp(self) -> None:
        self.connection.execute("DELETE FROM source_transactions")
        self.connection.commit()

    def test_valid_source_loads_once_and_is_queryable(self) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        records = read_source_transactions(SOURCE, version)
        first = load_source_transactions(self.connection, records)
        self.connection.commit()
        second = load_source_transactions(self.connection, records)
        self.connection.commit()

        loaded = get_source_transaction(self.connection, records[0].transaction_id)
        self.assertEqual((first.source_rows, first.inserted_rows, first.existing_rows), (1000, 1000, 0))
        self.assertEqual((second.inserted_rows, second.existing_rows), (0, 1000))
        self.assertEqual(loaded, records[0])
        self.assertEqual(loaded.provenance, SOURCE_DATASET)

    def test_invalid_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "bad.csv"
            with malformed.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Transaction ID", "unexpected"])
                writer.writerow(["id", "value"])
            with self.assertRaisesRegex(ValueError, "invalid source CSV columns"):
                read_source_transactions(malformed, "sha256:test")
