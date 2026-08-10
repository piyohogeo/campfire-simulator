"""Collect completed Phase V3T-R run directories without rerunning Kit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
from datetime import datetime
from pathlib import Path


DEVELOPER_EXTENSIONS = (
    "omni.kit.debug.python",
    "omni.kit.debug.settings",
    "omni.kit.debug.vscode",
    "omni.kit.dev.utilities.bundle",
    "omni.kit.developer.bundle",
    "omni.kit.widget.text_editor",
    "omni.kit.window.commands",
    "omni.kit.window.extensions",
    "omni.kit.window.script_editor",
)
RUN_PATTERN = re.compile(r"^(normal|developer|benchmark)_r(\d+)_o(\d+)$")
STARTUP_PATTERN = re.compile(r"\[ext:\s*([^\]]+)\]\s+startup")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _name(extension_id: str) -> str:
    return re.sub(r"-\d.*$", "", extension_id)


def _summary(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _gpu_rows(path: Path, start: datetime | None) -> list[dict]:
    if not path.exists():
        return []
    result = []
    with path.open(encoding="utf-8", errors="replace", newline="") as stream:
        for columns in csv.reader(stream):
            if len(columns) < 11:
                continue
            try:
                stamp = datetime.strptime(columns[0].strip(), "%Y/%m/%d %H:%M:%S.%f")
                if start is not None and stamp < start.replace(tzinfo=None):
                    continue
                result.append(
                    {
                        "utilization": float(columns[1]),
                        "memory_mib": float(columns[2]),
                        "power_w": float(columns[3]),
                        "graphics_clock_mhz": float(columns[4]),
                        "sm_clock_mhz": float(columns[5]),
                        "temperature_c": float(columns[6]),
                        "pstate": columns[7].strip(),
                        "power_limit_w": float(columns[8]),
                        "enforced_power_limit_w": float(columns[9]),
                        "perf_cap_reason": columns[10].strip(),
                    }
                )
            except (TypeError, ValueError):
                continue
    return result


def _collect_run(directory: Path, condition: str, run: int, order: int) -> dict:
    summary = _load(directory / "summary.json")
    runtime = _load(directory / "runtime_diagnostic.json")
    log_text = (directory / "kit.log").read_text(encoding="utf-8", errors="replace")
    startup_order = STARTUP_PATTERN.findall(log_text)
    enabled_names = {_name(item) for item in startup_order}
    developer_present = sorted(set(DEVELOPER_EXTENSIONS) & enabled_names)
    listen_lines = [
        line
        for line in log_text.splitlines()
        if "[omni.kit.debug.python] Listening python debugger on:" in line
    ]
    if condition == "developer":
        if set(developer_present) != set(DEVELOPER_EXTENSIONS):
            raise RuntimeError(f"developer extension gate failed: {directory}")
        if len(listen_lines) != 1 or "127.0.0.1" not in listen_lines[0] or "3000" not in listen_lines[0]:
            raise RuntimeError(f"developer listen gate failed: {directory}")
    elif developer_present or listen_lines or not summary["scenario"]["debugger_free"]:
        raise RuntimeError(f"debugger-free gate failed: {directory}")
    if runtime["status"] != "ok":
        raise RuntimeError(f"runtime diagnostic did not close cleanly: {directory}")
    if not summary["scenario"]["wood_visual_v3"]["enabled"] or summary["flow"]["active_blocks_peak"] <= 0:
        raise RuntimeError(f"V3/Flow gate failed: {directory}")
    wood = summary["wood"]
    if wood["dry"]["mass_balance_error_kg"] != 0 or wood["wet"]["mass_balance_error_kg"] != 0:
        raise RuntimeError(f"mass-balance gate failed: {directory}")
    play = next((row for row in runtime["snapshots"] if row["marker"] == "timeline_play"), None)
    play_time = datetime.fromisoformat(play["timestamp_utc"]) if play else None
    gpu_rows = _gpu_rows(directory / "gpu.csv", play_time)
    timing = summary["timing"]["segments"]["frame_pacing"]["update_frame"]
    performance = summary["scenario"]
    v3 = performance["wood_visual_v3"]
    return {
        "condition": condition,
        "run": run,
        "order_index": order,
        "startup_order": startup_order,
        "enabled_extension_ids": sorted(set(startup_order)),
        "developer_extension_names": developer_present,
        "debugpy_listen": {
            "observed": len(listen_lines) == 1,
            "lines": listen_lines,
            "expected_address": "127.0.0.1:3000" if condition == "developer" else None,
        },
        "performance": {
            "average_visible_fps": performance["visible_viewport"]["average_fps"],
            "derived_frame_time_ms": round(1000.0 / performance["visible_viewport"]["average_fps"], 4),
            "kit_updates_per_second": round(1000.0 / timing["mean_ms"], 4),
            "timeline_sim_wall_ratio": round(performance["model_duration_seconds"] / performance["simulation_wall_seconds"], 4),
            "main_update_interval": timing,
            "v3_publication_timing": v3["publication_timing"],
            "v3_publication_count": len(v3["publication_samples"]),
            "v3_upload_count": v3["status_after_timeline_stop"]["upload_count"],
            "v3_quantized_skip_count": v3["status_after_timeline_stop"]["quantized_skip_count"],
            "v3_visual_commit_count": v3["status_after_timeline_stop"]["visual_commit_count"],
            "flow_active_blocks_final": summary["flow"]["active_blocks_final"],
            "flow_active_blocks_peak": summary["flow"]["active_blocks_peak"],
        },
        "authority": {
            "dry_sha256": wood["dry"]["authoritative_state_sha256"],
            "wet_sha256": wood["wet"]["authoritative_state_sha256"],
            "dry_mass_balance_error_kg": wood["dry"]["mass_balance_error_kg"],
            "wet_mass_balance_error_kg": wood["wet"]["mass_balance_error_kg"],
        },
        "gpu": {
            **{
                output_name: _summary([row[source_name] for row in gpu_rows])
                for output_name, source_name in (
                    ("utilization_percent", "utilization"),
                    ("power_w", "power_w"),
                    ("graphics_clock_mhz", "graphics_clock_mhz"),
                    ("sm_clock_mhz", "sm_clock_mhz"),
                    ("memory_used_mib", "memory_mib"),
                    ("temperature_c", "temperature_c"),
                    ("power_limit_w", "power_limit_w"),
                    ("enforced_power_limit_w", "enforced_power_limit_w"),
                )
            },
            "pstates": sorted({row["pstate"] for row in gpu_rows}),
            "perf_cap_reasons": sorted({row["perf_cap_reason"] for row in gpu_rows}),
        },
        "runtime_diagnostic": {
            "status": runtime["status"],
            "kit": runtime["kit"],
            "app_name": runtime["app_name"],
            "setting_changes": runtime["setting_changes"],
            "observed_update_count": runtime["observed_update_count"],
            "snapshots": [
                {key: row.get(key) for key in ("marker", "timestamp_utc", "update_index", "timeline_playing", "timeline_seconds", "settings")}
                for row in runtime["snapshots"]
            ],
        },
        "paths": {
            "summary": str(directory / "summary.json"),
            "log": str(directory / "kit.log"),
            "diagnostic": str(directory / "runtime_diagnostic.json"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-apps", type=Path)
    parser.add_argument("--visible-window", action="store_true")
    args = parser.parse_args()
    root = args.input.resolve()
    repo = Path(__file__).resolve().parents[1]
    candidate_apps = args.candidate_apps or root / "candidate-apps"
    apps = {
        "normal": candidate_apps / "campfire.simulator.candidate.kit",
        "developer": candidate_apps / "campfire.simulator.developer.candidate.kit",
        "benchmark": repo / "_build" / "windows-x86_64" / "release" / "apps" / "campfire.simulator.benchmark.kit",
    }
    entries = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        match = RUN_PATTERN.match(directory.name)
        if match:
            entries.append(_collect_run(directory, match.group(1), int(match.group(2)), int(match.group(3))))
    if not entries:
        raise RuntimeError(f"no completed Phase V3T-R runs found: {root}")
    manifest = {
        "schema": "campfire.phasev3tr.debug-split-manifest.v1",
        "status": "ok",
        "kit": "110.2",
        "flow": "110.0.0",
        "resolution": [1280, 720],
        "candidate_performance": True,
        "power_limit_changed": False,
        "v3_default_on": True,
        "gpu_transport": "cpu_source",
        "visible_window": args.visible_window,
        "app_hashes_after": {name: {"path": str(path), "sha256": _sha256(path)} for name, path in apps.items()},
        "entries": sorted(entries, key=lambda row: (row["run"], row["order_index"])),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(entries)} Phase V3T-R run(s): {args.output}")


if __name__ == "__main__":
    main()
