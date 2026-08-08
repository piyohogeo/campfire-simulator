"""Summarize Phase 6DE's public profiler and subscriber-surface audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


MARKER_PREFIX = "CampfirePhase6DEFrame"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _members(runtime: dict, surface: str) -> set[str]:
    return set(runtime["surfaces"][surface]["member_names"])


def _flow_specific(name: str) -> bool:
    lowered = name.lower()
    return (
        "flowusd" in lowered
        or "omni.flowusd" in lowered
        or lowered.startswith("flow ")
    )


def _matching_names(names: set[str], *terms: str) -> list[str]:
    return sorted(
        name for name in names if any(term.lower() in name.lower() for term in terms)
    )


def _render_svg(report: dict) -> str:
    surface = report["surface_result"]
    rows = (
        ("Generic completed-frame profile snapshot", True, "public IProfileMonitor"),
        ("FlowUsd StageUpdate node", True, "enabled · order 1000"),
        ("Named USD / Fabric / Hydra / PhysX zones", True, "observed in live run"),
        ("Direct omni.flowusd ingest timer", False, "not exposed"),
        ("Registered Tf subscriber enumeration", False, "not exposed"),
        ("Flow-specific named profiler zone", False, "not observed"),
    )
    row_svg = []
    for index, (label, available, detail) in enumerate(rows):
        y = 242 + index * 55
        color = "#86efac" if available else "#fbbf24"
        verdict = "YES" if available else "NO"
        row_svg.append(
            f'<text x="86" y="{y}" class="label">{label}</text>'
            f'<rect x="710" y="{y - 25}" width="86" height="34" rx="17" fill="{color}" opacity="0.18"/>'
            f'<text x="753" y="{y}" class="verdict" fill="{color}">{verdict}</text>'
            f'<text x="830" y="{y}" class="detail">{detail}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DE public profiler and subscriber boundary</title><desc id="desc">The fixed Flow build exposes generic completed-frame profile snapshots and several named USD pipeline zones, but no direct FlowUsd ingest timer, subscriber enumeration, or Flow-specific profiler zone.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#102a43"/><stop offset="1" stop-color="#30203c"/></linearGradient></defs><style>.k{{font:700 17px 'Segoe UI',sans-serif;fill:#93c5fd;letter-spacing:2px}}.title{{font:750 35px 'Segoe UI',sans-serif;fill:#f8fafc}}.sub{{font:16px 'Segoe UI',sans-serif;fill:#cbd5e1}}.label{{font:650 17px 'Segoe UI',sans-serif;fill:#e2e8f0}}.verdict{{font:750 16px 'Segoe UI',sans-serif;text-anchor:middle}}.detail{{font:15px 'Segoe UI',sans-serif;fill:#cbd5e1}}.good{{font:750 21px 'Segoe UI',sans-serif;fill:#86efac}}.warn{{font:650 16px 'Segoe UI',sans-serif;fill:#fbbf24}}.note{{font:14px 'Segoe UI',sans-serif;fill:#94a3b8}}</style>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="61" class="k">PHASE 6DE · PROFILER / SUBSCRIBER SURFACE</text><text x="64" y="111" class="title">Named zones are visible; Flow ingest still is not isolated</text><text x="64" y="150" class="sub">Flow 110.0.0 · live Resident Point run · temporary capture mask restored · production unchanged</text>
<rect x="56" y="186" width="1088" height="358" rx="20" fill="#0b2032"/>{''.join(row_svg)}
<text x="64" y="584" class="good">{report['gates_passed']} / {report['gate_count']} gates · {surface['live_profile_record_count']} correlated updates · active blocks {surface['active_blocks_min']}–{surface['active_blocks_max']}</text>
<text x="64" y="618" class="warn">Capture inflated update time to seconds; recorded durations and nested-zone sums are excluded from performance acceptance.</text>
<text x="64" y="650" class="note">Next: derived default-off enablement controls, measured without profiler capture, before assigning Phase 6DD residual cost to a consumer.</text></svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--monitor", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()

    runtime = _read(args.runtime)
    monitor = _read(args.monitor)
    profile = _read(args.profile)
    base = _read(args.base)
    manifest = _read(args.manifest)
    records = profile["records"]
    names = set(profile["observed_selected_zone_names"])
    sidecar = base["lifecycle"]["owner"]["session"]["sidecar"]
    stage_nodes = runtime["stage_update"]["nodes"]
    flow_nodes = [node for node in stage_nodes if node["name"] == "FlowUsd"]
    monitor_members = _members(runtime, "carb_profile_monitor_interface")
    flow_public_candidates = runtime["surfaces"]["flowusd_public_module"][
        "timing_or_subscription_candidates"
    ]
    flow_internal_candidates = runtime["surfaces"]["flowusd_internal_interface"][
        "timing_or_subscription_candidates"
    ]
    tf_members = _members(runtime, "tf_notice")
    custom_events = monitor["capture"]["custom_events"]
    changed = [
        record
        for record in records
        if record["layout_changed"] and record["translation_triggered_before_frame"]
    ]
    unchanged = [record for record in records if not record["layout_changed"]]
    flow_names = sorted(name for name in names if _flow_specific(name))
    zone_groups = {
        "usd_notice_or_pending": _matching_names(names, "UsdNotice", "pendingUsd"),
        "fabric": _matching_names(names, "Fabric"),
        "hydra": _matching_names(names, "Hydra"),
        "physx": _matching_names(names, "PhysX"),
        "stage_update": _matching_names(names, "StageUpdate"),
        "flow_specific": flow_names,
    }
    masks_restored = (
        runtime["profiler"]["capture_mask_before"]
        == runtime["profiler"]["capture_mask_after"]
        == 0
        and monitor["capture"]["capture_mask_before"]
        == monitor["capture"]["capture_mask_restored"]
        == 0
        and profile["capture"]["capture_mask_before"]
        == profile["capture"]["capture_mask_restored"]
        == 0
    )
    gates = {
        "runtime_surface_probe_ok": runtime["status"] == "ok",
        "profile_monitor_calibration_ok": monitor["status"] == "ok",
        "live_profile_probe_ok": profile["status"] == "ok",
        "generic_profile_snapshot_public": {
            "get_last_profile_events",
            "mark_frame_end",
        } <= monitor_members,
        "flow_public_direct_timer_absent": not flow_public_candidates,
        "flow_internal_direct_timer_absent": not flow_internal_candidates,
        "tf_subscriber_enumeration_absent": not any(
            "enumer" in name.lower() or "subscriber" in name.lower()
            for name in tf_members
        ),
        "flow_stage_node_enabled_at_1000": len(flow_nodes) == 1
        and flow_nodes[0]["enabled"]
        and flow_nodes[0]["order"] == 1000,
        "custom_zone_round_trip_observed": len(custom_events) >= 2
        and all(float(event["duration"]) > 0 for event in custom_events),
        "temporary_capture_masks_restored": masks_restored,
        "live_profile_records_captured": len(records) >= 4,
        "changed_and_unchanged_updates_captured": bool(changed)
        and len(unchanged) >= 2,
        "markers_correlate_each_update": all(
            any(
                event["name"].startswith(
                    f"{MARKER_PREFIX}.before_r{record['revision_before']}"
                )
                for event in record["profile"]["marker_events"]
            )
            for record in records
        ),
        "usd_change_zones_observed": bool(zone_groups["usd_notice_or_pending"]),
        "fabric_hydra_physx_zones_observed": all(
            zone_groups[group] for group in ("fabric", "hydra", "physx")
        ),
        "no_flow_specific_named_zone_observed": not flow_names,
        "flow_simulation_was_active": max(
            record["active_blocks"] for record in records
        ) > 0,
        "resident_publication_contract_held": sidecar["prepare_count"]
        == sidecar["publish_count"]
        == 760
        and sidecar["failure_count"] == 0
        and not base["publication"]["point_resyncs"]
        and not base["publication"]["unexpected_point_changes"],
        "production_app_unchanged": not manifest["production_changed"]
        and manifest["production_app_sha256_before"]
        == manifest["production_app_sha256_after"],
    }
    if not all(gates.values()):
        raise RuntimeError(f"Phase 6DE gates failed: {gates}")

    report = {
        "phase": "phase6de",
        "status": "ok",
        "scope": "public profiler and subscriber-surface availability audit",
        "surface_result": {
            "kit_version": runtime["runtime"]["kit_version"],
            "app_name": runtime["runtime"]["app_name"],
            "stage_update_nodes": stage_nodes,
            "profile_monitor_methods": sorted(monitor_members),
            "flow_public_timing_candidates": flow_public_candidates,
            "flow_internal_timing_candidates": flow_internal_candidates,
            "tf_notice_methods": sorted(tf_members),
            "live_profile_record_count": len(records),
            "layout_changed_after_trigger_record_count": len(changed),
            "unchanged_record_count": len(unchanged),
            "active_blocks_min": min(record["active_blocks"] for record in records),
            "active_blocks_max": max(record["active_blocks"] for record in records),
            "observed_zone_groups": zone_groups,
            "flow_specific_zone_observed": False,
            "direct_flow_ingest_timer_available": False,
            "registered_subscriber_enumeration_available": False,
        },
        "calibration": {
            "custom_zone_name": monitor["capture"]["custom_zone_name"],
            "custom_event_count": len(custom_events),
            "custom_events": custom_events,
            "capture_mask_before": 0,
            "capture_mask_during": monitor["capture"]["capture_mask_during"],
            "capture_mask_restored": monitor["capture"]["capture_mask_restored"],
            "duration_is_performance_evidence": False,
        },
        "interpretation": {
            "qualified": (
                "The fixed Kit build can return completed-frame generic profiler "
                "events and exposes named USD, Fabric, Hydra, and PhysX zones while "
                "Flow is active. The FlowUsd StageUpdate node is identifiable."
            ),
            "not_qualified": (
                "No direct omni.flowusd ingest timer, Flow-specific named zone, or "
                "registered Tf subscriber enumeration was exposed. Workflow* names "
                "are not Flow zones. Profiler capture inflated updates to seconds, "
                "and nested zone durations must not be summed or used for acceptance."
            ),
            "phase6dd_effect": (
                "Phase 6DD's ChangeBlock-exit residual still cannot be assigned to "
                "Flow ingestion or to any single subscriber."
            ),
            "next": (
                "Use a default-off derived run to vary consumer enablement one item "
                "at a time. Measure publication and update timing with profiler capture "
                "disabled, then use the profiler only to confirm which boundary ran."
            ),
        },
        "gates": gates,
        "gates_passed": sum(gates.values()),
        "gate_count": len(gates),
        "production_app": {
            "sha256_before": manifest["production_app_sha256_before"],
            "sha256_after": manifest["production_app_sha256_after"],
            "changed_during_run": manifest["production_changed"],
        },
        "base_harness": {
            "status": base["status"],
            "inherited_flow_kit_exit_code": manifest["flow_kit_exit_code"],
            "known_reason": (
                "historical Phase 6CO static/STOP expectations conflict with the "
                "current default-off dynamic translation qualification"
            ),
        },
        "contracts": {
            "production_default": "OFF",
            "production_sphere_emitter_changed": False,
            "physics_changed": False,
            "json_schema_changed": False,
            "serialization_changed": False,
            "usd_save_changed": False,
            "rollback_changed": False,
            "revision_changed": False,
            "immutable_snapshot_changed": False,
            "flow_version": "110.0.0",
        },
        "video": {
            "reused": "resident_translation_breakdown.mp4",
            "reason": "same deterministic default-off Resident translation scenario",
            "success_criterion": "not video-only",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.svg.write_text(_render_svg(report), encoding="utf-8")
    print(f"Phase 6DE: {sum(gates.values())}/{len(gates)} gates passed")


if __name__ == "__main__":
    main()
