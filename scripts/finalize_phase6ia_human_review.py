"""Bind a bounded human visual verdict to immutable Phase 6IA runtime evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6ho_app_ready_environment import write_json
from phase6hw_temporal_occlusion import evaluate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts/phase6hx_single_log_occlusion_contract.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--verdict", choices=("pass", "unclear", "fail"), required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    original = json.loads((root / "temporal_evidence.json").read_text(encoding="utf-8"))
    if summary.get("status") != "awaiting_human_review" or original.get("human_review") != "pending":
        raise RuntimeError("Phase 6IA is not awaiting one human review")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    reviewed, _ = evaluate(root, policy, args.verdict)
    for key in ("conditions", "ratios", "background_absolute_difference", "automated_gates", "automated_pass"):
        if reviewed[key] != original[key]:
            raise RuntimeError("Phase 6IA recomputed evidence mismatch:" + key)
    qualified = reviewed["qualified"] and summary.get("invariants_pass") is True and all(item.get("status") == "qualified" for item in summary["conditions"].values())
    report = {
        "schema":"campfire.phase6ia.human-review.v1","phase":"phase6ia","status":"qualified" if qualified else "safe_stop_visual_or_metric_ambiguity",
        "verdict":args.verdict,"reason":args.reason,"automated_pass":reviewed["automated_pass"],"all_runtime_conditions_qualified":all(item.get("status") == "qualified" for item in summary["conditions"].values()),
        "invariants_pass":summary.get("invariants_pass"),"frozen_probe_contract_sha256":sha(CONTRACT),"runtime_summary_sha256_before_review":sha(root / "summary.json"),
        "thresholds_or_rois_changed":False,"runtime_or_past_artifact_reused":False,
    }
    write_json(root / "human_review.json", report)
    final = {**summary, "status":report["status"], "human_review":report, "qualification_scope": "single axis-aligned diagnostic log static Mesh CollisionProxy visual signature only" if qualified else None}
    write_json(root / "final_summary.json", final)
    return 0 if qualified else 1


if __name__ == "__main__":
    raise SystemExit(main())

