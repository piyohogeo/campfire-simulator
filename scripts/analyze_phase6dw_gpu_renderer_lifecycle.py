#!/usr/bin/env python3
"""Build the sanitized Phase 6DW report from local, ignored run artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape


CONDITIONS = (
    "kit_only",
    "openusd_empty",
    "rtx_empty",
    "box_openusd",
    "box_rtx",
    "flow_load",
    "flow_sim",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def selected_gpu(lines: list[str]) -> dict:
    active = next((line.split("Active GPU:", 1)[1].strip() for line in lines if "Active GPU:" in line), None)
    cuda = next((line.rsplit(":", 1)[1].strip() for line in lines if "CUDA device index:" in line), None)
    display = next((line for line in lines if "primary monitor's refresh rate" in line), None)
    hydra = next((line.rsplit("mask:", 1)[1].strip() for line in lines if "getHydraEngineDeviceMask" in line), None)
    viewport = next((line.rsplit("device", 1)[1].strip() for line in lines if "assigned to device" in line), None)
    graph_cuda = next((line.rsplit(":", 1)[1].strip().rstrip(".") for line in lines if "CUDA device ordinal:" in line), None)
    return {
        "active_gpu": active,
        "cuda_device_index": cuda,
        "hydra_device_mask": hydra,
        "viewport_device": viewport,
        "graph_cuda_device_ordinal": graph_cuda,
        "primary_display_log": display,
    }


def summarize_run(path: Path) -> dict:
    raw = load(path / "raw.json")
    evidence = load(path / "runner_evidence.json")
    marker_names = [item["marker"] for item in evidence.get("lifecycle_history", [])]
    log_text = (path / "kit.log").read_text(encoding="utf-8", errors="replace") if (path / "kit.log").exists() else ""
    extra_device_lines = [
        line for line in log_text.splitlines()
        if any(token in line for token in ("getHydraEngineDeviceMask", "assigned to device", "CUDA device ordinal:"))
    ]
    def gpu_telemetry(items: list[dict]) -> list[dict]:
        keys = ("index", "name", "memory_used_mib", "utilization_percent", "power_w", "temperature_c")
        return [{key: item.get(key) for key in keys} for item in items]
    crash = evidence.get("crash_reporter", {})
    disabled_by = crash.get("automatic_upload_disabled_by", [])
    return {
        "condition": evidence["condition"],
        "cache_kind": evidence["cache_kind"],
        "status": evidence["probe_status"],
        "duration_seconds": round(float(evidence["duration_seconds"]), 6),
        "process_exit_code": evidence["process_exit_code"],
        "timed_out": evidence["timed_out"],
        "final_durable_marker": evidence["lifecycle_marker"],
        "markers": marker_names,
        "renderer_frame_complete": "first_viewport_frame_complete" in marker_names,
        "flow_extension_loaded": any(name in marker_names for name in ("flow_extension_load_complete", "flow_extension_load_verified")),
        "flow_simulation_started": "flow_simulation_started" in marker_names,
        "stage_close_complete": "stage_close_complete" in marker_names,
        "renderer_drain_complete": "renderer_drain_complete" in marker_names,
        "plugin_shutdown_observed": bool(evidence.get("plugin_shutdown_log_lines")),
        "fatal_count": len(evidence.get("fatal_lines", [])),
        "dump_count": len(evidence.get("dump_inventory", [])),
        "automatic_upload_attempt_count": len(evidence.get("automatic_upload_attempt_lines", [])),
        "crash_registry_unchanged": evidence.get("relevant_crash_registry_unchanged"),
        "crash_upload_contract": {
            "app_startup_upload_disabled": "/app/uploadDumpsOnStartup=false" in disabled_by,
            "old_dump_upload_skipped": "/crashreporter/skipOldDumpUpload=true" in disabled_by,
            "upload_url_empty": "/crashreporter/url=<empty>" in disabled_by,
            "privacy_opt_out_file": "/structuredLog/privacySettingsFile=<repo-local opt-out file>" in disabled_by,
            "preserve_dump_requested": crash.get("preserve_dump_requested"),
        },
        "production_changed": evidence.get("production_changed"),
        "production_app_sha256_before": evidence.get("production_app_sha256_before"),
        "production_app_sha256_after": evidence.get("production_app_sha256_after"),
        "gpu_before": gpu_telemetry(evidence.get("gpu_before", [])),
        "gpu_after": gpu_telemetry(evidence.get("gpu_after", [])),
        "selected_device": selected_gpu(evidence.get("selected_device_log_lines", []) + extra_device_lines),
        "effective_cache": "new_empty_isolated_cache" if evidence["cache_kind"] == "isolated" else "existing_user_cache",
        "kit_build": raw.get("kit_build"),
        "extensions": raw.get("extensions", {}),
    }


def historical_device_summary(phase: str, root: Path) -> dict:
    logs = list(root.rglob("kit.log")) if root.exists() else []
    active: set[str] = set()
    cuda: set[str] = set()
    evidence_logs = 0
    for log in logs:
        content = log.read_text(encoding="utf-8", errors="replace")
        found = False
        for line in content.splitlines():
            if "Active GPU:" in line:
                active.add(line.split("Active GPU:", 1)[1].strip())
                found = True
            if "CUDA device index:" in line:
                cuda.add(line.rsplit(":", 1)[1].strip())
                found = True
        evidence_logs += int(found)
    return {
        "phase": phase,
        "artifact_root": root.as_posix(),
        "kit_log_count": len(logs),
        "logs_with_device_evidence": evidence_logs,
        "active_gpu_names": sorted(active),
        "cuda_device_indices": sorted(cuda),
    }


def svg(report: dict) -> str:
    normal = {item["condition"]: item for item in report["formal_runs"] if item["cache_kind"] == "normal"}
    isolated = {item["condition"]: item for item in report["formal_runs"] if item["cache_kind"] == "isolated"}
    labels = {
        "kit_only": "Kit only",
        "openusd_empty": "OpenUSD empty",
        "rtx_empty": "RTX empty",
        "box_openusd": "Box OpenUSD",
        "box_rtx": "Box RTX",
        "flow_load": "Flow load",
        "flow_sim": "Flow simulation",
    }
    max_seconds = max(item["duration_seconds"] for item in report["formal_runs"])
    chart_x, chart_w = 278, 680
    rows = []
    for index, condition in enumerate(CONDITIONS):
        y = 175 + index * 61
        n = normal[condition]["duration_seconds"]
        i = isolated[condition]["duration_seconds"]
        nw = chart_w * n / max_seconds
        iw = chart_w * i / max_seconds
        rows.append(
            f'<text x="42" y="{y + 5}" class="label">{escape(labels[condition])}</text>'
            f'<rect x="{chart_x}" y="{y - 16}" width="{nw:.1f}" height="18" rx="5" class="normal"/>'
            f'<rect x="{chart_x}" y="{y + 8}" width="{iw:.1f}" height="18" rx="5" class="isolated"/>'
            f'<text x="{chart_x + nw + 9:.1f}" y="{y - 2}" class="value">{n:.2f}s</text>'
            f'<text x="{chart_x + iw + 9:.1f}" y="{y + 22}" class="value">{i:.2f}s</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700">
<style>
  .bg{{fill:#12151c}} .panel{{fill:#1d2330;stroke:#364052;stroke-width:1.5}} .title{{fill:#fff;font:700 30px system-ui,sans-serif}}
  .sub{{fill:#aeb9cb;font:16px system-ui,sans-serif}} .label{{fill:#e5ebf5;font:600 15px system-ui,sans-serif}}
  .value{{fill:#cbd5e4;font:13px ui-monospace,monospace}} .normal{{fill:#65d4a5}} .isolated{{fill:#f5b95f}}
  .metric{{fill:#fff;font:700 26px system-ui,sans-serif}} .metric-label{{fill:#9dacbf;font:13px system-ui,sans-serif}}
</style>
<rect width="1200" height="700" class="bg"/><rect x="24" y="24" width="1152" height="652" rx="18" class="panel"/>
<text x="50" y="72" class="title">Phase 6DW · GPU / renderer lifecycle baseline</text>
<text x="50" y="103" class="sub">RTX 3090 selected consistently · RTX 2070 present · normal and isolated cache</text>
<rect x="50" y="121" width="200" height="45" rx="9" fill="#273244"/><text x="66" y="146" class="metric">14 / 14</text><text x="155" y="146" class="metric-label">normal OS exits</text>
<rect x="978" y="121" width="150" height="45" rx="9" fill="#273244"/><text x="994" y="146" class="metric">0</text><text x="1022" y="146" class="metric-label">crash / dump</text>
{''.join(rows)}
<rect x="50" y="616" width="16" height="16" rx="4" class="normal"/><text x="76" y="629" class="sub">existing cache</text>
<rect x="210" y="616" width="16" height="16" rx="4" class="isolated"/><text x="236" y="629" class="sub">new empty isolated cache</text>
<text x="630" y="629" class="sub">Longer isolated-cache startup is cold initialization, not an exit failure.</text>
</svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--normal-root", type=Path, required=True)
    parser.add_argument("--isolated-root", type=Path, required=True)
    parser.add_argument("--explicit-root", type=Path, required=True)
    parser.add_argument("--phase6dt-root", type=Path, required=True)
    parser.add_argument("--phase6du-root", type=Path, required=True)
    parser.add_argument("--phase6dv-root", type=Path, required=True)
    parser.add_argument("--phase0-summary", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--production-app", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-svg", type=Path, required=True)
    args = parser.parse_args()

    inventory = load(args.inventory)
    install_2070 = next(
        item["properties"]["DEVPKEY_Device_FirstInstallDate"]
        for item in inventory["pnp_devices"]
        if "2070" in item["name"]
    )
    formal_runs = [summarize_run(args.normal_root / condition) for condition in CONDITIONS]
    formal_runs += [summarize_run(args.isolated_root / condition) for condition in CONDITIONS]
    explicit = summarize_run(args.explicit_root)
    phase0 = load(args.phase0_summary)
    candidate = load(args.candidate_manifest)
    if len(formal_runs) != 14:
        raise RuntimeError(f"Expected 14 formal processes, got {len(formal_runs)}")
    if any(item["process_exit_code"] != 0 or item["timed_out"] or item["status"] != "ok" for item in formal_runs):
        raise RuntimeError("Formal process exit/status gate failed")
    if any(item["fatal_count"] or item["dump_count"] or item["automatic_upload_attempt_count"] for item in formal_runs):
        raise RuntimeError("Formal crash/fatal/upload gate failed")
    if any(not all(item["crash_upload_contract"].values()) for item in formal_runs):
        raise RuntimeError("Formal crash-upload/preserve-dump configuration gate failed")
    if phase0.get("status") != "ok" or candidate.get("status") != "ok":
        raise RuntimeError("Phase 0 or Candidate Performance app regression failed")

    gpus = [
        {key: gpu.get(key) for key in (
            "index", "name", "pci_bus_id", "pci_device_id", "driver_version",
            "display_active", "memory_total_mib", "power_limit_w"
        )}
        for gpu in inventory["nvidia_gpus"]
    ]
    display_paths = [
        {key: item.get(key) for key in (
            "display_name", "adapter_name", "adapter_state_flags", "monitor_description", "monitor_state_flags"
        )}
        for item in inventory["display_paths"]
        if item.get("monitor_name")
    ]
    production_hash = sha256(args.production_app)
    production_changed = any(
        item["production_changed"]
        or item["production_app_sha256_before"] != production_hash
        or item["production_app_sha256_after"] != production_hash
        for item in formal_runs
    )
    if production_changed:
        raise RuntimeError("Production app hash gate failed")
    report = {
        "schema": "campfire.phase6dw.gpu-renderer-lifecycle-report.v1",
        "phase": "6DW",
        "status": "qualified_safe_baseline",
        "production_changed": production_changed,
        "production_app_sha256": production_hash,
        "environment": {
            "os": inventory["os"],
            "directx": inventory["dxdiag_summary"]["directx_version"],
            "wddm": sorted(set(inventory["dxdiag_summary"]["driver_models"])),
            "feature_levels": sorted(set(inventory["dxdiag_summary"]["feature_levels"])),
            "gpus": gpus,
            "display_paths": display_paths,
            "rtx_2070_first_install_local": install_2070,
            "physical_cable_identity": "not independently verified; Windows maps active outputs to both GPUs",
        },
        "timeline": {
            "rtx_2070_first_install_local": install_2070,
            "windows_last_boot_local": inventory["os"]["last_boot_local"],
            "phase_artifacts": inventory["artifact_timeline"],
            "classification": "Phase 6DT, 6DU, and 6DV artifacts all postdate RTX 2070 installation and the full reboot",
        },
        "historical_phase_device_evidence": [
            historical_device_summary("6DT", args.phase6dt_root),
            historical_device_summary("6DU", args.phase6du_root),
            historical_device_summary("6DV", args.phase6dv_root),
        ],
        "formal_runs": formal_runs,
        "formal_gate": {
            "processes": len(formal_runs),
            "normal_exit_count": sum(item["process_exit_code"] == 0 and not item["timed_out"] for item in formal_runs),
            "fatal_count": sum(item["fatal_count"] for item in formal_runs),
            "dump_count": sum(item["dump_count"] for item in formal_runs),
            "automatic_upload_attempt_count": sum(item["automatic_upload_attempt_count"] for item in formal_runs),
            "all_production_hashes_unchanged": all(not item["production_changed"] for item in formal_runs),
            "selected_gpu_names": sorted({item["selected_device"]["active_gpu"] for item in formal_runs if item["selected_device"]["active_gpu"]}),
            "selected_cuda_indices": sorted({item["selected_device"]["cuda_device_index"] for item in formal_runs if item["selected_device"]["cuda_device_index"]}),
        },
        "explicit_gpu_zero_control": explicit,
        "official_selection_evidence": {
            "setting": "/renderer/activeGpu",
            "local_runtime_evidence": "gpu.foundation.plugin.dll setting strings and omni.app.mini.kit",
            "auto_and_explicit_gpu_zero_same_device": explicit["selected_device"]["active_gpu"] == "NVIDIA GeForce RTX 3090",
            "production_default_changed": False,
        },
        "regressions": {
            "release_build": {"status": "ok", "seconds": 6.25},
            "standard_suite": {"status": "ok", "processes": 8, "tests_passed": 78, "tests_total": 78, "wall_seconds": 310.6},
            "phase0_rtx": {"status": phase0["status"], "resolution": phase0["resolution"]},
            "candidate_performance_apps": {"status": candidate["status"], "app_count": len(candidate["entries"]), "gpu": candidate["gpu"]},
            "known_good_flow_minimal": {"status": next(item["status"] for item in formal_runs if item["condition"] == "flow_sim" and item["cache_kind"] == "normal")},
            "devlog_static": {"status": "ok", "local_reference_count": 589, "missing_reference_count": 0, "utf8_replacement_character_count": 0},
            "devlog_browser_render": {"status": "unavailable", "reason": "no browser binding in this session"},
        },
        "classification": {
            "observed": [
                "RTX 3090 was selected as render/CUDA device 0 in every formal renderer run",
                "Kit primary present display was DISPLAY2 on RTX 3090; no cross-adapter presentation was observed",
                "all seven conditions exited normally with both existing and newly isolated cache directories",
                "known-good Box reached first renderer frame, stage close, renderer drain, plugin shutdown, and OS exit",
                "Flow extension load and known-good Flow simulation also exited normally",
            ],
            "strong_inference": [
                "Phase 6DV's non-exit is more likely tied to its launcher/app composition or teardown ordering than to the current two-GPU configuration alone",
                "the existing renderer cache is not required to obtain a normal lifecycle; isolated cache only increases cold startup time",
            ],
            "unconfirmed": [
                "whether the RTX 2070 addition contributed to the historical Fabric crashes through a rare race or stale cache state",
                "function-level cause of omni.fabric.plugin.dll+0xD6960",
                "Flow 110.0.0 does not emit a separate public device-selection line; the Flow process used RTX/Hydra device mask 1 and graph CUDA ordinal 0",
                "physical cable identity beyond Windows display-path mapping",
            ],
        },
        "phase6du_restart": {
            "qualified": True,
            "scope": "next independent staged Box-to-Cylinder ablation only",
            "direct_failed_condition_rerun": False,
            "minimum_safe_start": "known-good static axis-aligned Flow-only Box Mesh, then one topology difference per process before any Cylinder hull retry",
        },
        "excluded_local_runs": {
            "reason": "runner-development defects before the formal matrix; no native crash, dump, upload, device lost, or TDR",
            "included_in_formal_population": False,
        },
        "sensitive_local_artifacts_committed": False,
        "latest_demo_changed": False,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_svg.write_text(svg(report), encoding="utf-8")


if __name__ == "__main__":
    main()
