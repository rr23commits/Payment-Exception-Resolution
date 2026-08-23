"""Command-line entry point for loading the inspected source CSV."""

import argparse
import json
from pathlib import Path

from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import connect, load_source_transactions, read_source_transactions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    version = inspect_csv(args.csv_path)["source"]["version"]
    records = read_source_transactions(args.csv_path, version)
    with connect() as connection:
        result = load_source_transactions(connection, records)
    print(json.dumps(result.__dict__, sort_keys=True))


if __name__ == "__main__":
    main()
