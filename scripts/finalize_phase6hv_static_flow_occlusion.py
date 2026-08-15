"""Apply the independent human image gate to a completed Phase 6HV root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase6ho_app_ready_environment import write_json
from phase6hv_visual_occlusion import build_media, evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--human-review", choices=("pass", "unclear", "fail"), required=True)
    args = parser.parse_args()
    root = args.artifact_root.absolute()
    summary_path = root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("phase") != "phase6hv" or summary.get("status") not in ("awaiting_human_review", "safe_stop"):
        raise RuntimeError("Phase 6HV summary is not eligible for human finalization")
    if summary.get("status") == "safe_stop" and not (summary.get("visual_evidence") or {}).get("automated_pass"):
        raise RuntimeError("Phase 6HV automated gate did not pass")
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    visual = evaluate(root, contract, args.human_review)
    build_media(root, contract, visual, root / "comparison.png", root / "difference.png")
    summary["visual_evidence"] = visual
    summary["status"] = "qualified" if visual["qualified"] and summary.get("stage_difference", {}).get("passed") and summary.get("invariants_pass") else "safe_stop"
    summary["qualified_scope"] = contract["scope_if_pass"] if summary["status"] == "qualified" else None
    write_json(summary_path, summary)
    return 0 if summary["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
