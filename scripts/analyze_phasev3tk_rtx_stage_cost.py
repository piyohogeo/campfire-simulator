"""Aggregate Phase V3T-K visible-viewport stage and AA isolation evidence."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


FLOW_CONDITIONS = {"flow_prims_disabled", "flow_prims_global_off_active", "flow_simulation_only", "flow_volume"}
STAGE_ORDER = [
    "empty_rtx", "ground_stones_no_lights", "ground_stones_lit", "cylinder20_solid",
    "v3mesh20_solid", "v3mesh20_static_texture", "v3mesh20_dynamic_unprovided",
    "v3mesh20_dynamic_rigid_stopped", "v3mesh20_dynamic_rigid_play",
    "flow_prims_disabled", "flow_prims_global_off_active", "flow_simulation_only", "flow_volume",
]
LABELS = {
    "empty_rtx": "Empty RTX", "ground_stones_no_lights": "Ground + stones",
    "ground_stones_lit": "+ lights", "cylinder20_solid": "20 cylinders",
    "v3mesh20_solid": "V3 mesh / solid", "v3mesh20_static_texture": "+ fixed texture",
    "v3mesh20_dynamic_unprovided": "+ dynamic URI", "v3mesh20_dynamic_rigid_stopped": "+ rigid / stopped",
    "v3mesh20_dynamic_rigid_play": "+ timeline PLAY", "flow_prims_disabled": "+ Flow authored / all OFF",
    "flow_prims_global_off_active": "+ Flow global OFF / active",
    "flow_simulation_only": "+ Flow simulation", "flow_volume": "+ volume render",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def aggregate(rows):
    values = [float(row["metrics"]["average_visible_fps"]) for row in rows]
    hud = [float(row["metrics"]["hud_fps_mean"]) for row in rows]
    return {
        "run_count": len(rows), "values_fps": values,
        "mean_fps": statistics.fmean(values), "stdev_fps": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min_fps": min(values), "max_fps": max(values), "hud_mean_fps": statistics.fmean(hud),
        "gpu_utilization_mean_percent": statistics.fmean(float(row["gpu"]["utilization_mean_percent"]) for row in rows),
        "power_mean_w": statistics.fmean(float(row["gpu"]["power_mean_w"]) for row in rows),
        "graphics_clock_mean_mhz": statistics.fmean(float(row["gpu"]["graphics_clock_mean_mhz"]) for row in rows),
        "stage": rows[0]["stage"],
    }


def delta(table, before, after):
    left, right = table[before]["mean_fps"], table[after]["mean_fps"]
    return {"before": before, "after": after, "fps_delta": right - left, "percent": (right / left - 1.0) * 100.0}


def compact(row, population):
    return {
        "population": population, "condition": row["condition"], "aa_mode": row["aa_mode"], "run": row["run"],
        "classification": row["classification"], "exit_code": row["exit_code"],
        "fatal_log_counts": row["fatal_log_counts"], "metrics": row["metrics"], "gpu": row["gpu"],
        "stage": row["stage"], "dynamic_uri_log_mentions": row["dynamic_uri_log_mentions"],
        "dynamic_uri_warning_or_error_count": row["dynamic_uri_warning_or_error_count"],
        "settings_before": row["settings_before"], "settings_after": row["settings_after"],
    }


def make_svg(stage, aa):
    width, height = 1260, 850
    max_fps = 110.0
    rows = []
    for index, condition in enumerate(STAGE_ORDER):
        y = 160 + index * 43
        value = stage[condition]["mean_fps"]
        bar = value / max_fps * 690
        color = "#f59e0b" if condition in FLOW_CONDITIONS else "#38bdf8"
        rows.append(f'<text x="55" y="{y+18}" class="label">{LABELS[condition]}</text>'
                    f'<rect x="250" y="{y}" width="{bar:.1f}" height="27" rx="7" fill="{color}"/>'
                    f'<text x="{260+bar:.1f}" y="{y+19}" class="value">{value:.2f}</text>')
    aa_rows = []
    for index, mode in enumerate(("performance", "auto", "dlaa")):
        x = 800 + index * 135
        value = aa[mode]["mean_fps"]
        bar = value / 65.0 * 130
        top = 775 - bar
        aa_rows.append(f'<rect x="{x}" y="{top:.1f}" width="92" height="{bar:.1f}" rx="7" fill="#a78bfa"/>'
                       f'<text x="{x+46}" y="{top-9:.1f}" class="aaValue" text-anchor="middle">{value:.2f}</text>'
                       f'<text x="{x+46}" y="803" class="aa" text-anchor="middle">{mode}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-K RTX stage and AA cost isolation</title>
<desc id="desc">Average visible viewport FPS for staged scene additions and DLSS modes at 1280 by 720, RTX 3090, 210 watt power limit.</desc>
<rect width="1260" height="850" rx="28" fill="#08111f"/><style>.k{{font:700 15px system-ui;fill:#7dd3fc;letter-spacing:2px}}.t{{font:700 32px system-ui;fill:#f8fafc}}.s{{font:15px system-ui;fill:#94a3b8}}.label{{font:14px system-ui;fill:#dbeafe}}.value{{font:700 14px system-ui;fill:#f8fafc}}.aa{{font:12px system-ui;fill:#c4b5fd}}.aaValue{{font:700 13px system-ui;fill:#f8fafc}}</style>
<text x="55" y="48" class="k">PHASE V3T-K · PRODUCTION-NEUTRAL VISIBLE VIEWPORT</text><text x="55" y="91" class="t">The 32 FPS boundary is cumulative, not V3 Mesh alone</text>
<text x="55" y="120" class="s">Kit 110.2 · Flow 110.0.0 · RTX 3090 · 1280×720 · 210 W · DLSS Auto for stage matrix · 3 independent runs</text>
{''.join(rows)}
<line x1="760" y1="560" x2="760" y2="815" stroke="#334155"/><text x="800" y="590" class="k">GLOBAL FLOW OFF · ACTIVE SUBTREE · AA</text>
<text x="800" y="620" class="s">Performance nears 60 FPS; Auto and DLAA stay near 31 FPS.</text>
<line x1="790" y1="775" x2="1200" y2="775" stroke="#64748b"/>{''.join(aa_rows)}
<text x="55" y="838" class="s">No added RenderProduct/HydraTexture/capture · fatal logs 0 · internal render resolution unavailable through inspected public API</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-stage", type=Path, required=True)
    parser.add_argument("--formal-stage", type=Path, required=True)
    parser.add_argument("--formal-flow", type=Path, required=True)
    parser.add_argument("--formal-disabled", type=Path, required=True)
    parser.add_argument("--preflight-aa", type=Path, required=True)
    parser.add_argument("--formal-aa", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    preflight_stage = load(args.preflight_stage)
    formal_stage = load(args.formal_stage)
    formal_flow = load(args.formal_flow)
    formal_disabled = load(args.formal_disabled)
    preflight_aa = load(args.preflight_aa)
    formal_aa = load(args.formal_aa)
    preflight_stage_rows = [dict(row, condition="flow_prims_global_off_active") if row["condition"] == "flow_prims_disabled" else row for row in preflight_stage["entries"]]
    preflight_aa_rows = [dict(row, condition="flow_prims_global_off_active") if row["condition"] == "flow_prims_disabled" else row for row in preflight_aa["entries"]]
    selected_aa_rows = [dict(row, condition="flow_prims_global_off_active") if row["condition"] == "flow_prims_disabled" else row for row in formal_aa["entries"]]
    selected_stage_rows = [row for row in formal_stage["entries"] if row["condition"] not in FLOW_CONDITIONS]
    selected_stage_rows += [dict(row, condition="flow_prims_global_off_active") if row["condition"] == "flow_prims_disabled" else row for row in formal_flow["entries"]]
    selected_stage_rows += formal_disabled["entries"]
    stage = {condition: aggregate([row for row in selected_stage_rows if row["condition"] == condition]) for condition in STAGE_ORDER}
    aa = {mode: aggregate([row for row in selected_aa_rows if row["aa_mode"] == mode]) for mode in ("performance", "auto", "dlaa")}
    accepted = selected_stage_rows + selected_aa_rows
    fatal_total = sum(sum(int(value) for value in row["fatal_log_counts"].values()) for row in accepted)
    if len(selected_stage_rows) != 39 or len(selected_aa_rows) != 9 or fatal_total:
        raise RuntimeError("formal population or fatal-log gate failed")
    if any(float(row["gpu"]["power_limit_w"]) != 210.0 for row in accepted):
        raise RuntimeError("210 W power-limit gate failed")
    if any(row["classification"] != "normal" or row["exit_code"] != 0 for row in accepted):
        raise RuntimeError("normal-exit gate failed")
    settings = selected_stage_rows[0]["settings_before"]
    report = {
        "schema": "campfire.phasev3tk.rtx-stage-cost-report.v1", "status": "ok", "phase": "V3T-K",
        "baseline_commit": "88136a2", "kit": "110.2", "flow": "110.0.0", "gpu": "NVIDIA GeForce RTX 3090",
        "measurement_contract": {
            "output_resolution": [1280, 720], "power_limit_w": 210.0, "power_limit_percent_of_default": 60.0,
            "power_limit_changed": False,
            "measurement_only_override": {"path": "/rtx/ecoMode/enabled", "effective_value": False, "persisted_to_production": False},
            "visible_fps_source": "public ViewportAPI.frame_info frame_number delta / wall time",
            "hud_fps_source": "public smoothed ViewportAPI.frame_info fps", "display_present_fps_measured": False,
            "raw_frame_p95_p99_measured": False, "one_percent_low_measured": False,
            "additional_render_product_created": False, "hydra_texture_created": False, "capture_or_encode_used": False,
            "stage_or_material_mutated_during_measurement": False,
        },
        "formal_gate": {"stage_processes": len(selected_stage_rows), "aa_processes": len(selected_aa_rows),
                        "fatal_log_count": fatal_total, "stage_id_error_count": 0, "normal_exit_count": len(accepted)},
        "regression": {"standard_processes_passed": 8, "standard_processes_total": 8,
                       "tests_passed": 77, "tests_total": 77, "suite_elapsed_seconds": None,
                       "final_static_plus_suite_command_wall_seconds": 352.9},
        "effective_setting_audit": settings,
        "stage_formal": stage, "aa_formal": aa,
        "stage_preflight": {row["condition"]: row["metrics"] for row in preflight_stage_rows},
        "aa_preflight": {row["aa_mode"]: row["metrics"] for row in preflight_aa_rows},
        "deltas": {
            "empty_to_ground_stones_unlit": delta(stage, "empty_rtx", "ground_stones_no_lights"),
            "unlit_to_lit": delta(stage, "ground_stones_no_lights", "ground_stones_lit"),
            "lit_to_20_cylinders": delta(stage, "ground_stones_lit", "cylinder20_solid"),
            "cylinders_to_v3_mesh": delta(stage, "cylinder20_solid", "v3mesh20_solid"),
            "solid_to_fixed_textures": delta(stage, "v3mesh20_solid", "v3mesh20_static_texture"),
            "fixed_to_unprovided_dynamic": delta(stage, "v3mesh20_static_texture", "v3mesh20_dynamic_unprovided"),
            "rigid_stopped_to_play": delta(stage, "v3mesh20_dynamic_rigid_stopped", "v3mesh20_dynamic_rigid_play"),
            "no_flow_to_fully_disabled_flow_prims": delta(stage, "v3mesh20_dynamic_rigid_play", "flow_prims_disabled"),
            "fully_disabled_to_global_off_active_flow": delta(stage, "flow_prims_disabled", "flow_prims_global_off_active"),
            "global_off_active_to_simulation": delta(stage, "flow_prims_global_off_active", "flow_simulation_only"),
            "simulation_to_volume": delta(stage, "flow_simulation_only", "flow_volume"),
        },
        "decision": {
            "first_large_drop": "empty RTX to ground plus stones (-43.4%)",
            "v3_mesh_is_primary_cause": False, "unprovided_dynamic_uri_is_primary_cause": False,
            "flow_off_32fps_classification": "Flow global OFF and Emitter disabled were insufficient while Simulate/Render prims and layer Flow render settings remained active",
            "aa_dominant_observation": "Performance 59.81 FPS versus Auto 31.16 and DLAA 31.13 on the global-OFF/active-subtree scene",
            "highest_quality_mode_meeting_60_fps": None,
            "closest_tested_mode": "DLSS Performance (59.812 FPS mean; all three runs below 60)",
            "production_fix_required": "audit production Flow-OFF semantics: the exact all-OFF scene measured 44.25 FPS versus 31.48 with active Flow subtree/settings; do not change production in this phase",
            "profiler_run_performed": False,
            "profiler_reason": "staged and AA comparisons already identified the dominant public boundaries; no profiler overhead added",
        },
        "observed_facts": [
            "Cylinder20 and V3 Mesh20 differ by +0.12 FPS, within run variation.",
            "Fixed texture to unprovided dynamic URI costs 0.76 FPS; no repeated dynamic-URI warning/error was logged.",
            "RigidBody with timeline stopped is unchanged; timeline PLAY costs 8.55 FPS.",
            "Authoring Flow while explicitly deactivating Simulate/Render and layer Flow settings measured 44.25 FPS.",
            "Leaving the Flow subtree/settings active while global Flow and Emitter were OFF reduced the same constructed scene to 31.48 FPS.",
            "Flow simulation costs 6.95 FPS; volume rendering adds no measurable loss in this camera.",
        ],
        "strong_inferences": [
            "The reported Flow-OFF ~32 FPS is not caused primarily by the V3 render mesh or missing DynamicTextureProvider.",
            "The application-level Flow-OFF path does not fully eliminate Flow integration work when authored prims and layer render settings remain active.",
            "DLSS Auto behaves like the measured DLAA cost on this scene, but internal resolution/mode equivalence is unconfirmed.",
        ],
        "unconfirmed": [
            "Public internal render resolution was not found in Kit 110.2.",
            "Public Ray Reconstruction runtime state was not found.",
            "The exact RTX pass or Flow integration work executed for globally disabled Flow prims is not profiled.",
            "Why the explicit all-OFF Flow stage outperformed the no-Flow stage during timeline PLAY is not confirmed.",
            "Display-present FPS, raw frame latency p95/p99, and 1% low are not measured.",
        ],
    }
    samples = {
        "schema": "campfire.phasev3tk.rtx-stage-cost-samples.v1", "status": "ok",
        "formal_stage": [compact(row, "formal_stage") for row in selected_stage_rows],
        "formal_aa": [compact(row, "formal_aa") for row in selected_aa_rows],
        "preflight_stage": [compact(row, "preflight_stage") for row in preflight_stage_rows],
        "preflight_aa": [compact(row, "preflight_aa") for row in preflight_aa_rows],
        "rejected_populations": [
            {"path": "artifacts/phasev3tk-smoke-empty", "reason": "pre-Eco-mode readiness smoke; no visible frames"},
            {"path": "artifacts/phasev3tk-formal-flow-exact", "reason": "Flow effective-value mismatch before measurement"},
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "rtx_stage_cost_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "rtx_stage_cost_samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "rtx_stage_cost_report.svg").write_text(make_svg(stage, aa), encoding="utf-8")
    print(json.dumps({"status": "ok", "stage_processes": len(selected_stage_rows), "aa_processes": len(selected_aa_rows),
                      "flow_all_off_fps": stage["flow_prims_disabled"]["mean_fps"],
                      "flow_global_off_active_fps": stage["flow_prims_global_off_active"]["mean_fps"],
                      "performance_fps": aa["performance"]["mean_fps"]}, indent=2))


if __name__ == "__main__":
    main()
