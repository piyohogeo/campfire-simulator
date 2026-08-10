"""Aggregate Phase V3T-J crash-evidence and lifecycle observations."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dump-smoke", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    dump_smoke = json.loads(args.dump_smoke.read_text(encoding="utf-8-sig"))
    raw = []
    groups = defaultdict(list)
    for process in manifest["entries"]:
        markers = [json.loads(line) for line in Path(process["markers"]).read_text(encoding="utf-8-sig").splitlines() if line]
        probe = json.loads(Path(process["probe_json"]).read_text(encoding="utf-8-sig"))
        raw.append({"process": process, "probe": probe, "markers": markers})
        groups[(process["transport"], process["scenario"])].append(process)
    invalid = [row["process"]["name"] for row in raw if row["process"]["classification"] != "normal" or row["process"]["probe_status"] != "ok" or not row["process"]["teardown_order_ok"]]
    stage_errors = sum(row["process"]["fatal_log_counts"].get("IRenderSettings::getRenderSettings failed getting a stage-id", 0) for row in raw)
    fatal_errors = sum(sum(row["process"]["fatal_log_counts"].values()) for row in raw)
    dumps = [row["process"]["dump"] for row in raw if row["process"].get("dump")]
    if invalid or stage_errors or fatal_errors or dumps:
        raise RuntimeError(f"invalid Phase V3T-J formal population: invalid={invalid}, stage={stage_errors}, fatal={fatal_errors}, dumps={len(dumps)}")
    summary = []
    for (transport, scenario), rows in groups.items():
        summary.append({
            "transport": transport, "scenario": scenario, "runs": len(rows),
            "normal_exits": sum(row["classification"] == "normal" for row in rows),
            "access_violations": sum(row["classification"] == "access_violation_0xC0000005" for row in rows),
            "teardown_order_pass": sum(row["teardown_order_ok"] for row in rows),
            "fallback_counts": [row["publication"]["fallback_count"] for row in rows],
            "last_markers": sorted({row["last_marker"] for row in rows}),
        })
    report = {
        "schema": "campfire.phasev3tj.gpu-transport-crash-evidence-report.v1",
        "status": "ok",
        "baseline_commit": "a014058",
        "phase1_commit": manifest["phase1_commit"],
        "formal_processes": len(raw),
        "normal_exits": sum(row["process"]["classification"] == "normal" for row in raw),
        "access_violations": 0,
        "full_dumps_created_by_formal_runs": 0,
        "stage_id_errors": stage_errors,
        "fatal_log_errors": fatal_errors,
        "lifecycle_groups": summary,
        "dump_collection": {
            **manifest["dump_collection"],
            "fixture_validation": dump_smoke,
            "formal_dump_directory": str(args.manifest.parent.resolve()),
            "windbg_available": False,
            "windbg_analysis_performed": False,
            "reason": "No Kit access violation was reproduced. WinDbg/cdb/dumpchk were not installed in the fixed environment.",
        },
        "rejected_path": {
            "method": "DEBUG_ONLY_THIS_PROCESS external launcher",
            "result": "rejected before formal population",
            "reason": "RTX RtPso asynchronous compilation remained in a wait loop beyond 200 seconds and the run timed out at 240 seconds.",
            "formal_results_reused": False,
        },
        "combined_non_reproduction": {
            "phase_v3tg_processes": 78,
            "phase_v3tj_formal_processes": len(raw),
            "combined_processes": 78 + len(raw),
            "access_violations": 0,
            "interpretation": "Additional non-reproduction only; it is not proof of safety and does not negate the Phase V3T-F crash.",
        },
        "observed_facts": [
            "The target-local handler fixture produced a full-memory minidump with a Memory64ListStream and a durable SHA-256 record.",
            "All formal Kit processes ran without an attached debugger, exited normally, completed the ordered teardown markers, and emitted no stage-ID, CUDA illegal-address, device-lost, or invalid-pointer marker.",
            "GPU initialization and publication failures fell back to CPU at a complete publication boundary without reusing a faulted GPU pointer.",
        ],
        "strong_inference": [
            "The target-local unhandled-exception filter has negligible steady-state work compared with the rejected debugger-attached path.",
            "The selected probe-owned GPU lifecycle sequences did not reproduce the prior shutdown crash in this fixed environment.",
        ],
        "unconfirmed": [
            "DynamicTextureProvider GPU source-consumed fence and pointer reuse lifetime remain undocumented.",
            "The target process or a later-loaded component could replace the top-level exception filter after the installation marker.",
            "The Phase V3T-F crash root cause, native fault module/offset/stack, and reproducibility remain unknown because no Kit dump was generated.",
        ],
        "decision": "Do not adopt GPU transport in production. Keep the experimental path probe-only and default OFF; reconsider only after a real dump or a documented source-consumed lifetime contract.",
        "production_changed": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "gpu_transport_crash_evidence_samples.json").write_text(json.dumps({"schema": "campfire.phasev3tj.raw.v1", "runs": raw}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "gpu_transport_crash_evidence_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    for index, item in enumerate(summary):
        label = ("CPU" if item["transport"] == "cpu" else "GPU ring3") + " / " + item["scenario"].replace("_", " ")
        y = 190 + index * 50
        rows.append(f'<text x="58" y="{y+22}" class="label">{label}</text><rect x="430" y="{y}" width="300" height="32" rx="8" fill="#34d399"/><text x="750" y="{y+22}" class="value">{item["normal_exits"]} / {item["runs"]} normal</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="690" viewBox="0 0 1100 690" role="img"><style>.title{{font:700 34px Segoe UI,sans-serif;fill:#f8fafc}}.sub{{font:16px Segoe UI,sans-serif;fill:#a7b2c2}}.label{{font:700 15px Segoe UI,sans-serif;fill:#e2e8f0}}.value{{font:700 15px Segoe UI,sans-serif;fill:#f8fafc}}.warn{{font:15px Segoe UI,sans-serif;fill:#fbbf24}}</style><rect width="1100" height="690" rx="28" fill="#0b1625"/><text x="58" y="58" class="sub">PHASE V3T-J / CRASH EVIDENCE</text><text x="58" y="104" class="title">24 normal exits with target-local full-dump arming</text><text x="58" y="138" class="sub">Kit 110.2 / Flow 110.0.0 / RTX 3090 / GPU ring3 remains probe-only</text>{''.join(rows)}<text x="58" y="625" class="warn">0 crashes is not a safety proof. V3T-F root cause and Provider source-consumed lifetime remain unknown.</text><text x="58" y="656" class="sub">Fixture dump: {dump_smoke['size_bytes']:,} bytes · Memory64ListStream present · formal dumps 0</text></svg>'''
    (args.output_dir / "gpu_transport_crash_evidence_report.svg").write_text(svg, encoding="utf-8")
    print(json.dumps({"processes": len(raw), "normal": len(raw), "access_violations": 0, "combined_non_reproduction": 78 + len(raw)}))


if __name__ == "__main__":
    main()
