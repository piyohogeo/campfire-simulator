"""Aggregate Phase V3T-L performance, visual, and crash evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path


SCENES = ["ground_stones_no_lights", "ground_stones_lit", "cylinder20_solid", "v3mesh20_static_texture", "flow_volume"]
LABELS = ["Ground + stones", "+ lights", "+ 20 cylinders", "V3 mesh + fixed texture", "Flow simulation + volume"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def aggregate(rows):
    fps = [float(row["metrics"]["average_visible_fps"]) for row in rows]
    return {
        "run_count": len(rows), "values_fps": fps, "mean_fps": statistics.fmean(fps),
        "stdev_fps": statistics.stdev(fps), "mean_frame_time_ms_from_average_fps": 1000.0 / statistics.fmean(fps),
        "hud_mean_fps": statistics.fmean(float(row["metrics"]["hud_fps_mean"]) for row in rows),
        "kit_updates_per_second": statistics.fmean(float(row["metrics"]["kit_updates_per_second"]) for row in rows),
        "timeline_sim_per_wall": statistics.fmean(float(row["metrics"]["timeline_sim_per_wall"]) for row in rows),
        "gpu_utilization_mean_percent": statistics.fmean(float(row["gpu"]["utilization_mean_percent"]) for row in rows),
        "graphics_clock_mean_mhz": statistics.fmean(float(row["gpu"]["graphics_clock_mean_mhz"]) for row in rows),
        "power_mean_w": statistics.fmean(float(row["gpu"]["power_mean_w"]) for row in rows),
        "vram_max_mib": max(float(row["gpu"]["memory_max_mib"]) for row in rows),
    }


def file_info(path: Path):
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def svg(k_baseline, formal, preflight):
    width, height = 1280, 780
    colors = {"v3tk_auto": "#64748b", "candidate_balanced": "#38bdf8", "candidate_performance": "#a78bfa"}
    rows = []
    for i, (scene, label) in enumerate(zip(SCENES, LABELS)):
        y = 150 + i * 92
        rows.append(f'<text x="45" y="{y+20}" class="label">{label}</text>')
        for j, mode in enumerate(("v3tk_auto", "candidate_balanced", "candidate_performance")):
            value = k_baseline[scene] if mode == "v3tk_auto" else formal[scene][mode]["mean_fps"]
            bar = min(730, value / 120 * 730)
            yy = y + j * 22
            rows.append(f'<rect x="300" y="{yy}" width="{bar:.1f}" height="16" rx="5" fill="{colors[mode]}"/><text x="{310+bar:.1f}" y="{yy+13}" class="value">{value:.2f} FPS · {1000/value:.2f} ms</text>')
    contrib = [("Balanced", preflight["balanced"]), ("Performance", preflight["performance"]), ("Max bounces 2", preflight["max_bounces_2"]), ("RTX Minimal*", preflight["minimal"])]
    crows = []
    for i, (label, value) in enumerate(contrib):
        x = 735 + i * 125
        h = value / 65 * 105
        crows.append(f'<rect x="{x}" y="{730-h:.1f}" width="82" height="{h:.1f}" rx="7" fill="#f59e0b"/><text x="{x+41}" y="{718-h:.1f}" class="value" text-anchor="middle">{value:.1f}</text><text x="{x+41}" y="752" class="small" text-anchor="middle">{label}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Phase V3T-L lightweight RTX preset comparison</title><desc id="desc">Average visible viewport FPS and derived frame time at 1280 by 720 and 210 watts.</desc>
<rect width="1280" height="780" rx="28" fill="#08111f"/><style>.k{{font:700 15px system-ui;fill:#7dd3fc;letter-spacing:2px}}.t{{font:700 31px system-ui;fill:#f8fafc}}.s{{font:15px system-ui;fill:#94a3b8}}.label{{font:14px system-ui;fill:#dbeafe}}.value{{font:700 13px system-ui;fill:#f8fafc}}.small{{font:12px system-ui;fill:#cbd5e1}}</style>
<text x="45" y="46" class="k">PHASE V3T-L · PRODUCTION-NEUTRAL RTX PRESET</text><text x="45" y="87" class="t">DLSS + RT2 max-bounces dominates the tested public controls</text>
<text x="45" y="116" class="s">Kit 110.2 · Flow 110.0.0 · RTX 3090 · 1280×720 · 210 W · 3 runs per candidate</text>
{''.join(rows)}<g><rect x="1015" y="130" width="18" height="12" fill="#64748b"/><text x="1040" y="141" class="small">V3T-K Auto</text><rect x="1015" y="151" width="18" height="12" fill="#38bdf8"/><text x="1040" y="162" class="small">Candidate Balanced</text><rect x="1015" y="172" width="18" height="12" fill="#a78bfa"/><text x="1040" y="183" class="small">Candidate Performance</text></g>
<text x="735" y="592" class="k">FLOW + VOLUME ONE-SETTING PREFLIGHT</text>{''.join(crows)}
<text x="45" y="766" class="s">* Minimal reached 60 FPS but failed the Flow active-block compatibility gate. AO OFF caused native 0xC0000005 and is held.</text></svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v3tk-report", type=Path, required=True)
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--preflight-partial", type=Path, required=True)
    parser.add_argument("--preflight-safe", type=Path, required=True)
    parser.add_argument("--crash-analysis", type=Path, required=True)
    parser.add_argument("--visual-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    k = load(args.v3tk_report)
    formal_manifest = load(args.formal)
    safe = load(args.preflight_safe)
    partial_rows = [load(path) for path in args.preflight_partial.glob("*/process.json")]
    preflight_rows = partial_rows + list(safe["entries"])
    crash = load(args.crash_analysis)
    formal = {scene: {} for scene in SCENES}
    for scene in SCENES:
        for preset in ("candidate_balanced", "candidate_performance"):
            formal[scene][preset] = aggregate([row for row in formal_manifest["entries"] if row["condition"] == scene and row["preset"] == preset])
    preflight = {row["preset"]: float(row["metrics"]["average_visible_fps"]) for row in preflight_rows}
    baseline_preflight = preflight["baseline"]
    contributions = {name: {"fps": value, "frame_time_ms": 1000 / value, "frame_time_delta_ms_vs_baseline": 1000 / value - 1000 / baseline_preflight} for name, value in preflight.items()}
    kmap = {
        "ground_stones_no_lights": k["stage_formal"]["ground_stones_no_lights"]["mean_fps"],
        "ground_stones_lit": k["stage_formal"]["ground_stones_lit"]["mean_fps"],
        "cylinder20_solid": k["stage_formal"]["cylinder20_solid"]["mean_fps"],
        "v3mesh20_static_texture": k["stage_formal"]["v3mesh20_static_texture"]["mean_fps"],
        "flow_volume": k["stage_formal"]["flow_volume"]["mean_fps"],
    }
    visual_files = [file_info(path) for path in sorted(args.visual_dir.iterdir()) if path.is_file()]
    accepted = formal_manifest["entries"]
    fatal = sum(sum(int(v) for v in row["fatal_log_counts"].values()) for row in accepted)
    if len(accepted) != 30 or fatal or any(float(row["gpu"]["power_limit_w"]) != 210 for row in accepted):
        raise RuntimeError("formal population gate failed")
    report = {
        "schema": "campfire.phasev3tl.lightweight-rtx-report.v1", "status": "ok", "phase": "V3T-L", "baseline_commit": "cb96b2a",
        "contract": {"production_changed": False, "power_limit_w": 210, "power_limit_changed": False, "display_present_fps_measured": False, "visible_fps_source": "ViewportAPI.frame_info frame delta / wall time", "frame_time_definition": "1000 / average visible FPS; not raw frame latency"},
        "formal_gate": {"processes": 30, "normal_exits": 30, "fatal_log_count": fatal, "crash_count": 0},
        "v3tk_auto_reference": kmap, "formal_candidates": formal, "individual_preflight": contributions,
        "ao_off_native_crash": {"classification": "native_crash_excluded", "candidate_status": "held", "continuous_rerun_performed": False, "analysis": crash, "retry_artifact_status": "aborted and excluded"},
        "visual_gate": {"performance_population": False, "files": visual_files, "balanced": "pass: geometry, shadows, V3 emission, flame and smoke remain visible during fixed and moving camera capture", "performance": "conditional pass: same features remain visible; flame/smoke fine detail is slightly smoother, so fallback-only is recommended", "minimal": "fail: Phase 3 Flow active-block gate failed; not a production candidate"},
        "decision": {"candidate_balanced": "quality baseline candidate only; production Flow scene mean 45.41 FPS does not reach the 58-FPS near-present threshold", "candidate_performance": "fallback candidate; Flow mean 47.86 FPS, still below 58", "ao": "do not change until native crash boundary is understood", "max_bounces_2": "strong positive contribution and retained", "cache_and_optional_features": "no measurable individual benefit in the tested Flow scene and omitted from combined candidates", "power_100_percent": "not executed; requires a later explicit approval"},
        "observed_facts": ["Ground/stones Auto reference 17.40 ms fell to 8.57 ms with either candidate.", "Cylinder20 Auto reference 21.73 ms fell to 8.57 ms.", "Flow+volume Auto reference 40.79 ms fell to 22.02 ms Balanced and 20.90 ms Performance.", "AO OFF crashed in omni.fabric.plugin.dll+0xD6960 during startup after scene acceleration-structure creation.", "RTX Minimal reached 60.08 FPS in preflight but failed the real Phase 3 Flow active-block gate."],
        "strong_inferences": ["DLSS mode and RT2 max-bounces are the dominant tested public controls.", "The AO crash is native Fabric/Hydra-boundary evidence, not a Python exception."],
        "unconfirmed": ["AO OFF versus Flow volume versus setting timing versus RTX initialization race is not isolated.", "The native stack is not authoritatively unwound because WinDbg/CDB and private symbols are unavailable.", "Display-present FPS and raw frame-time percentiles remain unmeasured."],
    }
    samples = {"schema": "campfire.phasev3tl.lightweight-rtx-samples.v1", "status": "ok", "formal": accepted, "preflight": preflight_rows, "excluded": [{"condition": "ao_off", "reason": "native crash"}, {"condition": "ao_off_retry", "reason": "aborted after crash discovery"}]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "lightweight_rtx_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "lightweight_rtx_samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "lightweight_rtx_report.svg").write_text(svg(kmap, formal, preflight), encoding="utf-8")
    print(json.dumps({"status": "ok", "formal": len(accepted), "flow_balanced": formal["flow_volume"]["candidate_balanced"]["mean_fps"], "flow_performance": formal["flow_volume"]["candidate_performance"]["mean_fps"]}, indent=2))


if __name__ == "__main__":
    main()
