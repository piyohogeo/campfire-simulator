from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from phase6ih_runtime_authoring_isolation_fixture import run_fixture
class Phase6IHTests(unittest.TestCase):
 def test_fixture(self):
  with tempfile.TemporaryDirectory() as directory:self.assertEqual(run_fixture(Path(directory)/"fixture")["status"],"qualified")
if __name__=="__main__":unittest.main()
