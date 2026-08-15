import tempfile
import unittest
from pathlib import Path

from phase6ii_stage_open_composition_fixture import run_fixture


class TestPhase6II(unittest.TestCase):
    def test_producer_consumer_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_fixture(Path(directory) / "fixture")
        self.assertEqual("qualified", result["status"])


if __name__ == "__main__":
    unittest.main()
