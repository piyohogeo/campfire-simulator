"""Phase 6GK startup-only replacement and accepted-preflight classifier."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from phase6gh_startup_replacement_policy import classify_attempt as classify_phase6gh


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def classify(raw: dict, runner: dict, guard: dict, preflight: dict | None) -> dict:
    base = classify_phase6gh(raw, runner, guard, preflight)
    if base["classification"] == "accepted_normal_sample":
        valid = bool(preflight and preflight.get("status") == "pass"
                     and (preflight.get("validation") or {}).get("pass") is True
                     and preflight.get("public_readback_calls") == 1
                     and preflight.get("weak_reference_alive_after_release_count") == 0
                     and preflight.get("ownership_container_residual_count") == 0)
        if not valid:
            base.update(classification="operation_failure", replacement_eligible=False,
                        reasons=["qualified_preflight_integrity"])
    base["schema"] = "campfire.phase6gk.preflight-attempt-classification.v1"
    return base


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--guard", type=Path, required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = classify(load(args.raw), load(args.runner), load(args.guard),
                      load(args.preflight) if args.preflight and args.preflight.is_file() else None)
    write(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
