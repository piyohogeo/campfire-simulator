"""Combine the isolated material probe and paired Phase 3 V0 measurements."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite_non_negative(value) -> bool:
    return math.isfinite(float(value)) and float(value) >= 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--off", type=Path, required=True)
    parser.add_argument("--on", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    probe = _read(args.probe)
    off = _read(args.off)
    on = _read(args.on)
    off_visual = off["scenario"]["wood_visual_v0"]
    on_visual = on["scenario"]["wood_visual_v0"]

    authority_equal = {
        name: (
            off["wood"][name]["authoritative_state_sha256"]
            == on["wood"][name]["authoritative_state_sha256"]
        )
        for name in ("dry", "wet")
    }
    gates = {
        "isolated_probe_all_passed": (
            probe["status"] == "ok" and all(probe["gates"].values())
        ),
        "feature_off_is_inert": (
            not off_visual["enabled"]
            and off_visual["status_after_timeline_stop"] is None
            and off_visual["publication_timing"] is None
            and off_visual["usd_set_count"] == 0
        ),
        "authority_exact_off_on": all(authority_equal.values()),
        "mass_balance_preserved": all(
            result["wood"][name]["mass_balance_error_kg"] == 0.0
            for result in (off, on)
            for name in ("dry", "wet")
        ),
        "resident_revision_preserved": all(
            result["scenario"]["resident_snapshot_adapter"]
            ["status_after_timeline_stop"]["revision"]
            == 1200
            for result in (off, on)
        ),
        "visual_revision_committed": (
            on_visual["enabled"]
            and on_visual["status_after_timeline_stop"]["revision"] == 1200
            and on_visual["status_after_timeline_stop"]["publish_count"] == 240
        ),
        "visual_failure_free": (
            on_visual["status_after_timeline_stop"]["failure_count"] == 0
            and on_visual["status_after_timeline_stop"]["recovery_count"] == 0
            and not on_visual["errors"]
        ),
        "flow_active_off_on": (
            off["flow"]["active_blocks_peak"] > 0
            and on["flow"]["active_blocks_peak"] > 0
            and off["flow"]["peak_fuel_input"] > 0.0
            and on["flow"]["peak_fuel_input"] > 0.0
        ),
        "ignition_contract_preserved": all(
            result["comparison"]["both_ignited"]
            and result["comparison"]["wet_ignition_delayed"]
            for result in (off, on)
        ),
        "timings_finite": all(
            _finite_non_negative(value)
            for value in (
                off["timing"]["segments"]["kit_flow_render_update"]["p95_ms"],
                on["timing"]["segments"]["kit_flow_render_update"]["p95_ms"],
                on_visual["publication_timing"]["p95_ms"],
            )
        ),
    }

    report = {
        "schema": "campfire.phasev0.wood_visual_report.v1",
        "status": "ok" if all(gates.values()) else "failed",
        "safe_start": {
            "phase": "Phase 6DM",
            "commit": "57fe3bc",
            "production_layout_integration": "not modified by Phase V0",
        },
        "scope": {
            "implemented": "Phase V0 per-log material only",
            "feature_default": "off",
            "input": "ResidentPublishedSnapshot",
            "v1_v2_v3_implemented": False,
        },
        "kit_flow_version": probe["kit_flow_version"],
        "material_selection": probe["selection"],
        "gates": gates,
        "isolated_four_log_probe": {
            "gate_count": len(probe["gates"]),
            "gate_pass_count": sum(bool(value) for value in probe["gates"].values()),
            "uniforms": probe["uniforms"],
            "publication": probe["publication"],
            "frame_timing": probe["frame_timing"],
        },
        "production_two_log_off_on": {
            "authority_sha256_equal": authority_equal,
            "flow_active_blocks_peak": {
                "off": off["flow"]["active_blocks_peak"],
                "on": on["flow"]["active_blocks_peak"],
            },
            "resident_revision": {
                "off": off["scenario"]["resident_snapshot_adapter"]
                ["status_after_timeline_stop"]["revision"],
                "on": on["scenario"]["resident_snapshot_adapter"]
                ["status_after_timeline_stop"]["revision"],
            },
            "visual": on_visual,
            "update_frame_p95_ms": {
                "off": off["timing"]["segments"]["kit_flow_render_update"][
                    "p95_ms"
                ],
                "on": on["timing"]["segments"]["kit_flow_render_update"][
                    "p95_ms"
                ],
                "interpretation": "sequential single runs; no speedup claim",
            },
        },
        "limitations": [
            "uniform state per log; no local hot spots or composition bands",
            "four-log all-fields-changing p95 exceeds the 20-log 1 ms reference budget",
            "diagnostic video uses fixed synthetic snapshots, not a combustion trajectory",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Phase V0 combined report: {sum(gates.values())}/{len(gates)} gates")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
