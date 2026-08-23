"""Validate, load, and look up source-only Kaggle transaction records."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

from src.config import database_url
from src.domain.source_transaction import SourceTransaction
from src.ingestion.inspect import EXPECTED_COLUMNS
from src.provenance import SOURCE_DATASET


@dataclass(frozen=True)
class LoadResult:
    source_rows: int
    inserted_rows: int
    existing_rows: int


def read_source_transactions(path: Path, dataset_version: str) -> list[SourceTransaction]:
    """Reject an unexpected CSV contract before anything reaches PostgreSQL."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(EXPECTED_COLUMNS):
            raise ValueError(f"invalid source CSV columns: expected {list(EXPECTED_COLUMNS)!r}, got {reader.fieldnames!r}")
        records = [_record_from_row(row, dataset_version) for row in reader]
    if not records:
        raise ValueError("source CSV contains no transaction rows")
    ids = [record.transaction_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("source CSV has duplicate Transaction ID values")
    return records


def _record_from_row(row: dict[str, str], dataset_version: str) -> SourceTransaction:
    try:
        timestamp = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")
        amount = Decimal(row["Amount (INR)"])
    except (ValueError, InvalidOperation) as error:
        raise ValueError(f"invalid source value for transaction {row.get('Transaction ID')!r}") from error
    values = [value.strip() for value in row.values()]
    if not all(values) or amount < 0:
        raise ValueError(f"blank or negative source value for transaction {row.get('Transaction ID')!r}")
    return SourceTransaction(
        transaction_id=row["Transaction ID"],
        timestamp=timestamp,
        sender_name=row["Sender Name"],
        sender_upi_id=row["Sender UPI ID"],
        receiver_name=row["Receiver Name"],
        receiver_upi_id=row["Receiver UPI ID"],
        amount_inr=amount,
        status=row["Status"],
        dataset_version=dataset_version,
    )


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url())


def create_source_transactions_table(connection: psycopg.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_transactions (
            transaction_id TEXT PRIMARY KEY,
            transaction_timestamp TIMESTAMP NOT NULL,
            sender_name TEXT NOT NULL,
            sender_upi_id TEXT NOT NULL,
            receiver_name TEXT NOT NULL,
            receiver_upi_id TEXT NOT NULL,
            amount_inr NUMERIC NOT NULL,
            source_status TEXT NOT NULL,
            dataset_version TEXT NOT NULL,
            provenance TEXT NOT NULL CHECK (provenance = 'SOURCE_DATASET')
        )
        """
    )


def load_source_transactions(connection: psycopg.Connection, records: list[SourceTransaction]) -> LoadResult:
    """Insert a source snapshot once; reject a changed record with the same ID."""
    create_source_transactions_table(connection)
    existing = {
        row[0]: row[1:]
        for row in connection.execute(
            """SELECT transaction_id, transaction_timestamp, sender_name, sender_upi_id,
                      receiver_name, receiver_upi_id, amount_inr, source_status,
                      dataset_version, provenance
               FROM source_transactions WHERE transaction_id = ANY(%s)""",
            ([record.transaction_id for record in records],),
        )
    }
    new_records = []
    for record in records:
        current = existing.get(record.transaction_id)
        # The query stores the ID as the dictionary key, so compare only its remaining values.
        database_values = _database_values(record)
        expected = database_values[1:]
        if current is None:
            new_records.append(database_values)
        elif current != expected:
            raise ValueError(f"source transaction {record.transaction_id!r} conflicts with stored source data")

    if new_records:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO source_transactions (
                        transaction_id, transaction_timestamp, sender_name, sender_upi_id,
                        receiver_name, receiver_upi_id, amount_inr, source_status,
                        dataset_version, provenance
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                new_records,
            )
    return LoadResult(len(records), len(new_records), len(records) - len(new_records))


def get_source_transaction(connection: psycopg.Connection, transaction_id: str) -> SourceTransaction | None:
    row = connection.execute(
        """SELECT transaction_id, transaction_timestamp, sender_name, sender_upi_id,
                  receiver_name, receiver_upi_id, amount_inr, source_status,
                  dataset_version, provenance
           FROM source_transactions WHERE transaction_id = %s""",
        (transaction_id,),
    ).fetchone()
    return SourceTransaction(*row) if row else None


def _database_values(record: SourceTransaction) -> tuple[object, ...]:
    return (
        record.transaction_id,
        record.timestamp,
        record.sender_name,
        record.sender_upi_id,
        record.receiver_name,
        record.receiver_upi_id,
        record.amount_inr,
        record.status,
        record.dataset_version,
        SOURCE_DATASET,
    )
