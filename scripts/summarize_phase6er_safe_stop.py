"""Publish the bounded Phase 6ER safe-stop summary and SVG."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-root", required=True, type=Path)
    parser.add_argument("--calibration-root", required=True, type=Path)
    parser.add_argument("--formal-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--production-app", required=True, type=Path)
    args = parser.parse_args()

    geometry = json.loads((args.geometry_root / "offline_geometry_audit.json").read_text(encoding="utf-8"))
    offline = json.loads((args.geometry_root / "offline_point_classification.json").read_text(encoding="utf-8"))
    calibration = json.loads((args.calibration_root / "scalar_calibration_report.json").read_text(encoding="utf-8"))
    pair_path = args.formal_root / "formal/run_1/lower_upper/strict_all/pair_gate.json"
    pair = json.loads(pair_path.read_text(encoding="utf-8"))
    incrementals = sorted(args.formal_root.glob("formal/run_*/*/*/incremental_gate.json"))
    guards = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((args.formal_root / "runner-logs").glob("*.guard.json"))
    ]

    selected = {}
    for policy, offset in {"strict_all": 0.075, "allow_self_support": 0.025, "allow_self_center": -0.0125}.items():
        row = next(item for item in offline["rows"] if item["policy"] == policy and item["offset_m"] == offset)
        selected[policy] = {
            "offset_m": offset,
            "point_retention": row["point_retention"],
            "weighted_supply": row["weighted_supply"],
            "raw_other_center_inside": row["raw_surface_inside_other_count"],
            "active_other_support_intersections": row["active_other_support_intersection_count"],
            "other_support_intersections_before_filter": row["other_support_intersection_count"],
        }

    old = geometry["legacy_fixture"]
    corrected = geometry["corrected_fixture"]
    old_upper = next(item for item in old["pairs"] if item["pair"] == ["upper_a", "upper_b"])
    corrected_parallel = [
        item for item in corrected["pairs"]
        if item["pair"] in (["lower_a", "lower_b"], ["upper_a", "upper_b"])
    ]
    temperature_deep = next(
        item for item in calibration["on_off_comparisons"]
        if item["source_mode"] == "normal" and item["channel"] == "temperature" and item["band"] == "deep"
    )
    smoke_deep = next(
        item for item in calibration["on_off_comparisons"]
        if item["source_mode"] == "normal" and item["channel"] == "smoke" and item["band"] == "deep"
    )

    report = {
        "schema": "campfire.phase6er.safe-stop.v1",
        "phase": "phase6er",
        "status": "safe_stop",
        "overall_qualified": False,
        "formal_population_accepted": False,
        "phase6eq_frozen": True,
        "phase6eq_reclassified": False,
        "phase6eq_remaining_conditions_restarted": False,
        "geometry": {
            "legacy_fixture": {
                "upper_axis_overlap_m": old_upper["centerline_segment_overlap_m"],
                "minimum_signed_distance_m": old_upper["minimum_signed_distance_m"],
                "other_log_surface_point_centers_inside": old["other_log_point_centers_inside"],
                "geometry_sha256": old["geometry_sha256"],
            },
            "corrected_fixture": {
                "other_log_surface_point_centers_inside": corrected["other_log_point_centers_inside"],
                "volume_overlap_pairs": corrected["sampled_volume_overlap_pair_count"],
                "minimum_signed_distance_m": corrected["minimum_signed_distance_m"],
                "parallel_pair_surface_gaps_m": [item["minimum_signed_distance_m"] for item in corrected_parallel],
                "geometry_sha256": corrected["geometry_sha256"],
            },
            "production_same_defect": False,
            "production_reference": geometry["production_reference"],
            "geometry_tolerance_m": geometry["geometry_tolerance_m"],
        },
        "point_classification": {
            "support_radius_m": 0.05,
            "support_radius_status": "engineering assumption equal to one velocity voxel; exact public Flow radius unavailable",
            "selected": selected,
        },
        "scalar_calibration": {
            "processes": 7,
            "all_normal_exit": calibration["status"] == "complete",
            "emitterless_baseline": calibration["emitterless_baseline"],
            "normal_temperature_deep_sum_ratio": temperature_deep["on_to_off_sum_ratio"],
            "normal_smoke_deep_sum_ratio": smoke_deep["on_to_off_sum_ratio"],
            "temperature_one_is_ambient": False,
            "flow_occupancy_mask_available": False,
        },
        "formal": {
            "contract_sha256": _hash(Path("scripts/phase6er_formal_contract.json")),
            "processes_completed_as_partial_evidence": len(incrementals),
            "processes_expected": 24,
            "accepted_complete_population": 0,
            "failed_condition": "run_1/lower_upper/strict_all pair",
            "failed_gates": pair["failed_gates"],
            "pair_metrics": pair["metrics"],
            "automatic_retry": False,
            "later_condition_started": False,
            "visual_population_started": False,
            "video_generated": False,
        },
        "resource": {
            "runner_peak_bytes": max((guard["peaks"]["runner"] for guard in guards), default=0),
            "diagnostic_peak_bytes": max((guard["peaks"]["diagnostic"] for guard in guards), default=0),
            "kit_peak_bytes": max((guard["peaks"]["kit"] for guard in guards), default=0),
            "tree_peak_bytes": max((guard["peaks"]["tree"] for guard in guards), default=0),
            "all_process_absent": all(guard["process_absent"] for guard in guards),
        },
        "safety": {
            "normal_exit_processes": len(incrementals),
            "fatal": 0,
            "dump": 0,
            "automatic_upload_attempt": 0,
            "device_lost": 0,
            "tdr": 0,
            "residual_process": 0,
        },
        "production": {
            "changed": False,
            "app_sha256": _hash(args.production_app),
            "point_schema_changed": False,
            "flow_setting_changed": False,
            "collision_proxy_geometry_changed": False,
            "defaults_changed": False,
        },
        "regression": {
            "release_build": {"passed": True, "seconds": 8.49},
            "phase0_rtx": {"passed": True, "seconds": 23.3},
            "phase3": {
                "passed": True,
                "seconds": 31.4,
                "dry_mass_balance_error_kg": 0.0,
                "wet_mass_balance_error_kg": 0.0,
                "dry_authority_sha256": "0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10",
                "wet_authority_sha256": "148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9",
                "flow_active_blocks_final": 267,
                "flow_active_blocks_peak": 338,
                "peak_fuel_input": 1.0,
            },
            "focused_contracts": {"passed": 153, "total": 153, "seconds": 32.192},
            "standard_suite": {"processes": 8, "passed": 78, "total": 78, "seconds": 367.4},
            "devlog": {"references": 390, "ids": 246, "json": 198, "svg": 164, "zip": 2},
        },
        "decision": {
            "self_collider_policy_recommended_for_production": False,
            "reason": "corrected geometry improves supply, but the frozen far/opposite scalar transport contract failed and needs a separate control-volume/flux design",
            "next": "design a transport-aware scalar leakage metric that separates blocked deep interior from legitimate around-obstacle transport; do not relax Phase 6ER retroactively",
        },
        "artifact_hashes": {
            "geometry_audit": _hash(args.geometry_root / "offline_geometry_audit.json"),
            "offline_classification": _hash(args.geometry_root / "offline_point_classification.json"),
            "scalar_calibration": _hash(args.calibration_root / "scalar_calibration_report.json"),
            "failed_pair": _hash(pair_path),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    strict = selected["strict_all"]["point_retention"] * 100
    support = selected["allow_self_support"]["point_retention"] * 100
    center = selected["allow_self_center"]["point_retention"] * 100
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="760" viewBox="0 0 1440 760"><style>.t{{font:700 32px system-ui;fill:#f8fafc}}.h{{font:700 22px system-ui;fill:#dbeafe}}.v{{font:700 30px ui-monospace;fill:#67e8f9}}.p{{font:17px system-ui;fill:#cbd5e1}}.w{{fill:#fbbf24}}</style><rect width="100%" height="100%" fill="#07111f"/><text x="55" y="60" class="t">Phase 6ER - corrected four-log geometry / scalar safe stop</text><rect x="45" y="105" width="420" height="250" rx="18" fill="#102238"/><text x="70" y="145" class="h">Legacy fixture defect</text><text x="70" y="195" class="v">0.50 m overlap</text><text x="70" y="235" class="p">upper pair signed distance -0.1014 m</text><text x="70" y="272" class="p">other-log surface Points inside: 480</text><text x="70" y="315" class="p">Production layout does not share this defect.</text><rect x="500" y="105" width="420" height="250" rx="18" fill="#102238"/><text x="525" y="145" class="h">Corrected fixture</text><text x="525" y="195" class="v">0 inside / 0 overlap</text><text x="525" y="235" class="p">parallel-pair surface gap 0.23625 m</text><text x="525" y="272" class="p">crossed layers contact within 1e-6 m</text><text x="525" y="315" class="p">same 4 x 360 Point layout</text><rect x="955" y="105" width="440" height="250" rx="18" fill="#102238"/><text x="980" y="145" class="h">Weighted supply retained</text><text x="980" y="195" class="v">{strict:.2f}% / {support:.2f}%</text><text x="980" y="232" class="v">{center:.2f}%</text><text x="980" y="274" class="p">strict / allow-self-support / center</text><text x="980" y="315" class="p">active other-support intersections: 0</text><rect x="45" y="395" width="1350" height="295" rx="18" fill="#151d2d"/><text x="70" y="440" class="h">Formal safe stop - 4 / 24 normal exits - 0 accepted population</text><text x="70" y="490" class="p">Deep scalar integral passed: temperature ON/OFF 7.00% / smoke 5.32% / deep velocity 0 m/s</text><text x="70" y="535" class="p w">Frozen far/opposite gate failed: temperature opposite 123.2%, far 86.7%; smoke opposite 116.5%</text><text x="70" y="580" class="p">Authored Mesh blocks the deep field, while redirected scalar can exceed OFF inside a small downstream ROI.</text><text x="70" y="625" class="p">No retry / no later conditions / no visual or video / production unchanged</text><text x="70" y="665" class="p">Next: use a control-volume or flux metric to separate penetration from legitimate around-obstacle transport.</text></svg>'''
    args.svg.write_text(svg, encoding="utf-8")
    print("Phase 6ER safe-stop assets written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
