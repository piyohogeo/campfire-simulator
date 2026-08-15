from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from phase6ig_camera_opinion_fixture import run_fixture as run_camera
from phase6ig_marker_fixture import run_fixture as run_markers

class Phase6IGTests(unittest.TestCase):
 def test_camera_fixture(self):
  with tempfile.TemporaryDirectory() as directory:self.assertEqual(run_camera(Path(directory)/"camera")["status"],"qualified")
 def test_marker_fixture(self):
  with tempfile.TemporaryDirectory() as directory:self.assertEqual(run_markers(Path(directory)/"markers")["status"],"qualified")
if __name__=="__main__":unittest.main()
