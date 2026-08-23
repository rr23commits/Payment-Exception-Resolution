"""Serve the local Phase 14 read-only API from the immutable source CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.api import EngineApi, serve
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    version = inspect_csv(args.csv_path)["source"]["version"]
    serve(EngineApi.from_source_records(read_source_transactions(args.csv_path, version)), args.host, args.port)


if __name__ == "__main__":
    main()
