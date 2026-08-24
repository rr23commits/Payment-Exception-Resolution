"""Reproducible Phase 13 end-to-end engine proof without API or UI dependencies."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.baseline import derive_target, fit, pending_observation_cutoff
from src.baseline import BaselinePrediction
from src.domain.scenarios import SCENARIOS
from src.domain.scenarios.config import parameters_for
from src.domain.source_transaction import SourceTransaction
from src.domain.state_machine import STATE_MACHINE_VERSION
from src.engine.exceptions import ExceptionIncident, detect_exceptions
from src.engine.reconstruction import StateSnapshot, reconstruct_state
from src.features import FEATURE_DEFINITION_VERSION, FeatureRow, build_feature_row
from src.generation import ASSIGNMENT_VERSION, ScenarioInstance, generate_scenario_instance
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.ml import DatasetSplit
from src.ml.experiment import ABLATIONS, EXPERIMENT_VERSION, build_rows, fit_model, model_probability, model_probabilities, run_experiment
from src.policy import PolicyAction, PolicyDecision, PredictionSignal, recommend
from src.resolution import HumanDecision, ModeledHumanDecision, VersionedPrediction, open_resolution_case
from src.resolution import ResolutionCase


PROOF_VERSION = "phase13-end-to-end-v1"
MODEL_ABLATION = "plus_complaint_signals"
BASELINE_VERSION = "phase9-train-split-state-rate-v1"


@dataclass(frozen=True)
class EngineRecord:
    """Existing engine outputs for one transaction; this adds no new domain truth."""

    source: SourceTransaction
    instance: ScenarioInstance
    snapshot: StateSnapshot
    incidents: tuple[ExceptionIncident, ...]
    features: FeatureRow
    baseline_prediction: BaselinePrediction
    model_prediction: PredictionSignal
    recovery_features: FeatureRow
    recovery_prediction: PredictionSignal
    policy_decision: PolicyDecision
    resolution_case: ResolutionCase


def run_engine_proof(
    records: list[SourceTransaction], engine_records: tuple[EngineRecord, ...] | None = None
) -> dict[str, object]:
    """Execute the full evidence-to-audit path for every source transaction."""
    if not records:
        raise ValueError("end-to-end proof requires source transactions")
    experiment = run_experiment(records)
    if engine_records is None:
        engine_records = build_engine_records(records)
    if len(engine_records) != len(records):
        raise ValueError("engine records must cover every source transaction")
    proof = _summarize_records(engine_records)
    proof["intervention_recall"] = experiment["models"]["ablations"][MODEL_ABLATION]["metrics"]["test"]["recall"]
    proof["false_escalation_rate"] = experiment["models"]["ablations"][MODEL_ABLATION]["metrics"]["test"]["false_escalation_rate"]
    return {
        "proof_version": PROOF_VERSION,
        "dataset": {"version": records[0].dataset_version, "sha256": records[0].dataset_version.removeprefix("sha256:"), "row_count": len(records)},
        "scenario_configuration": {
            "assignment_version": ASSIGNMENT_VERSION,
            "scenarios": {
                scenario.scenario_id.value: {
                    "evidence": [evidence.value for evidence in scenario.evidence],
                    "expected_resolution_window_seconds": parameters_for(scenario).expected_resolution_window.total_seconds(),
                }
                for scenario in SCENARIOS
            },
        },
        "definitions": {
            "state_machine": STATE_MACHINE_VERSION,
            "feature_definition": FEATURE_DEFINITION_VERSION,
            "baseline": "train-split intervention rate by reconstructed pending state",
            "model": {"version": EXPERIMENT_VERSION, "ablation": MODEL_ABLATION, "type": experiment["models"]["type"]},
        },
        "pipeline": proof,
        "performance_comparison": {
            "baseline_test": experiment["baseline"]["metrics"]["test"],
            "model_test": experiment["models"]["ablations"][MODEL_ABLATION]["metrics"]["test"],
        },
        "ablation_test_metrics": {
            name: result["metrics"]["test"] for name, result in experiment["models"]["ablations"].items()
        },
        "resolution_time_error": "not applicable: the approved model predicts intervention only, not a duration",
        "limitations": [
            "Lifecycle, complaint, timing, and outcome data are deterministic controlled simulations.",
            "The report evaluates a transaction-ID held-out split; it is not a production-service estimate.",
            "Policy recommendations and modeled human decisions do not execute payment operations.",
        ],
        "execution_scope": {"ui_required": False, "api_required": False, "money_moving_integration": False},
    }


def build_engine_records(records: list[SourceTransaction]) -> tuple[EngineRecord, ...]:
    """Run the approved Phase 13 pipeline and retain its existing per-transaction outputs."""
    if not records:
        raise ValueError("end-to-end proof requires source transactions")
    rows = build_rows(records)
    train_rows = [row for row in rows if row.split == DatasetSplit.TRAIN]
    baseline = fit([row.features for row in train_rows], [row.target for row in train_rows])
    feature_names = ABLATIONS[MODEL_ABLATION]
    model = fit_model(rows, feature_names)
    probabilities = dict(zip((row.features.transaction_id for row in rows), model_probabilities(model, rows, feature_names)))
    output = []
    for source in records:
        instance = generate_scenario_instance(source)
        cutoff = pending_observation_cutoff(instance)
        snapshot = reconstruct_state(instance.events, cutoff)
        incidents = detect_exceptions(snapshot, instance.expected_resolution_window)
        features = build_feature_row(source, instance, cutoff)
        target = derive_target(instance, cutoff)
        baseline_prediction = baseline.predict(features)
        model_score = probabilities[source.transaction_id]
        model_signal = PredictionSignal(model_score >= 0.5, model_score)
        # Recovery reconstructs the earlier timeout cutoff, so it must be scored from
        # that same snapshot rather than reuse the pending-state prediction below.
        recovery_features = build_feature_row(source, instance, instance.observation_cutoff)
        recovery_probability = model_probability(model, recovery_features, feature_names)
        recovery_signal = PredictionSignal(recovery_probability >= 0.5, recovery_probability)
        policy = recommend(snapshot, incidents, model_signal)
        case = open_resolution_case(
            instance,
            snapshot,
            incidents,
            features,
            (
                VersionedPrediction(BASELINE_VERSION, PredictionSignal(baseline_prediction.requires_intervention, baseline_prediction.intervention_probability)),
                VersionedPrediction(EXPERIMENT_VERSION, model_signal),
            ),
            policy,
        )
        if policy.action == PolicyAction.REQUIRE_HUMAN_APPROVAL:
            case = case.record_human_decision(ModeledHumanDecision(HumanDecision.REJECT, "modeled approval gate"))
        verified = case.reveal_and_verify(instance)
        if verified.verification is None or verified.verification.requires_intervention != target.requires_intervention:
            raise ValueError("resolution verification disagrees with the controlled target")
        output.append(
            EngineRecord(
                source,
                instance,
                snapshot,
                incidents,
                features,
                baseline_prediction,
                model_signal,
                recovery_features,
                recovery_signal,
                policy,
                verified,
            )
        )
    return tuple(output)


def _summarize_records(records: tuple[EngineRecord, ...]) -> dict[str, object]:
    action_counts: Counter[str] = Counter()
    total_audit_records = 0
    human_decisions = 0
    for record in records:
        action_counts[record.policy_decision.action.value] += 1
        total_audit_records += len(record.resolution_case.audit_trail.records)
        human_decisions += record.resolution_case.human_decision is not None
    return {
        "evaluated_incidents": len(records),
        "verified_resolutions": len(records),
        "audit_record_count": total_audit_records,
        "policy_action_counts": dict(sorted(action_counts.items())),
        "modeled_human_decision_count": human_decisions,
    }


def write_markdown_report(result: dict[str, object], path: Path) -> None:
    """Write a compact, standalone proof report for the no-UI engine run."""
    baseline = result["performance_comparison"]["baseline_test"]
    model = result["performance_comparison"]["model_test"]
    pipeline = result["pipeline"]
    lines = [
        "# Phase 13 End-to-End Engine Proof",
        "",
        f"Dataset: `{result['dataset']['version']}` ({result['dataset']['row_count']} source rows).",
        f"Verified resolutions: `{pipeline['verified_resolutions']}/{pipeline['evaluated_incidents']}`; audit records: `{pipeline['audit_record_count']}`.",
        "",
        "## Held-out performance",
        "",
        "| Run | Recall | False escalation | Brier | ROC-AUC | AP |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        _metric_row("State-rate baseline", baseline),
        _metric_row("Phase 10 V3 logistic model", model),
        "",
        f"Resolution-time error: {result['resolution_time_error']}.",
        "",
        "No API, UI, or money-moving integration is required or implemented.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _metric_row(name: str, metrics: dict[str, float]) -> str:
    return "| {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
        name,
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
    result = run_engine_proof(read_source_transactions(args.csv_path, version))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown_report(result, args.markdown_report)


if __name__ == "__main__":
    main()
