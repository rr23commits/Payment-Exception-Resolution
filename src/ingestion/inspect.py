"""Reproducible, read-only profiling of the source Kaggle CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


EXPECTED_COLUMNS = (
    "Transaction ID",
    "Timestamp",
    "Sender Name",
    "Sender UPI ID",
    "Receiver Name",
    "Receiver UPI ID",
    "Amount (INR)",
    "Status",
)
SOURCE_TRANSACTION_MAPPING = {
    "transaction_id": "Transaction ID",
    "timestamp": "Timestamp",
    "sender_name": "Sender Name",
    "sender_upi_id": "Sender UPI ID",
    "receiver_name": "Receiver Name",
    "receiver_upi_id": "Receiver UPI ID",
    "amount_inr": "Amount (INR)",
    "status": "Status",
}


def _inferred_type(column: str, values: list[str]) -> str:
    if column == "Timestamp":
        try:
            [datetime.strptime(value, "%Y-%m-%d %H:%M:%S") for value in values]
        except ValueError:
            return "string"
        return "datetime (%Y-%m-%d %H:%M:%S)"
    if column == "Amount (INR)":
        try:
            [Decimal(value) for value in values]
        except InvalidOperation:
            return "string"
        return "decimal"
    return "string"


def inspect_csv(path: Path) -> dict[str, object]:
    """Profile CSV values without rewriting or deriving source records."""
    raw = path.read_bytes()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("source CSV must have a header row")
        columns = reader.fieldnames
        rows = list(reader)

    values = {column: [row[column] for row in rows] for column in columns}
    timestamps = values.get("Timestamp", [])
    amounts = [Decimal(value) for value in values.get("Amount (INR)", [])]
    transaction_ids = values.get("Transaction ID", [])
    return {
        "source": {
            "filename": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "version": f"sha256:{hashlib.sha256(raw).hexdigest()}",
            "bytes": len(raw),
            "row_count": len(rows),
        },
        "columns": columns,
        "inferred_types": {column: _inferred_type(column, values[column]) for column in columns},
        "timestamp": {
            "format": "%Y-%m-%d %H:%M:%S" if _inferred_type("Timestamp", timestamps).startswith("datetime") else None,
            "min": min(timestamps) if timestamps else None,
            "max": max(timestamps) if timestamps else None,
        },
        "missing_values": {column: sum(not value.strip() for value in values[column]) for column in columns},
        "transaction_id": {
            "unique": len(set(transaction_ids)) == len(transaction_ids),
            "distinct_count": len(set(transaction_ids)),
            "duplicate_count": len(transaction_ids) - len(set(transaction_ids)),
        },
        "status_distribution": dict(sorted(Counter(values.get("Status", [])).items())),
        "amount_inr": {
            "min": str(min(amounts)) if amounts else None,
            "max": str(max(amounts)) if amounts else None,
            "mean": str(sum(amounts) / len(amounts)) if amounts else None,
        },
        "field_quality": {
            column: {
                "non_empty": sum(bool(value.strip()) for value in values[column]),
                "distinct_count": len(set(values[column])),
                "valid_upi_format": sum(value.count("@") == 1 and all(value.split("@")) for value in values[column])
                if "UPI ID" in column
                else None,
            }
            for column in ("Sender Name", "Sender UPI ID", "Receiver Name", "Receiver UPI ID")
            if column in values
        },
        "duplicate_rows": len(rows) - len({tuple(row[column] for column in columns) for row in rows}),
        "undocumented_columns": [column for column in columns if column not in EXPECTED_COLUMNS],
        "lifecycle_event_fields_present": False,
        "source_transaction_mapping": SOURCE_TRANSACTION_MAPPING,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_csv(args.csv_path)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
