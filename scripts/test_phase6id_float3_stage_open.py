from __future__ import annotations
import hashlib, tempfile, unittest
from pathlib import Path
from phase6id_float3_fixture import run_fixture
ROOT=Path(__file__).resolve().parents[1]; SCRIPTS=ROOT/"scripts"
class Phase6IDTest(unittest.TestCase):
    def test_float3_fixture(self):
        with tempfile.TemporaryDirectory() as temporary: report=run_fixture(Path(temporary)/"fixture",SCRIPTS/"phase6hx_single_log_occlusion_contract.json")
        self.assertEqual(report["status"],"qualified"); self.assertEqual(report["case_count"],[22,22]); self.assertEqual(report["ulp_budget"],0)
    def test_sidecars(self):
        for stem in ("phase6id_stage_open_contract","phase6id_authoring_dependencies"):
            source=SCRIPTS/(stem+".json"); expected=(SCRIPTS/(stem+".sha256")).read_text(encoding="ascii").split()[0].upper(); self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest().upper(),expected)
if __name__=="__main__": unittest.main()
