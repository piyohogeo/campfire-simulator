"""Combine V3M-B Mesh, PhysX/Flow, and Resident-native evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


POSITION_TOLERANCE_M = 0.02
ORIENTATION_TOLERANCE_RAD = 0.05
COUNT_RELATIVE_TOLERANCE = 0.10


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _distance(left, right):
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))


def _quat(path):
    text = Path(path).read_text(encoding="utf-8")
    match = re.search(
        r'def (?:Cylinder|Xform) "Log_04".*?quatf xformOp:orient = \(([^)]+)\)',
        text,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"Log_04 orientation is unavailable: {path}")
    values = tuple(float(value.strip()) for value in match.group(1).split(","))
    if len(values) != 4:
        raise ValueError("Unexpected quaternion cardinality")
    return values


def _quat_angle(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return 2.0 * math.acos(min(1.0, abs(dot / norm)))


def _relative_difference(left, right):
    return abs(float(left) - float(right)) / max(abs(float(left)), 1.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--phase2-off", required=True)
    parser.add_argument("--phase2-on", required=True)
    parser.add_argument("--phase3-off", required=True)
    parser.add_argument("--phase3-on", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    mesh = _read(args.mesh)
    phase2_off = _read(args.phase2_off)
    phase2_on = _read(args.phase2_on)
    phase3_off = _read(args.phase3_off)
    phase3_on = _read(args.phase3_on)

    position_error = _distance(
        phase2_off["rigid_body"]["final_position_m"],
        phase2_on["rigid_body"]["final_position_m"],
    )
    off_stage = phase2_off["final_stage"]
    on_stage = phase2_on["final_stage"]
    orientation_error = _quat_angle(_quat(off_stage), _quat(on_stage))
    contact_event_difference = _relative_difference(
        phase2_off["rigid_body"]["contact_report_events"],
        phase2_on["rigid_body"]["contact_report_events"],
    )
    contact_point_difference = _relative_difference(
        phase2_off["rigid_body"]["contact_points"],
        phase2_on["rigid_body"]["contact_points"],
    )
    active_block_difference = _relative_difference(
        phase2_off["flow"]["active_blocks_peak"],
        phase2_on["flow"]["active_blocks_peak"],
    )
    resident_off = phase3_off["scenario"]["resident_snapshot_adapter"]
    resident_on = phase3_on["scenario"]["resident_snapshot_adapter"]
    gates = {
        "mesh_probe_qualified": mesh["status"] == "qualified"
        and all(mesh["gates"].values()),
        "default_off_preserved": not phase2_off["wood_render_hierarchy_enabled"]
        and not phase3_off["scenario"]["wood_render_hierarchy_enabled"],
        "phase2_hierarchy_opt_in": phase2_on["wood_render_hierarchy_enabled"],
        "drop_and_settle_preserved": all(
            report["rigid_body"][name]
            for report in (phase2_off, phase2_on)
            for name in ("settled", "inside_stone_ring", "resting_above_ground")
        ),
        "final_position_within_2cm": position_error <= POSITION_TOLERANCE_M,
        "final_orientation_within_0_05rad": orientation_error
        <= ORIENTATION_TOLERANCE_RAD,
        "contact_reports_preserved": min(
            phase2_off["rigid_body"]["contact_report_events"],
            phase2_on["rigid_body"]["contact_report_events"],
            phase2_off["rigid_body"]["contact_points"],
            phase2_on["rigid_body"]["contact_points"],
        )
        > 0
        and max(contact_event_difference, contact_point_difference)
        <= COUNT_RELATIVE_TOLERANCE,
        "flow_source_and_blocks_preserved": phase2_off["emitter_follow"]["followed"]
        and phase2_on["emitter_follow"]["followed"]
        and min(
            phase2_off["flow"]["active_blocks_peak"],
            phase2_on["flow"]["active_blocks_peak"],
        )
        > 0
        and active_block_difference <= COUNT_RELATIVE_TOLERANCE,
        "authority_sha256_exact": all(
            phase3_off["wood"][name]["authoritative_state_sha256"]
            == phase3_on["wood"][name]["authoritative_state_sha256"]
            for name in ("dry", "wet")
        ),
        "mass_balance_and_ignition_exact": all(
            phase3_off["wood"][name][field] == phase3_on["wood"][name][field]
            for name in ("dry", "wet")
            for field in ("mass_balance_error_kg", "ignition_seconds")
        )
        and phase3_off["comparison"] == phase3_on["comparison"],
        "flow_fuel_exact_and_blocks_preserved": all(
            phase3_off["flow"][field] == phase3_on["flow"][field]
            for field in ("input_owner", "peak_fuel_input")
        )
        and min(
            phase3_off["flow"]["active_blocks_final"],
            phase3_on["flow"]["active_blocks_final"],
        )
        > 0
        and _relative_difference(
            phase3_off["flow"]["active_blocks_final"],
            phase3_on["flow"]["active_blocks_final"],
        )
        <= COUNT_RELATIVE_TOLERANCE,
        "resident_revision_exact": resident_off["status_after_timeline_stop"]["revision"]
        == resident_on["status_after_timeline_stop"]["revision"]
        == 1200
        and resident_off["final_usd_state"] == resident_on["final_usd_state"],
        "support_decision_exact": all(
            resident_off["final_usd_state"]["logs"][log_id]["weakest_support_ratio"]
            == resident_on["final_usd_state"]["logs"][log_id]["weakest_support_ratio"]
            for log_id in ("Log_00", "Log_01")
        ),
    }
    report = {
        "schema": "campfire.phasev3mb.final_report.v1",
        "status": "qualified" if all(gates.values()) else "not_qualified",
        "tolerances_defined_before_final_evaluation": {
            "position_m": POSITION_TOLERANCE_M,
            "orientation_rad": ORIENTATION_TOLERANCE_RAD,
            "contact_and_flow_count_relative": COUNT_RELATIVE_TOLERANCE,
        },
        "gates": gates,
        "mesh": mesh,
        "physics_equivalence": {
            "final_position_error_m": position_error,
            "final_orientation_error_rad": orientation_error,
            "contact_event_relative_difference": contact_event_difference,
            "contact_point_relative_difference": contact_point_difference,
            "flow_active_block_relative_difference": active_block_difference,
            "off": phase2_off,
            "on": phase2_on,
        },
        "resident_equivalence": {
            "authority_sha256": {
                mode: {
                    name: report["wood"][name]["authoritative_state_sha256"]
                    for name in ("dry", "wet")
                }
                for mode, report in (("off", phase3_off), ("on", phase3_on))
            },
            "revision": {
                "off": resident_off["status_after_timeline_stop"]["revision"],
                "on": resident_on["status_after_timeline_stop"]["revision"],
            },
            "ignition_seconds": {
                mode: {name: report["wood"][name]["ignition_seconds"] for name in ("dry", "wet")}
                for mode, report in (("off", phase3_off), ("on", phase3_on))
            },
            "mass_balance_error_kg": {
                mode: {name: report["wood"][name]["mass_balance_error_kg"] for name in ("dry", "wet")}
                for mode, report in (("off", phase3_off), ("on", phase3_on))
            },
            "flow": {"off": phase3_off["flow"], "on": phase3_on["flow"]},
            "support": {
                mode: {
                    log_id: resident["final_usd_state"]["logs"][log_id]["weakest_support_ratio"]
                    for log_id in ("Log_00", "Log_01")
                }
                for mode, resident in (("off", resident_off), ("on", resident_on))
            },
        },
        "decision": {
            "phasev3mb_qualified": all(gates.values()),
            "phasev3mc_may_start": all(gates.values()),
            "production_default_changed": False,
            "mesh_collider_used": False,
            "points_deformed": False,
            "phase6dm_resumed": False,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Phase V3M-B final: {sum(gates.values())}/{len(gates)} gates")
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
