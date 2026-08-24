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
        recovery = self.api.recovery_by_transaction.get(self.transaction_id)
        expected_trail = recovery.resolution_case.audit_trail if recovery else record.resolution_case.audit_trail
        self.assertEqual(len(audit.body["records"]), len(expected_trail.records))

    def test_incidents_and_evaluation_are_exposed_without_api_truth(self) -> None:
        incidents = self.api.dispatch("/incidents")
        evaluation = self.api.dispatch("/evaluation")

        self.assertEqual(incidents.status, 200)
        self.assertTrue(incidents.body["incidents"])
        self.assertTrue(any(incident["recovery_available"] for incident in incidents.body["incidents"]))
        self.assertEqual(evaluation.body["proof_version"], "phase13-end-to-end-v1")
        self.assertFalse(evaluation.body["execution_scope"]["money_moving_integration"])
        self.assertFalse(hasattr(self.api, "next_state"))
        self.assertFalse(hasattr(self.api, "recommend"))

    def test_invalid_routes_and_transactions_fail_cleanly(self) -> None:
        self.assertEqual(self.api.dispatch("/transactions/unknown/state").status, 404)
        self.assertEqual(self.api.dispatch("/transactions/%s/unknown" % self.transaction_id).status, 404)
        self.assertEqual(self.api.dispatch("/missing").status, 404)

    def test_recovery_decision_is_local_one_time_simulation(self) -> None:
        transaction_id = next(iter(self.api.recovery_by_transaction))
        original = self.api.records_by_transaction[transaction_id]

        pending = self.api.dispatch(f"/transactions/{transaction_id}/recovery")
        approved = self.api.decide_recovery(transaction_id, "APPROVE")

        self.assertEqual(pending.body["opportunity"]["status"], "PENDING_APPROVAL")
        self.assertEqual(approved.body["opportunity"]["status"], "SIMULATED_SUCCEEDED")
        self.assertEqual(approved.body["metrics"]["simulated_recovered_revenue"], str(original.source.amount_inr))
        self.assertEqual(approved.body["policy_decision"]["action"], "REQUIRE HUMAN APPROVAL")
        self.assertEqual(self.api.decide_recovery(transaction_id, "APPROVE").status, 409)
        self.assertEqual(self.api.decide_recovery(transaction_id, "MAYBE").status, 400)
        self.assertEqual(original.instance.final_outcome.value, "REVERSED")
        self.assertEqual(original.resolution_case.verification.final_outcome.value, "REVERSED")

    def test_recovery_rejection_records_no_simulated_outcome(self) -> None:
        transaction_id = next(
            transaction_id
            for transaction_id, recovery in self.api.recovery_by_transaction.items()
            if recovery.opportunity.status.value == "PENDING_APPROVAL"
        )

        rejected = self.api.decide_recovery(transaction_id, "REJECT")
        audit = self.api.dispatch(f"/transactions/{transaction_id}/audit")

        self.assertEqual(rejected.body["opportunity"]["status"], "REJECTED")
        self.assertEqual(rejected.body["metrics"]["simulated_recovered_revenue"], "0")
        self.assertIn("HUMAN_DECISION", [record["record_type"] for record in audit.body["records"]])
        self.assertNotIn("SIMULATED_RECOVERY_OUTCOME", [record["record_type"] for record in audit.body["records"]])

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
