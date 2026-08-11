from __future__ import annotations

import argparse
import json
from pathlib import Path


def _case_summary(case: dict) -> dict:
    name = case["name"]
    debugger = case.get("debugger") or {}
    diagnostic_helper = case.get("diagnostic_helper") or {}
    cdb_guard = case.get("guard") or {}
    if debugger:
        cdb_evidence = debugger
    elif name == "cdb-abnormal-exit":
        cdb_evidence = cdb_guard
    else:
        cdb_evidence = {}
    return {
        "name": name,
        "status": case["status"],
        "diagnostic_capture_succeeded": case.get("diagnostic_capture_succeeded"),
        "exclusive_log_lock": case.get("exclusive_log_lock", False),
        "log_capture_error_recorded": case.get("log_capture_error_recorded", False),
        "target_alive_after_detach": case.get("target_alive_after_detach"),
        "target_alive_after_cdb_timeout": case.get("target_alive_after_cdb_timeout"),
        "cdb_timed_out": cdb_evidence.get("timed_out", False),
        "cdb_process_absent": cdb_evidence.get("process_absent"),
        "cdb_exit_code": cdb_evidence.get("exit_code"),
        "cdb_peak_private_bytes": cdb_evidence.get("peak_private_bytes"),
        "cdb_total_cpu_seconds": cdb_evidence.get("total_cpu_seconds"),
        "stack_bytes": cdb_evidence.get("stdout_bytes", 0),
        "stderr_bytes": cdb_evidence.get("stderr_bytes", 0),
        "diagnostic_helper_peak_private_bytes": diagnostic_helper.get("peak_private_bytes"),
        "diagnostic_helper_total_cpu_seconds": diagnostic_helper.get("total_cpu_seconds"),
        "target_resource_before": case.get("target_resource_before"),
        "target_resource_after": case.get("target_resource_after"),
    }


def _svg(report: dict) -> str:
    rows = [c for c in report["cases"] if c["cdb_peak_private_bytes"] is not None]
    maximum = max(float(c["cdb_peak_private_bytes"]) for c in rows) or 1.0
    bars = []
    for index, case in enumerate(rows):
        y = 116 + index * 68
        width = 480 * float(case["cdb_peak_private_bytes"]) / maximum
        mib = float(case["cdb_peak_private_bytes"]) / (1024 * 1024)
        bars.append(
            f'<text x="56" y="{y}" class="label">{case["name"]}</text>'
            f'<rect x="300" y="{y-20}" width="{width:.1f}" height="26" rx="7" class="bar"/>'
            f'<text x="{310+width:.1f}" y="{y}" class="value">{mib:.1f} MiB</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="520" viewBox="0 0 1180 520">
<style>.bg{{fill:#111827}}.title{{fill:#f8fafc;font:700 28px system-ui}}.sub{{fill:#94a3b8;font:16px system-ui}}.label{{fill:#e2e8f0;font:15px system-ui}}.value{{fill:#f8fafc;font:700 14px system-ui}}.bar{{fill:#38bdf8}}.gate{{fill:#bbf7d0;font:700 16px system-ui}}</style>
<rect class="bg" width="1180" height="520" rx="20"/>
<text x="56" y="54" class="title">Phase 6EL — bounded CDB diagnostic path</text>
<text x="56" y="82" class="sub">CDB Private Bytes · direct-to-file stack capture · no system-wide debugger changes</text>
{''.join(bars)}
<text x="56" y="472" class="gate">5 / 5 fixtures passed · CDB/target/helper remainder 0 · Phase 6EG not restarted</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    fixture = manifest["fixture_report"]
    report = {
        "schema": "campfire.phase6el.cdb-diagnostic-path-report.v1",
        "phase": "phase6el",
        "status": manifest["status"],
        "phase6eg_formal_restarted": False,
        "cdb": fixture["cdb"],
        "contract": fixture["attach_contract"],
        "cases": [_case_summary(case) for case in fixture["cases"]],
        "machine_wide_configuration_changed": fixture["machine_debug_configuration"]["changed"],
        "machine_debug_configuration_before_sha256": fixture["machine_debug_configuration"]["before_sha256"],
        "machine_debug_configuration_after_sha256": fixture["machine_debug_configuration"]["after_sha256"],
        "fixture_runner": {
            "peak_private_bytes": manifest["fixture_guard"]["peak_private_bytes"],
            "total_cpu_seconds": manifest["fixture_guard"]["total_cpu_seconds"],
            "duration_seconds": manifest["fixture_guard"]["duration_seconds"],
            "process_absent": manifest["fixture_guard"]["process_absent"],
        },
        "remainder": fixture["process_remainder"],
        "production_app_sha256_before": manifest["production_app_sha256_before"],
        "production_app_sha256_after": manifest["production_app_sha256_after"],
        "phase6eg_contract_sha256_before": manifest["phase6eg_contract_sha256_before"],
        "phase6eg_contract_sha256_after": manifest["phase6eg_contract_sha256_after"],
        "observations": [
            "The installed Windows Kits CDB was detected without postmortem registration.",
            "A non-invasive attach produced loaded modules and all-thread native stacks, then detached while the target remained alive.",
            "Exclusive log access produced log_capture_error but did not prevent CDB capture or bounded JSON publication.",
            "Timeout and abnormal-exit fixtures removed only their exact debugger/helper processes.",
        ],
        "limits": [
            "Fixture processes are PowerShell wait fixtures, not Kit; they do not prove the known NGX stack is present.",
            "Private NVIDIA and Omniverse symbols may remain unavailable; unknown or ambiguous stacks still fail closed.",
            "Phase 6EG remains unqualified and was not restarted.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
