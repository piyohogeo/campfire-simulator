from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from phase6ho_app_ready_environment import ROOT,write_json
from phase6ih_runtime_authoring_isolation_fixture import run_fixture
from phase6ih_marker_fixture import run_fixture as run_markers
S=ROOT/"scripts";CONTRACT=S/"phase6ih_runtime_authoring_isolation_contract.json";SIDECAR=S/"phase6ih_runtime_authoring_isolation_contract.sha256";MANIFEST=S/"phase6ih_authoring_dependencies.json";MANIFEST_SIDECAR=S/"phase6ih_authoring_dependencies.sha256"
def run(root:Path)->dict:
 if root.exists():raise RuntimeError("Phase 6IH preflight refuses root reuse")
 root.mkdir(parents=True);digest=hashlib.sha256(CONTRACT.read_bytes()).hexdigest().upper();policy=json.loads(CONTRACT.read_text());manifest_digest=hashlib.sha256(MANIFEST.read_bytes()).hexdigest().upper();manifest=json.loads(MANIFEST.read_text());deps=[]
 for row in manifest["modules"]:
  path=ROOT/row["repository_relative_path"];observed=hashlib.sha256(path.read_bytes()).hexdigest().upper() if path.is_file() else None;deps.append({"module_id":row["module_id"],"passed":observed==row["sha256"],"expected_sha256":row["sha256"],"observed_sha256":observed})
 fixture=run_fixture(root/"isolation-fixture");markers=run_markers(root/"marker-fixture");accepted=digest==SIDECAR.read_text().split()[0].upper() and manifest_digest==MANIFEST_SIDECAR.read_text().split()[0].upper()==policy["dependency_manifest"]["sha256"] and all(row["passed"] for row in deps) and fixture["status"]==markers["status"]=="qualified"
 report={"schema":"campfire.phase6ih.preflight.v1","phase":"phase6ih","status":"qualified" if accepted else "failed","contract_sha256":digest,"manifest_sha256":manifest_digest,"dependency_audit":deps,"isolation_fixture":fixture,"marker_fixture":markers,"kit_launch_count":0,"phase6ig_reclassified":False,"phase6ig_artifact_reused":False};write_json(root/"summary.json",report);return report
def main():
 p=argparse.ArgumentParser();p.add_argument("--artifact-root",type=Path,required=True);args=p.parse_args();return 0 if run(args.artifact_root.absolute())["status"]=="qualified" else 1
if __name__=="__main__":raise SystemExit(main())
