"""Evaluate the V1 rules baseline on deterministic controlled ground truth."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.baseline import (
    OBSERVATION_PLAN_VERSION,
    TARGET_DEFINITION_VERSION,
    derive_target,
    fit,
    pending_observation_cutoff,
)
from src.domain.state_machine import STATE_MACHINE_VERSION
from src.features import FEATURE_DEFINITION_VERSION, build_feature_row
from src.generation import ASSIGNMENT_VERSION, generate_scenario_instance
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.ml import SPLIT_VERSION, DatasetSplit, split_for_transaction


def evaluate(records: list[object]) -> dict[str, object]:
    """Create a JSON-safe distribution and metrics report from source records."""
    rows: list[tuple[DatasetSplit, object, object]] = []
    for source in records:
        instance = generate_scenario_instance(source)
        cutoff = pending_observation_cutoff(instance)
        features = build_feature_row(source, instance, cutoff)
        rows.append((split_for_transaction(source.transaction_id), derive_target(instance, cutoff), features))
    train_rows = [(target, features) for split, target, features in rows if split == DatasetSplit.TRAIN]
    baseline = fit([features for _, features in train_rows], [target for target, _ in train_rows])
    scored_rows = [(split, target, baseline.predict(features)) for split, target, features in rows]

    return {
        "row_count": len(scored_rows),
        "versions": {
            "dataset": records[0].dataset_version if records else None,
            "scenario_assignment": ASSIGNMENT_VERSION,
            "state_machine": STATE_MACHINE_VERSION,
            "feature_definition": FEATURE_DEFINITION_VERSION,
            "target_definition": TARGET_DEFINITION_VERSION,
            "observation_plan": OBSERVATION_PLAN_VERSION,
            "split": SPLIT_VERSION,
        },
        "target_distribution": {
            "requires_intervention": dict(sorted(Counter(str(target.requires_intervention).lower() for _, target, _ in scored_rows).items())),
            "intervention_rate_by_amount_band": _intervention_rates_by_amount_band(rows),
        },
        "baseline_state_rates": baseline.intervention_rate_by_state,
        "metrics": _metrics(scored_rows),
    }


def _metrics(rows: list[tuple[DatasetSplit, object, object]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[tuple[object, object]]] = defaultdict(list)
    for split, target, prediction in rows:
        grouped["all"].append((target, prediction))
        grouped[split.value].append((target, prediction))
    return {name: _score(group) for name, group in sorted(grouped.items())}


def _intervention_rates_by_amount_band(rows: list[tuple[DatasetSplit, object, object]]) -> dict[str, float]:
    labels = defaultdict(list)
    for _, target, features in rows:
        band = "high_amount" if features.model_inputs["amount_inr"] >= 1000 else "low_amount"
        labels[band].append(target.requires_intervention)
    return {band: sum(values) / len(values) for band, values in sorted(labels.items())}


def _score(rows: list[tuple[object, object]]) -> dict[str, float]:
    total = len(rows)
    intervention_correct = sum(target.requires_intervention == prediction.requires_intervention for target, prediction in rows)
    actual_interventions = sum(target.requires_intervention for target, _ in rows)
    false_escalations = sum(not target.requires_intervention and prediction.requires_intervention for target, prediction in rows)
    return {
        "intervention_accuracy": intervention_correct / total if total else 0.0,
        "intervention_recall": (
            sum(target.requires_intervention and prediction.requires_intervention for target, prediction in rows) / actual_interventions
            if actual_interventions else 0.0
        ),
        "false_escalation_rate": false_escalations / total if total else 0.0,
        "brier_score": (
            sum((float(target.requires_intervention) - prediction.intervention_probability) ** 2 for target, prediction in rows) / total
            if total else 0.0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    version = inspect_csv(args.csv_path)["source"]["version"]
    report = evaluate(read_source_transactions(args.csv_path, version))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
