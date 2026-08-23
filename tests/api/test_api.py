from pathlib import Path
import json
from http.server import ThreadingHTTPServer
from threading import Thread
import unittest
from urllib.request import urlopen

from src.api import EngineApi, make_handler
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions


SOURCE = Path("data/raw/transactions.csv")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.api = EngineApi.from_source_records(read_source_transactions(SOURCE, version))
        cls.transaction_id = next(iter(cls.api.records_by_transaction))

    def test_responses_match_existing_engine_records(self) -> None:
        record = self.api.records_by_transaction[self.transaction_id]

        state = self.api.dispatch(f"/transactions/{self.transaction_id}/state")
        predictions = self.api.dispatch(f"/transactions/{self.transaction_id}/predictions")
        resolution = self.api.dispatch(f"/transactions/{self.transaction_id}/resolution")
        audit = self.api.dispatch(f"/transactions/{self.transaction_id}/audit")

        self.assertEqual(state.status, 200)
        self.assertEqual(state.body["snapshot"]["state"], record.snapshot.state.value)
        self.assertEqual(predictions.body["model_prediction"]["probability"], record.model_prediction.probability)
        self.assertEqual(predictions.body["policy_decision"]["action"], record.policy_decision.action.value)
        self.assertEqual(resolution.body["verification"]["final_outcome"], record.resolution_case.verification.final_outcome.value)
        self.assertEqual(len(audit.body["records"]), len(record.resolution_case.audit_trail.records))

    def test_incidents_and_evaluation_are_exposed_without_api_truth(self) -> None:
        incidents = self.api.dispatch("/incidents")
        evaluation = self.api.dispatch("/evaluation")

        self.assertEqual(incidents.status, 200)
        self.assertTrue(incidents.body["incidents"])
        self.assertEqual(evaluation.body["proof_version"], "phase13-end-to-end-v1")
        self.assertFalse(evaluation.body["execution_scope"]["money_moving_integration"])
        self.assertFalse(hasattr(self.api, "next_state"))
        self.assertFalse(hasattr(self.api, "recommend"))

    def test_invalid_routes_and_transactions_fail_cleanly(self) -> None:
        self.assertEqual(self.api.dispatch("/transactions/unknown/state").status, 404)
        self.assertEqual(self.api.dispatch("/transactions/%s/unknown" % self.transaction_id).status, 404)
        self.assertEqual(self.api.dispatch("/missing").status, 404)

    def test_local_http_adapter_returns_dispatcher_data(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.api))
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/transactions/{self.transaction_id}/state") as response:
                body = json.load(response)
            with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
                page = response.read().decode("utf-8")
            self.assertEqual(body["snapshot"]["state"], self.api.records_by_transaction[self.transaction_id].snapshot.state.value)
            self.assertIn("Simulated controlled data only", page)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
