"""Generate and persist deterministic lifecycle ground truth for the inspected source CSV."""

import argparse
from pathlib import Path

from src.generation import generate_scenario_instance, write_ground_truth
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/generated"))
    args = parser.parse_args()
    version = inspect_csv(args.csv_path)["source"]["version"]
    for source in read_source_transactions(args.csv_path, version):
        write_ground_truth(generate_scenario_instance(source), args.output)


if __name__ == "__main__":
    main()
