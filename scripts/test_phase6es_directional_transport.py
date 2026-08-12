from __future__ import annotations
import json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import numpy as np
from phase6es_directional_transport import face_transport

class Phase6EsDirectionalTransport(unittest.TestCase):
 def test_uniform_upward_fixture_has_expected_signs(self):
  coords=np.arange(-.45,.451,.025)
  local=np.asarray([[x,y,z] for x in coords for y in coords[::4] for z in coords[::4]])
  velocity=np.zeros_like(local);velocity[:,2]=2.0
  scalar=np.ones(len(local));faces=face_transport(local,velocity,scalar,np.asarray([.025]*3),.05)
  self.assertGreater(faces["opposite_top"]["outward_transport_proxy"],0)
  self.assertGreater(faces["inlet_bottom"]["inward_transport_proxy"],0)
  self.assertEqual(0,faces["opposite_top"]["inward_transport_proxy"])
  self.assertEqual(0,faces["inlet_bottom"]["outward_transport_proxy"])
  for name in ("side_left","side_right","end_left","end_right"):
   self.assertEqual(0,faces[name]["outward_transport_proxy"])

 def test_calibration_contract_is_local_and_frozen(self):
  data=json.loads((ROOT/"scripts/phase6es_calibration_contract.json").read_text(encoding="utf-8"))
  self.assertTrue(data["declared_before_runtime"])
  self.assertEqual("blocker log local frame",data["control_volume"]["coordinate_system"])
  self.assertEqual(.05,data["control_volume"]["plane_offset_from_mesh_m"])
  self.assertIn("no overwrite",data["phase6er_policy"])

 def test_shared_defaults_remain_backward_compatible(self):
  runner=(ROOT/"scripts/run_phase6ep_point_collision_case.ps1").read_text(encoding="utf-8")
  self.assertIn('[string]$ReportPhase = "phase6ep"',runner)
  self.assertIn('[string]$Policy = "strict_all"',runner)
  self.assertIn("allow_other_support",runner)

if __name__=="__main__":unittest.main()
