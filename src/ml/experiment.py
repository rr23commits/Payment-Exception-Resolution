"""Reproducible Phase 10 logistic-regression experiment for the V2 target."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, brier_score_loss, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.baseline import ControlledTarget, StateRateBaseline, derive_target, fit, pending_observation_cutoff
from src.domain.source_transaction import SourceTransaction
from src.features import FEATURE_DEFINITION_VERSION, FeatureRow, build_feature_row
from src.generation import ASSIGNMENT_VERSION, generate_scenario_instance
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.ml import SPLIT_VERSION, DatasetSplit, split_for_transaction


EXPERIMENT_VERSION = "phase10-v3-logistic-v1"
RANDOM_SEED = 42

PAYMENT_ATTRIBUTES = (
    "amount_inr",
    "sender_upi_provider",
    "receiver_upi_provider",
    "source_hour",
    "source_weekday",
)
STATE = ("reconstructed_state",)
EVENT_HISTORY_TIMING = ("observed_event_count", "last_event_type", "elapsed_seconds")
MERCHANT_SIGNALS = ("merchant_event_count", "merchant_order_failure_observed")
COMPLAINT_SIGNALS = ("observed_complaint_count", "observed_high_severity_complaint_count")
ABLATIONS = {
    "payment_attributes": PAYMENT_ATTRIBUTES,
    "plus_state": PAYMENT_ATTRIBUTES + STATE,
    "plus_event_history_timing": PAYMENT_ATTRIBUTES + STATE + EVENT_HISTORY_TIMING,
    "plus_merchant_signals": PAYMENT_ATTRIBUTES + STATE + EVENT_HISTORY_TIMING + MERCHANT_SIGNALS,
    "plus_complaint_signals": PAYMENT_ATTRIBUTES + STATE + EVENT_HISTORY_TIMING + MERCHANT_SIGNALS + COMPLAINT_SIGNALS,
}


@dataclass(frozen=True)
class ExperimentRow:
    split: DatasetSplit
    features: FeatureRow
    target: ControlledTarget


def build_rows(records: list[SourceTransaction]) -> list[ExperimentRow]:
    """Build one pending-state target row per transaction at a shared time-safe cutoff."""
    rows = []
    for source in records:
        instance = generate_scenario_instance(source)
        cutoff = pending_observation_cutoff(instance)
        rows.append(
            ExperimentRow(
                split_for_transaction(source.transaction_id),
                build_feature_row(source, instance, cutoff),
                derive_target(instance, cutoff),
            )
        )
    return rows


def run_experiment(records: list[SourceTransaction]) -> dict[str, object]:
    """Train ablations on train rows and compare them to the same held-out baseline."""
    rows = build_rows(records)
    train_rows = [row for row in rows if row.split == DatasetSplit.TRAIN]
    if not train_rows:
        raise ValueError("experiment requires at least one training row")
    baseline = fit([row.features for row in train_rows], [row.target for row in train_rows])
    return {
        "row_count": len(rows),
        "versions": {
            "dataset": records[0].dataset_version if records else None,
            "scenario_assignment": ASSIGNMENT_VERSION,
            "feature_definition": FEATURE_DEFINITION_VERSION,
            "target_definition": "pending-window-v2",
            "split": SPLIT_VERSION,
            "experiment": EXPERIMENT_VERSION,
        },
        "target": "requires_intervention",
        "split_counts": {split.value: sum(row.split == split for row in rows) for split in DatasetSplit},
        "baseline": {
            "type": "train_split_state_rate",
            "state_rates": baseline.intervention_rate_by_state,
            "metrics": _score_baseline(baseline, rows),
        },
        "models": {
            "type": "sklearn_logistic_regression",
            "parameters": {"C": 1.0, "max_iter": 1000, "random_state": RANDOM_SEED, "solver": "liblinear"},
            "ablations": {name: _run_ablation(rows, feature_names) for name, feature_names in ABLATIONS.items()},
        },
        "not_evaluated": ["next_event_prediction", "resolution_time_error"],
    }


def _run_ablation(rows: list[ExperimentRow], feature_names: tuple[str, ...]) -> dict[str, object]:
    model = fit_model(rows, feature_names)
    return {
        "features": list(feature_names),
        "metrics": {
            split.value: _score_model(model, [row for row in rows if row.split == split], feature_names)
            for split in DatasetSplit
        },
    }


def fit_model(rows: list[ExperimentRow], feature_names: tuple[str, ...]) -> Pipeline:
    """Fit the existing deterministic Phase 10 model on train rows only."""
    train_rows = [row for row in rows if row.split == DatasetSplit.TRAIN]
    model = _new_model()
    model.fit(_feature_dicts(train_rows, feature_names), _labels(train_rows))
    return model


def model_probabilities(model: Pipeline, rows: list[ExperimentRow], feature_names: tuple[str, ...]) -> list[float]:
    """Score rows with the selected existing feature contract."""
    return model.predict_proba(_feature_dicts(rows, feature_names))[:, 1].tolist()


def model_probability(model: Pipeline, features: FeatureRow, feature_names: tuple[str, ...]) -> float:
    """Score one independently reconstructed snapshot with the existing model contract."""
    return float(model.predict_proba([{name: features.model_inputs[name] for name in feature_names}])[:, 1][0])


def _new_model() -> Pipeline:
    return Pipeline(
        [
            ("vectorize", DictVectorizer(sparse=True)),
            ("scale", StandardScaler(with_mean=False)),
            ("model", LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_SEED, solver="liblinear")),
        ]
    )


def _feature_dicts(rows: list[ExperimentRow], feature_names: tuple[str, ...]) -> list[dict[str, object]]:
    return [{name: row.features.model_inputs[name] for name in feature_names} for row in rows]


def _labels(rows: list[ExperimentRow]) -> list[bool]:
    return [row.target.requires_intervention for row in rows]


def _score_baseline(baseline: StateRateBaseline, rows: list[ExperimentRow]) -> dict[str, dict[str, float]]:
    return {
        split.value: _score_predictions(
            _labels([row for row in rows if row.split == split]),
            [baseline.predict(row.features).intervention_probability for row in rows if row.split == split],
        )
        for split in DatasetSplit
    }


def _score_model(model: Pipeline, rows: list[ExperimentRow], feature_names: tuple[str, ...]) -> dict[str, float]:
    return _score_predictions(_labels(rows), model_probabilities(model, rows, feature_names))


def _score_predictions(labels: list[bool], probabilities: list[float]) -> dict[str, float]:
    predictions = [probability >= 0.5 for probability in probabilities]
    false_escalations = sum(not label and prediction for label, prediction in zip(labels, predictions))
    return {
        "accuracy": accuracy_score(labels, predictions),
        "recall": recall_score(labels, predictions, zero_division=0),
        "false_escalation_rate": false_escalations / len(labels),
        "brier_score": brier_score_loss(labels, probabilities),
        "roc_auc": roc_auc_score(labels, probabilities),
        "average_precision": average_precision_score(labels, probabilities),
    }


def write_markdown_report(result: dict[str, object], path: Path) -> None:
    """Write the compact human-readable companion to the machine report."""
    test_baseline = result["baseline"]["metrics"]["test"]
    rows = ["# Phase 10 V3 Experiment", "", "## Test-set comparison", "", "| Run | Accuracy | Recall | False escalation | Brier | ROC-AUC | AP |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    rows.append(_metric_row("State-rate baseline", test_baseline))
    for name, ablation in result["models"]["ablations"].items():
        rows.append(_metric_row(name, ablation["metrics"]["test"]))
    rows.extend(["", f"Split counts: `{result['split_counts']}`.", "", "No policy, money action, or UI behavior is included."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _metric_row(name: str, metrics: dict[str, float]) -> str:
    return "| {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
        name,
        metrics["accuracy"],
        metrics["recall"],
        metrics["false_escalation_rate"],
        metrics["brier_score"],
        metrics["roc_auc"],
        metrics["average_precision"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    args = parser.parse_args()
    version = inspect_csv(args.csv_path)["source"]["version"]
    result = run_experiment(read_source_transactions(args.csv_path, version))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown_report(result, args.markdown_report)


if __name__ == "__main__":
    main()
