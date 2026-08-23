import unittest

from src.config import database_url
from src.provenance import ALL_PROVENANCE, SOURCE_DATASET


class ProjectTests(unittest.TestCase):
    def test_shared_provenance_and_local_database_configuration(self) -> None:
        self.assertIn(SOURCE_DATASET, ALL_PROVENANCE)
        self.assertEqual(database_url().split(":", 1)[0], "postgresql")
