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
  self.assertIn("SpatialScalarColliderIndices",runner)

 def test_phase6es_limits_scalar_collection_without_hiding_velocity(self):
  probe=(ROOT/"scripts/probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
  calibration=(ROOT/"scripts/run_phase6es_calibration.ps1").read_text(encoding="utf-8")
  self.assertIn('channel != "velocity"',probe)
  self.assertIn('if($condition.scenario -eq "production_four"){"2"}else{"1"}',calibration)

 def test_published_safe_stop_is_resource_not_numeric_acceptance(self):
  report=json.loads((ROOT/"docs/devlog/assets/phase6/point_directional_transport_safe_stop.json").read_text(encoding="utf-8"))
  self.assertEqual("safe_stop",report["status"])
  self.assertTrue(report["phase6er_frozen"])
  self.assertFalse(report["formal_contract_frozen"])
  self.assertFalse(report["formal_started"])
  self.assertFalse(report["video_started"])
  self.assertEqual(["kit_private_limit","kit_private_limit"],[item["stop_reason"] for item in report["resource_safe_stop"]["attempts"]])
  self.assertTrue(all(item["process_absent"] for item in report["resource_safe_stop"]["attempts"]))

 def test_full_supply_is_probe_only_and_unresolved(self):
  report=json.loads((ROOT/"docs/devlog/assets/phase6/point_directional_transport_safe_stop.json").read_text(encoding="utf-8"))
  full=report["offline"]["B_full_100"]
  self.assertEqual(1440,full["active_point_count"])
  self.assertEqual(0,full["other_center_inside_count"])
  self.assertEqual(96,full["active_other_support_intersection_count"])
  self.assertEqual("unresolved",report["decision"]["full_1440_supply_safe"])

 def test_offline_contract_persists_every_point_record(self):
  report=json.loads((ROOT/"docs/devlog/assets/phase6/point_directional_transport_safe_stop.json").read_text(encoding="utf-8"))
  metadata=report["offline"]["point_records"]
  self.assertEqual(4*1440,metadata["count"])
  prepare=(ROOT/"scripts/prepare_phase6es_offline.py").read_text(encoding="utf-8")+(ROOT/"scripts/phase6ep_point_collision_geometry.py").read_text(encoding="utf-8")
  for field in ("self_signed_distance_m","other_min_signed_distance_m","self_center_inside","other_center_inside","self_support_intersects","other_support_intersects","enabled_reason","original_fuel","enabled_fuel","original_temperature","enabled_temperature","original_smoke","enabled_smoke"):
   self.assertIn(field,prepare)

 def test_devlog_has_no_phase6es_video_or_latest_demo_change(self):
  html=(ROOT/"docs/devlog/index.html").read_text(encoding="utf-8")
  section=html.split('id="phase-6es"',1)[1].split('id="phase-6er"',1)[0]
  latest=json.loads((ROOT/"docs/devlog/assets/latest_demo.json").read_text(encoding="utf-8"))
  self.assertNotIn("data-video-src",section)
  self.assertNotEqual("phase6es",latest["phase"])

if __name__=="__main__":unittest.main()
