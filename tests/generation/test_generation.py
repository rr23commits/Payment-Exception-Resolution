import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from src.domain.complaints import ComplaintType
from src.domain.scenarios import SCENARIOS
from src.ingestion.inspect import inspect_csv
from src.ingestion.source_transactions import read_source_transactions
from src.generation import generate_scenario_instance, write_ground_truth
from src.provenance import GENERATED_COMPLAINT, GENERATED_LIFECYCLE
from src.domain.state_machine import apply_evidence


SOURCE = Path("data/raw/transactions.csv")


class LifecycleGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        version = inspect_csv(SOURCE)["source"]["version"]
        cls.source = read_source_transactions(SOURCE, version)[0]

    def test_generation_is_repeatable_and_does_not_change_source(self) -> None:
        original = self.source
        first = generate_scenario_instance(original)
        second = generate_scenario_instance(original)
        changed_status = replace(original, status="FAILED" if original.status == "SUCCESS" else "SUCCESS")

        self.assertEqual(first, second)
        self.assertEqual(first.scenario_id, generate_scenario_instance(changed_status).scenario_id)
        self.assertEqual(original, self.source)

    def test_events_are_ordered_valid_and_hidden_after_cutoff(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[2])
        self.assertEqual([event.sequence_number for event in instance.events], list(range(1, len(instance.events) + 1)))
        self.assertEqual([event.event_time for event in instance.events], sorted(event.event_time for event in instance.events))
        self.assertTrue(all(event.generation_origin == GENERATED_LIFECYCLE for event in instance.events))
        self.assertTrue(all(event.event_type.value for event in instance.events))
        self.assertTrue(all(event.event_time <= instance.observation_cutoff for event in instance.observed_events))
        self.assertTrue(all(event.event_time > instance.observation_cutoff for event in instance.hidden_future_events))
        self.assertEqual(instance.final_outcome.value, "REFUNDED")
        self.assertEqual(apply_evidence([event.event_type for event in instance.events]), instance.final_outcome)
        self.assertEqual(len(instance.merchant_evidence), 2)

    def test_ground_truth_storage_retains_envelope_and_hidden_boundary(self) -> None:
        instance = generate_scenario_instance(self.source, SCENARIOS[1])
        with tempfile.TemporaryDirectory() as directory:
            output = write_ground_truth(instance, Path(directory))
            stored = json.loads(output.read_text())
        self.assertEqual(stored["hidden_future_event_ids"], list(instance.hidden_future_event_ids))
        self.assertEqual(
            set(stored["events"][0]),
            {
                "event_id", "transaction_id", "scenario_instance_id", "event_time", "source",
                "event_type", "payload", "generation_origin", "sequence_number",
            },
        )
        self.assertNotIn("scenario_id", stored["events"][0])
        self.assertEqual(
            set(stored["complaints"][0]),
            {"event_id", "transaction_id", "scenario_instance_id", "event_time", "complaint_type", "text", "severity", "generation_origin"},
        )

    def test_complaints_are_repeatable_typed_and_time_safe(self) -> None:
        instances = [generate_scenario_instance(self.source, scenario) for scenario in SCENARIOS]

        self.assertEqual(instances, [generate_scenario_instance(self.source, scenario) for scenario in SCENARIOS])
        self.assertEqual(
            {complaint.complaint_type for instance in instances for complaint in instance.complaints},
            set(ComplaintType),
        )
        self.assertTrue(all(complaint.generation_origin == GENERATED_COMPLAINT for instance in instances for complaint in instance.complaints))
        self.assertTrue(all(complaint.text and complaint.severity.value for instance in instances for complaint in instance.complaints))
        self.assertTrue(all(complaint.event_time <= instance.observation_cutoff for instance in instances for complaint in instance.observed_complaints))
        self.assertTrue(all(complaint.event_time > instance.observation_cutoff for instance in instances for complaint in instance.hidden_future_complaints))
        self.assertTrue(any(instance.observed_complaints for instance in instances))
        self.assertTrue(any(instance.hidden_future_complaints for instance in instances))
