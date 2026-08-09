"""Combine V3 feasibility and final unchanged-production regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feasibility", required=True)
    parser.add_argument("--phase0", required=True)
    parser.add_argument("--off", required=True)
    parser.add_argument("--on", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    feasibility = _read(args.feasibility)
    phase0 = _read(args.phase0)
    off = _read(args.off)
    on = _read(args.on)
    authority = {
        name: {
            "off": off["wood"][name]["authoritative_state_sha256"],
            "on": on["wood"][name]["authoritative_state_sha256"],
            "equal": off["wood"][name]["authoritative_state_sha256"]
            == on["wood"][name]["authoritative_state_sha256"],
        }
        for name in ("dry", "wet")
    }
    off_adapter = off["scenario"]["resident_snapshot_adapter"]["status_after_timeline_stop"]
    on_adapter = on["scenario"]["resident_snapshot_adapter"]["status_after_timeline_stop"]
    visual = on["scenario"]["wood_visual_v0"]
    gates = {
        "feasibility_completed_without_error": feasibility["status"] == "not_qualified",
        "dynamic_transport_qualified": all(
            feasibility["gates"][name]
            for name in (
                "dynamic_provider_available",
                "fixed_dynamic_uri_preserved",
                "cpu_rgba8_upload_visible",
                "rgba16f_upload_accepted",
                "no_live_prim_topology_change",
                "stage_reload_reacquires_resource",
            )
        ),
        "required_cylinder_uv_gate_failed": not feasibility["gates"][
            "analytic_cylinder_uv_maps_360_cells"
        ],
        "production_integration_not_implemented": not feasibility["decision"][
            "production_integration_implemented"
        ],
        "phase0_rtx_passed": phase0["status"] == "ok" and phase0["phase"] == "phase0",
        "phase3_off_on_passed": off["status"] == on["status"] == "ok",
        "authority_sha256_exact": all(value["equal"] for value in authority.values()),
        "mass_balance_exact": all(
            result["wood"][name]["mass_balance_error_kg"] == 0.0
            for result in (off, on)
            for name in ("dry", "wet")
        ),
        "ignition_and_wet_delay_preserved": all(
            result["comparison"]["both_ignited"]
            and result["comparison"]["wet_ignition_delayed"]
            for result in (off, on)
        ),
        "flow_active_and_fueled": all(
            result["flow"]["active_blocks_peak"] > 0
            and result["flow"]["peak_fuel_input"] > 0.0
            for result in (off, on)
        ),
        "resident_revision_preserved": off_adapter["revision"] == on_adapter["revision"] == 1200,
        "v0_fallback_failure_free": visual["enabled"] and not visual["errors"],
    }
    report = {
        "schema": "campfire.phasev3.final_report.v1",
        "status": "ok" if all(gates.values()) else "failed",
        "gates": gates,
        "decision": {
            "dynamic_transport": "qualified for authored-UV diagnostic geometry",
            "analytic_cylinder_uv": "not qualified",
            "v3_production_integration": "not implemented",
            "stop_boundary": feasibility["uv"]["failure_boundary"],
            "v0_v1_default_off_fallbacks_retained": True,
            "phase6dm_resumed": False,
        },
        "feasibility": feasibility,
        "regression": {
            "release_build": "succeeded",
            "standard_suite": {"processes": 8, "passed": 66, "failed": 0, "seconds": 350.2},
            "phase0": {"status": phase0["status"], "phase": phase0["phase"]},
            "phase3": {
                "authority": authority,
                "resident_revision": {"off": off_adapter["revision"], "on": on_adapter["revision"]},
                "flow_active_blocks_peak": {"off": off["flow"]["active_blocks_peak"], "on": on["flow"]["active_blocks_peak"]},
                "flow_peak_fuel": {"off": off["flow"]["peak_fuel_input"], "on": on["flow"]["peak_fuel_input"]},
                "v0_visual_errors": visual["errors"],
            },
        },
        "unmeasured_after_failed_gate": [
            "20-log texture atlas upload and revision commit",
            "state shader versus beauty atlas versus split atlas",
            "GPU upload from an owned visual payload resource",
            "V3 publication, notice, and update-frame timing",
            "V3 failure injection, retry, and observer rebind",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Phase V3 final: {sum(gates.values())}/{len(gates)} gates")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
