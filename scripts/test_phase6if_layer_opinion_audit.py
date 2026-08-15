from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase6if_layer_opinion_fixture import run_fixture as run_layer
from phase6if_marker_fixture import run_fixture as run_markers


class Phase6IFLayerOpinionTests(unittest.TestCase):
    def test_layer_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            report=run_layer(Path(directory)/"layer")
            self.assertEqual(report["status"],"qualified",report)

    def test_marker_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            report=run_markers(Path(directory)/"markers")
            self.assertEqual(report["status"],"qualified",report)


if __name__=="__main__":unittest.main()
