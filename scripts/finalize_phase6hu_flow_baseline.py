"""Finalize the predeclared Phase 6HU human visibility gate without rerunning Kit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase6hs_operation_report import atomic_write_json
from phase6hu_visual_baseline import evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--human-review", choices=("pass", "unclear", "fail"), required=True)
    args = parser.parse_args()
    summary_path = args.artifact_root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "awaiting_human_review":
        raise RuntimeError("Phase 6HU summary is not awaiting human review")
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    visual = evaluate(args.artifact_root, contract, args.human_review)
    summary["visual_evidence"] = visual
    summary["status"] = "qualified" if visual["qualified"] and summary.get("invariants_pass") is True and (summary.get("condition") or {}).get("status") == "qualified" else "safe_stop"
    atomic_write_json(summary_path, summary)
    return 0 if summary["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
