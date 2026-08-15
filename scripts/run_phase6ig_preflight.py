from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from phase6ho_app_ready_environment import ROOT,write_json
from phase6ig_camera_opinion_fixture import run_fixture as run_camera
from phase6ig_marker_fixture import run_fixture as run_markers

SCRIPTS=ROOT/"scripts";CONTRACT=SCRIPTS/"phase6ig_camera_opinion_contract.json";SIDECAR=SCRIPTS/"phase6ig_camera_opinion_contract.sha256";MANIFEST=SCRIPTS/"phase6ig_authoring_dependencies.json";MANIFEST_SIDECAR=SCRIPTS/"phase6ig_authoring_dependencies.sha256"
def run(root:Path)->dict:
 if root.exists():raise RuntimeError("Phase 6IG preflight refuses root reuse")
 root.mkdir(parents=True);digest=hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper();side=SIDECAR.read_text(encoding="ascii").split()[0].upper();manifest_digest=hashlib.sha256(MANIFEST.read_bytes()).hexdigest().upper();manifest_side=MANIFEST_SIDECAR.read_text(encoding="ascii").split()[0].upper();policy=json.loads(CONTRACT.read_text(encoding="utf-8"));manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
 dependency=[]
 for row in manifest["modules"]:
  path=ROOT/row["repository_relative_path"];observed=hashlib.sha256(path.read_bytes()).hexdigest().upper() if path.is_file() else None;dependency.append({"module_id":row["module_id"],"path":str(path),"observed_sha256":observed,"expected_sha256":row["sha256"],"passed":observed==row["sha256"]})
 camera=run_camera(root/"camera-fixture");markers=run_markers(root/"marker-fixture")
 accepted=digest==side and manifest_digest==manifest_side==policy["dependency_manifest"]["sha256"] and all(row["passed"] for row in dependency) and camera["status"]=="qualified" and markers["status"]=="qualified"
 report={"schema":"campfire.phase6ig.preflight.v1","phase":"phase6ig","status":"qualified" if accepted else "failed","contract_sha256":digest,"contract_sidecar_match":digest==side,"manifest_sha256":manifest_digest,"manifest_sidecar_match":manifest_digest==manifest_side,"dependency_audit":dependency,"camera_fixture":camera,"marker_fixture":markers,"kit_launch_count":0,"phase6if_reclassified":False,"phase6if_artifact_reused":False,"production_changed":False};write_json(root/"summary.json",report);return report
def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--artifact-root",type=Path,required=True);args=parser.parse_args();return 0 if run(args.artifact_root.absolute())["status"]=="qualified" else 1
if __name__=="__main__":raise SystemExit(main())
