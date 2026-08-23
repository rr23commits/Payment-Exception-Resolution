"""Thin read-only HTTP boundary over existing evaluated engine records."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.domain.source_transaction import SourceTransaction
from src.evaluation import EngineRecord, build_engine_records, run_engine_proof


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
class EngineApi:
    """Routes precomputed engine records; it does not implement engine decisions."""

    records_by_transaction: dict[str, EngineRecord]
    evaluation: dict[str, object]

    @classmethod
    def from_source_records(cls, records: list[SourceTransaction]) -> EngineApi:
        engine_records = build_engine_records(records)
        return cls({record.source.transaction_id: record for record in engine_records}, run_engine_proof(records, engine_records))

    def dispatch(self, path: str) -> ApiResponse:
        """Return JSON-safe read models for the explicitly supported GET paths."""
        route = urlsplit(path).path.rstrip("/") or "/"
        if route == "/incidents":
            return ApiResponse(200, {"incidents": [_incident_summary(record) for record in self.records_by_transaction.values() if record.incidents]})
        if route == "/evaluation":
            return ApiResponse(200, _json_value(self.evaluation))
        parts = route.split("/")
        if len(parts) != 4 or parts[:2] != ["", "transactions"]:
            return ApiResponse(404, {"error": "route not found"})
        record = self.records_by_transaction.get(parts[2])
        if record is None:
            return ApiResponse(404, {"error": "transaction not found"})
        endpoint = parts[3]
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
            return ApiResponse(200, {"transaction_id": record.source.transaction_id, "records": _json_value(record.resolution_case.audit_trail.records)})
        return ApiResponse(404, {"error": "route not found"})


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
            self.send_error(405, "read-only API")

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve(api: EngineApi, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve existing records locally; no request path mutates the engine."""
    ThreadingHTTPServer((host, port), make_handler(api)).serve_forever()


def _incident_summary(record: EngineRecord) -> dict[str, object]:
    return {"transaction_id": record.source.transaction_id, "incidents": _json_value(record.incidents)}


def _json_value(value: object) -> Any:
    """Serialize existing typed records without adding API-specific business fields."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, timedelta):
        return value.total_seconds()
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
