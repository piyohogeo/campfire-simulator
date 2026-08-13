"""Aggregate Phase 6FR by reusing the Phase 6FQ lifecycle evidence parser."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyze_phase6fq_stage_close_lifecycle import _attempt, _json, _jsonl


def _ordered(markers: list[str], *names: str) -> bool:
    cursor = -1
    for name in names:
        try:
            cursor = markers.index(name, cursor + 1)
        except ValueError:
            return False
    return True


def build(root: Path, contract_path: Path) -> dict:
    contract = _json(contract_path)
    if not contract:
        raise ValueError("invalid Phase 6FR contract")
    attempts = []
    for path in sorted((root / "attempts").glob("attempt*")):
        if not path.is_dir():
            continue
        row = _attempt(path, contract)
        markers = [str(value.get("marker")) for value in _jsonl(path / "case" / "resource_markers.jsonl")]
        if row["condition"] == "A_release_before_close":
            order_ok = _ordered(
                markers,
                "renderer_drain_complete",
                "flow_references_release_started",
                "provider_readback_references_release_complete",
                "stage_close_request_before",
                "stage_close_request_after",
                "usd_context_disconnected",
            )
        else:
            order_ok = _ordered(
                markers,
                "renderer_drain_complete",
                "stage_close_request_before",
                "stage_close_request_after",
                "usd_context_disconnected",
                "post_close_renderer_update_complete",
                "references_retained_through_post_close",
                "flow_references_release_started",
                "provider_readback_references_release_complete",
            )
        row["shutdown_order_integrity"] = order_ok
        if not order_ok:
            row["failures"].append("shutdown_order_integrity")
            row["classification"] = "nonreplaceable_failure"
        diagnostic_path = path / "case" / "sensitive-shutdown-diagnostics" / "lightweight_shutdown_diagnostic.json"
        diagnostic = _json(diagnostic_path) or {}
        debugger = diagnostic.get("debugger") or {}
        row["diagnostic"].update(
            {
                "diagnostic_order": debugger.get("diagnostic_order"),
                "native_frames_observed": debugger.get("native_frames_observed"),
                "auxiliary_module_pass": (debugger.get("passes") or {}).get("auxiliary_modules"),
                "explicit_detach_pass": (debugger.get("passes") or {}).get("explicit_detach"),
                "raw_stack_log": debugger.get("raw_stack_log"),
            }
        )
        attempts.append(row)
    planned = len(contract["population"]["order"])
    failures = [row for row in attempts if row["classification"] == "nonreplaceable_failure"]
    startup = [row for row in attempts if row["classification"] == "startup_prerequisite_failure"]
    passed = [row for row in attempts if row["classification"] == "representative_pass"]
    by_condition: dict[str, list[dict]] = {}
    for row in attempts:
        by_condition.setdefault(str(row["condition"]), []).append(row)
    return {
        "schema": "campfire.phase6fr.stage-close-native-lifecycle-report.v1",
        "phase": "phase6fr",
        "contract_sha256": (root / "frozen_contract.sha256").read_text(encoding="utf-8").split()[0],
        "phase6fq_reclassified": False,
        "phase6fo_restarted": False,
        "population": {
            "planned": planned,
            "launched": len(attempts),
            "representative_pass": len(passed),
            "startup_prerequisite_failure": len(startup),
            "nonreplaceable_failure": len(failures),
        },
        "qualification_complete": len(passed) == planned and not failures,
        "safe_stop": failures[0] if failures else None,
        "attempts": attempts,
        "conditions": {
            key: {
                "runs": len(rows),
                "passes": sum(row["classification"] == "representative_pass" for row in rows),
                "stage_close_seconds": [row["stage_close_seconds"] for row in rows],
            }
            for key, rows in by_condition.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.root.resolve(), args.contract.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
