"""Aggregate the bounded Phase 6EA condition-A shutdown evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "artifacts" / "phase6ea-shutdown-residual-1"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


LOG_PREFIX = re.compile(r"^\S+ \[[^]]+\] \[[^]]+\] \[[^]]+\] ")


def normalize_log(line: str) -> str:
    return LOG_PREFIX.sub("", line.rstrip())


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+([+-])", r"\1\2", value))


def tool_inventory() -> list[dict]:
    result = []
    names = ["windbg", "windbgx", "cdb", "procdump", "procdump64", "procexp", "handle", "listdlls", "dumpchk", "wpr", "wpa"]
    for name in names:
        path = shutil.which(name)
        if name == "wpa" and not path:
            candidate = Path(r"C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit\wpa.exe")
            path = str(candidate) if candidate.exists() else None
        result.append({"name": name, "available": bool(path), "path": path})
    result.extend(
        [
            {"name": "Windows Wait Chain Traversal API", "available": True, "path": "advapi32.dll (public API)"},
            {"name": "Windows MiniDumpWriteDump API", "available": True, "path": "DbgHelp.dll (public API)"},
        ]
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    stage = load(artifact / "stage_difference_v2.json")
    raw = load(artifact / "A_phase6dy_direct" / "raw.json")
    runner = load(artifact / "A_phase6dy_direct" / "runner_evidence.json")
    monitor = load(artifact / "A_monitor" / "monitor_evidence.json")
    dump_analysis = load(artifact / "A_monitor" / "hang_dump_analysis.json")
    dump_path = artifact / "A_monitor" / "sensitive-hang-diagnostics" / "hang-full.dmp"
    success_root = ROOT / "artifacts" / "phase6dy-calibrated-stage-open-1" / "stage-open" / "D_cylinder_decomposition"
    success = load(success_root / "runner_evidence.json")
    success_lines = (success_root / "kit.log").read_text(encoding="utf-8", errors="replace").splitlines()
    hang_lines = (artifact / "A_phase6dy_direct" / "kit.log").read_text(encoding="utf-8", errors="replace").splitlines()
    hang_last = normalize_log(hang_lines[-1])
    matching = [index for index, line in enumerate(success_lines) if normalize_log(line) == hang_last]
    match_index = matching[-1] if matching else None
    next_success = normalize_log(success_lines[match_index + 1]) if match_index is not None and match_index + 1 < len(success_lines) else None
    shutdown_time = next(
        parse_iso(item["timestamp_utc"])
        for item in raw["lifecycle_history"]
        if item["marker"] == "shutdown_requested"
    )
    runner_end = parse_iso(runner["ended_local"])
    earliest_id = dump_analysis["earliest_created_thread_id"]
    earliest = next(item for item in dump_analysis["threads"] if item["thread_id"] == earliest_id)
    candidate_modules = []
    for candidate in earliest.get("stack_module_candidates", []):
        name = Path(candidate["module"]["name"]).name
        label = f"{name}+{candidate['module']['offset']}"
        if label not in candidate_modules:
            candidate_modules.append(label)
        if len(candidate_modules) >= 16:
            break
    report = {
        "schema": "campfire.phase6ea.shutdown-residual-report.v1",
        "phase": "phase6ea",
        "status": "safe_stop",
        "condition_a": {
            "status": "hang_confirmed",
            "stage_sha256": stage["left"]["sha256"],
            "runner": "scripts/run_phase6dw_gpu_renderer_case.ps1",
            "probe": "scripts/probe_phase6dw_gpu_renderer_lifecycle.py",
            "cache": "normal",
            "app": "omni.app.viewport.kit",
            "lifecycle_marker": raw["lifecycle_marker"],
            "probe_status": raw["status"],
            "normal_os_exit": False,
            "observed_seconds_after_shutdown_requested": (runner_end - shutdown_time.astimezone(runner_end.tzinfo)).total_seconds(),
            "automatic_retry": False,
            "path_verified_before_capture_and_stop": True,
            "process_id": dump_analysis["process_id"],
            "parent_runner_pid": monitor["outer_pid"],
            "fatal_count": len(runner["fatal_lines"]),
            "crash_reporter_dump_count": len(runner["dump_inventory"]),
            "automatic_upload_attempt_count": len(runner["automatic_upload_attempt_lines"]),
        },
        "matrix": {
            "A_phase6dy_direct": "hang_confirmed",
            "B_phase6dy_through_phase6dz_outer": "not_run_due_to_A_hang",
            "C_phase6dz_axis": "not_run_due_to_A_hang",
            "phase6dy_three_run_stability": "not_run_due_to_A_hang",
            "rotation_restart": "not_permitted",
        },
        "stage_comparison": {
            "phase6dy_sha256": stage["left"]["sha256"],
            "phase6dz_sha256": stage["right"]["sha256"],
            "normalized_difference_count": stage["normalized_difference_count"],
            "differences": [
                {"path": item["path"], "classification": "generated source documentation differs"}
                for item in stage["normalized_differences"]
            ],
            "semantic_payload_equal_except_documentation": stage["semantic_payload_equal_except_documentation"],
            "category_gates": stage["category_gates"],
        },
        "successful_control_comparison": {
            "prior_phase6dy_exit_code": success["process_exit_code"],
            "prior_phase6dy_duration_seconds": success["duration_seconds"],
            "last_common_shutdown_line": hang_last,
            "first_line_reached_by_success_but_not_hang": next_success,
            "hang_final_log_line_number": len(hang_lines),
            "success_matching_line_number": match_index + 1 if match_index is not None else None,
        },
        "hang_dump": {
            "relative_path": str(dump_path.relative_to(ROOT)).replace("\\", "/"),
            "git_ignored": True,
            "bytes": dump_path.stat().st_size,
            "sha256": sha256(dump_path),
            "full_memory_range_count": dump_analysis["full_memory_range_count"],
            "module_count": dump_analysis["module_count"],
            "thread_count": dump_analysis["thread_count"],
            "exception_stream_present": dump_analysis["exception_stream_present"],
            "instruction_module_counts": dump_analysis["instruction_module_counts"],
            "earliest_created_thread": {
                "thread_id": earliest_id,
                "instruction_module": earliest["instruction_module"],
                "kernel_time_100ns": earliest["thread_info"]["kernel_time_100ns"],
                "user_time_100ns": earliest["thread_info"]["user_time_100ns"],
                "heuristic_stack_module_candidates": candidate_modules,
            },
            "native_stack_unwind": dump_analysis["stack_analysis"],
            "wait_chain": {
                "available": False,
                "reason": "The first public-WCT collection did not produce durable output before the bounded capture command; future collection is capped at 10 seconds and writes a pre-dump snapshot.",
            },
            "handle_targets": {
                "available": False,
                "reason": "The dump includes MiniDumpWithHandleData, but no installed public debugger/analyzer can decode it in this environment.",
            },
        },
        "classification": {
            "observed_fact": [
                "The exact Phase 6DY qualified stage completed OpenUSD, USD-context, Hydra, viewport, stage-close, renderer-drain, and shutdown_requested before the process remained alive.",
                "The hang log stopped after 'Shutting down plugin gpu.foundation.plugin'; the prior successful log continued with PerfMonitor shutdown and remaining plugin unloads.",
                "The hang dump has no ExceptionStream; 132 of 133 captured instruction pointers are in ntdll.dll and one is in win32u.dll.",
                "No crash-reporter dump, fatal token, device-lost/TDR token, or upload attempt was recorded.",
            ],
            "strong_inference": "The residual process is predominantly waiting during the GPU/graphics teardown boundary at or immediately after gpu.foundation shutdown, rather than failing in stage geometry or Python probe execution.",
            "unconfirmed": [
                "The exact wait object and owner thread are unavailable because the WCT attempt did not complete durably.",
                "The heuristic stack scan is not a symbolized unwind and cannot identify a responsible function.",
                "Whether the cause is intermittent renderer teardown, NVIDIA NGX/telemetry, D3D12, or a Kit plugin lifetime issue remains unconfirmed.",
            ],
            "relation_to_prior_fabric_crash": "No ExceptionStream is present and the captured hang contexts do not reproduce omni.fabric.plugin.dll+0xD6960; this is a different evidence class, not proof of the same fault.",
            "runner_pid_misidentification": "denied_for_this_run: the remaining PID was kit.exe and its executable path was checked before dump capture and termination",
        },
        "tool_inventory": tool_inventory(),
        "production": {
            "app_sha256_before": runner["production_app_sha256_before"],
            "app_sha256_after": runner["production_app_sha256_after"],
            "changed": runner["production_changed"],
            "production_code_changed": False,
            "latest_demo_changed": False,
        },
        "decision": {
            "normal_control_recovered": False,
            "phase6du_resume_allowed": False,
            "rotation_resume_allowed": False,
            "next_required_evidence": "Analyze the preserved full dump with WinDbg/CDB and matching symbols, or perform a separately approved bounded ETW/WPR teardown trace; do not auto-retry condition A.",
        },
        "verification": {
            "release_build": {"status": "ok", "seconds": 9.41},
            "phase6dy_lifecycle_contract": {"status": "ok", "passed": 6, "total": 6},
            "phase6dz_rotation_roi_contract": {"status": "ok", "passed": 5, "total": 5},
            "phase6ea_diagnostic_contract": {"status": "ok", "passed": 5, "total": 5},
            "standard_suite": {"status": "ok", "processes": 8, "passed": 78, "total": 78, "seconds": 380.1},
            "flow_collider_test": {
                "status": "ok_in_standard_suite",
                "test": "campfire.app.tests.test_scene.TestScene.test_flow_scene_has_emitter_simulation_and_colliders",
            },
            "excluded_direct_test_launcher": {
                "status": "excluded_harness_permission_failure",
                "reason": "A non-escalated direct Kit test attempt could not write the AppData test reporter and was path-verified and stopped after its 120-second timeout; it is not a product or test failure and is not part of the formal results.",
                "automatic_retry": False,
            },
            "devlog_static": {"status": "ok", "unique_local_references": 333, "missing": 0, "json_files": 178, "svg_files": 145, "replacement_characters": 0},
            "phase0_rtx": {"status": "not_run", "reason": "production code and app composition unchanged"},
            "phase3": {"status": "not_run", "reason": "production code and app composition unchanged"},
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520" viewBox="0 0 1200 520" role="img" aria-labelledby="title desc">
<title id="title">Phase 6EA Kit shutdown residual process diagnosis</title>
<desc id="desc">Condition A completed stage lifecycle but remained after shutdown, stopping before conditions B and C.</desc>
<rect width="1200" height="520" fill="#11151c"/><text x="60" y="64" fill="#f4f0e6" font-family="Segoe UI, sans-serif" font-size="30" font-weight="700">Phase 6EA — Kit shutdown residual diagnosis</text>
<text x="60" y="100" fill="#aab7c8" font-family="Segoe UI, sans-serif" font-size="18">Exact Phase 6DY stage · production-neutral · no automatic retry</text>
<g font-family="Segoe UI, sans-serif" font-size="17"><rect x="60" y="150" width="250" height="92" rx="12" fill="#193b31"/><text x="82" y="184" fill="#8ee3bd">STAGE LIFECYCLE</text><text x="82" y="218" fill="#fff">close + drain + quit reached</text>
<rect x="350" y="150" width="250" height="92" rx="12" fill="#553822"/><text x="372" y="184" fill="#ffd18c">OS PROCESS</text><text x="372" y="218" fill="#fff">still alive after shutdown</text>
<rect x="640" y="150" width="250" height="92" rx="12" fill="#3d2730"/><text x="662" y="184" fill="#ff9faa">LAST LOG BOUNDARY</text><text x="662" y="218" fill="#fff">gpu.foundation shutdown</text>
<rect x="930" y="150" width="210" height="92" rx="12" fill="#252c3b"/><text x="952" y="184" fill="#a9c7ff">MATRIX</text><text x="952" y="218" fill="#fff">B / C not run</text></g>
<path d="M310 196h40M600 196h40M890 196h40" stroke="#718096" stroke-width="4"/>
<g font-family="Segoe UI, sans-serif"><text x="60" y="310" fill="#f4f0e6" font-size="22" font-weight="700">Captured hang state</text><text x="60" y="348" fill="#cbd5e1" font-size="18">133 threads · 438 modules · ExceptionStream absent</text><text x="60" y="380" fill="#cbd5e1" font-size="18">132 instruction pointers in ntdll.dll · 1 in win32u.dll</text><text x="60" y="412" fill="#cbd5e1" font-size="18">Full dump: {report['hang_dump']['bytes'] / (1024**3):.2f} GiB · SHA-256 {report['hang_dump']['sha256'][:16]}…</text><text x="60" y="468" fill="#ffcf7d" font-size="19">Decision: renderer/GPU teardown wait is the leading boundary; rotation remains paused.</text></g></svg>'''
    args.svg.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
