"""Thin read-only HTTP boundary over existing evaluated engine records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.domain.source_transaction import SourceTransaction
from src.evaluation import EngineRecord, build_engine_records, run_engine_proof
from src.recovery import RecoveryOpportunity, apply_decision, create_opportunity, read_model, retry_policy, simulate_retry
from src.resolution import HumanDecision, ModeledHumanDecision, ResolutionCase


_UI_DIRECTORY = Path(__file__).resolve().parents[2] / "ui"
_UI_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: dict[str, Any]


@dataclass(frozen=True)
class RecoveryState:
    opportunity: RecoveryOpportunity
    policy_decision: object
    resolution_case: ResolutionCase


@dataclass
class EngineApi:
    """Routes precomputed engine records plus local simulated recovery state."""

    records_by_transaction: dict[str, EngineRecord]
    evaluation: dict[str, object]
    recovery_by_transaction: dict[str, RecoveryState]

    @classmethod
    def from_source_records(cls, records: list[SourceTransaction]) -> EngineApi:
        engine_records = build_engine_records(records)
        recovery = {}
        for record in engine_records:
            opportunity = create_opportunity(record)
            if opportunity is not None:
                policy = retry_policy(record)
                recovery[record.source.transaction_id] = RecoveryState(opportunity, policy, record.resolution_case.record_recovery_opportunity(opportunity))
        return cls({record.source.transaction_id: record for record in engine_records}, run_engine_proof(records, engine_records), recovery)

    def dispatch(self, path: str) -> ApiResponse:
        """Return JSON-safe read models for the explicitly supported GET paths."""
        route = urlsplit(path).path.rstrip("/") or "/"
        if route == "/incidents":
            return ApiResponse(
                200,
                {
                    "incidents": [
                        _incident_summary(record, record.source.transaction_id in self.recovery_by_transaction)
                        for record in self.records_by_transaction.values()
                        if record.incidents or record.source.transaction_id in self.recovery_by_transaction
                    ]
                },
            )
        if route == "/evaluation":
            return ApiResponse(200, _json_value(self.evaluation))
        parts = route.split("/")
        if len(parts) != 4 or parts[:2] != ["", "transactions"]:
            return ApiResponse(404, {"error": "route not found"})
        record = self.records_by_transaction.get(parts[2])
        if record is None:
            return ApiResponse(404, {"error": "transaction not found"})
        endpoint = parts[3]
        if endpoint == "recovery":
            recovery = self.recovery_by_transaction.get(record.source.transaction_id)
            if recovery is None:
                return ApiResponse(404, {"error": "recovery opportunity not found"})
            return ApiResponse(200, self._recovery_body(record, recovery))
        if endpoint == "incidents":
            return ApiResponse(200, {"transaction_id": record.source.transaction_id, "incidents": _json_value(record.incidents)})
        if endpoint == "state":
            return ApiResponse(200, {"transaction_id": record.source.transaction_id, "snapshot": _json_value(record.snapshot)})
        if endpoint == "predictions":
            return ApiResponse(
                200,
                {
                    "transaction_id": record.source.transaction_id,
                    "baseline_prediction": _json_value(record.baseline_prediction),
                    "model_prediction": _json_value(record.model_prediction),
                    "policy_decision": _json_value(record.policy_decision),
                },
            )
        if endpoint == "resolution":
            return ApiResponse(
                200,
                {
                    "transaction_id": record.source.transaction_id,
                    "verification": _json_value(record.resolution_case.verification),
                    "human_decision": _json_value(record.resolution_case.human_decision),
                },
            )
        if endpoint == "audit":
            recovery = self.recovery_by_transaction.get(record.source.transaction_id)
            trail = recovery.resolution_case.audit_trail if recovery is not None else record.resolution_case.audit_trail
            return ApiResponse(200, {"transaction_id": record.source.transaction_id, "records": _json_value(trail.records)})
        return ApiResponse(404, {"error": "route not found"})

    def decide_recovery(self, transaction_id: str, decision: str) -> ApiResponse:
        """Apply exactly one local operator decision; no engine record or provider is changed."""
        if decision not in {"APPROVE", "REJECT"}:
            return ApiResponse(400, {"error": "decision must be APPROVE or REJECT"})
        record = self.records_by_transaction.get(transaction_id)
        recovery = self.recovery_by_transaction.get(transaction_id)
        if record is None:
            return ApiResponse(404, {"error": "transaction not found"})
        if recovery is None:
            return ApiResponse(404, {"error": "recovery opportunity not found"})
        try:
            opportunity = apply_decision(recovery.opportunity, decision == "APPROVE")
            case = recovery.resolution_case.record_human_decision(ModeledHumanDecision(HumanDecision(decision), "operator recovery decision"), recovery.policy_decision)
            if decision == "APPROVE":
                opportunity = simulate_retry(opportunity)
                case = case.record_simulated_recovery(opportunity)
        except ValueError as error:
            return ApiResponse(409, {"error": str(error)})
        updated = RecoveryState(opportunity, recovery.policy_decision, case)
        self.recovery_by_transaction[transaction_id] = updated
        return ApiResponse(200, self._recovery_body(record, updated))

    def _recovery_body(self, record: EngineRecord, recovery: RecoveryState) -> dict[str, Any]:
        body = _json_value(read_model(record, recovery.opportunity, recovery.policy_decision))
        body["transaction_id"] = record.source.transaction_id
        body["audit"] = _json_value(recovery.resolution_case.audit_trail.records)
        return body


def make_handler(api: EngineApi) -> type[BaseHTTPRequestHandler]:
    """Adapt the pure dispatcher to a local standard-library HTTP server."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler callback name
            asset = _UI_ASSETS.get(urlsplit(self.path).path)
            if asset:
                content = (_UI_DIRECTORY / asset[0]).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", asset[1])
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            response = api.dispatch(self.path)
            encoded = json.dumps(response.body, sort_keys=True).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler callback name
            route = urlsplit(self.path).path.rstrip("/")
            parts = route.split("/")
            if len(parts) != 5 or parts[:2] != ["", "transactions"] or parts[3:] != ["recovery", "decision"]:
                self.send_error(404, "route not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                if set(payload) != {"decision"} or not isinstance(payload["decision"], str):
                    raise ValueError
            except (ValueError, json.JSONDecodeError):
                response = ApiResponse(400, {"error": "body must contain only a decision"})
            else:
                response = api.decide_recovery(parts[2], payload["decision"])
            encoded = json.dumps(response.body, sort_keys=True).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve(api: EngineApi, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve existing records locally; no request path mutates the engine."""
    ThreadingHTTPServer((host, port), make_handler(api)).serve_forever()


def _incident_summary(record: EngineRecord, recovery_available: bool = False) -> dict[str, object]:
    route = f"{record.source.sender_upi_id.rsplit('@', 1)[-1]} → {record.source.receiver_upi_id.rsplit('@', 1)[-1]}"
    recovery = "RECOVERY_ELIGIBLE" if recovery_available else "NO_RECOVERY_PATH"
    return {
        "transaction_id": record.source.transaction_id,
        "incidents": _json_value(record.incidents),
        "recovery_available": recovery_available,
        "amount": str(record.source.amount_inr),
        "timestamp": _json_value(record.source.timestamp),
        "route": route,
        "state": record.snapshot.state.value if record.snapshot.state else "UNKNOWN",
        "recovery_status": recovery,
    }


def _json_value(value: object) -> Any:
    """Serialize existing typed records without adding API-specific business fields."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
