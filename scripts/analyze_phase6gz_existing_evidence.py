"""Read-only Phase 6GX/6GY boundary audit for Phase 6GZ."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase6gz_boundary_contract import classify_historical_candidate


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def candidate_rows(root: Path) -> list[dict]:
    return [row for row in load_jsonl(root / "aggregate.jsonl")
            if row.get("condition") == "B" and row.get("representative") is True]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    gx_root = repo / "artifacts/phase6gx-repetition-1"
    gy_root = repo / "artifacts/phase6gy-repetition-1"
    gx = candidate_rows(gx_root)
    gy = candidate_rows(gy_root)
    for row in gx:
        row["phase"] = "phase6gx"
    for row in gy:
        row["phase"] = "phase6gy"
    all_rows = gx + gy
    primary = [row for row in all_rows if classify_historical_candidate(row["phase"], row["sequence"]) == "primary-unintervened"]
    contaminated = [row for row in all_rows if row not in primary]
    file_evidence = []
    for row in all_rows:
        observed = row.get("temporary_file_cleanup", {}).get("observed", [])
        for item in observed:
            if str(item.get("relative_path", "")).lower().endswith("p3_f0180_temperature.nvdb"):
                file_evidence.append({"phase": row["phase"], "sequence": row["sequence"], "bytes": item.get("bytes")})
    retained = gx_root / "runs/launch02_B/case/p3_f0180_temperature.nvdb"
    dump_files = []
    crash_root = gy_root / "runs/launch23_B/case/sensitive-crash-dumps"
    if crash_root.is_dir():
        for path in sorted(crash_root.iterdir()):
            if path.is_file():
                dump_files.append({"path": str(path.relative_to(repo)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    report = {
        "schema": "campfire.phase6gz.historical-boundary-audit.v1",
        "read_only_sources": [str(gx_root.relative_to(repo)), str(gy_root.relative_to(repo))],
        "frozen_reports_modified": False,
        "primary_population": {
            "definition": "unintervened Candidate B timeout samples",
            "phase6gx_count": sum(row["phase"] == "phase6gx" for row in primary),
            "phase6gy_count": sum(row["phase"] == "phase6gy" for row in primary),
            "total": len(primary),
            "classification_counts": {name: sum(row.get("classification") == name for row in primary)
                                      for name in sorted({row.get("classification") for row in primary})},
            "last_operation_markers": sorted({row.get("last_operation_marker") for row in primary}),
        },
        "contaminated_samples": [{
            "phase": row["phase"], "sequence": row["sequence"], "raw_classification": row.get("classification"),
            "elapsed_seconds": row.get("elapsed_seconds"), "mechanism_inference_classification": "user-intervention-contaminated",
            "natural_second_outcome_claim_allowed": False, "raw_evidence_preserved": True,
        } for row in contaminated],
        "temperature_file_evidence": {
            "observations": file_evidence,
            "unique_sizes_bytes": sorted({item["bytes"] for item in file_evidence if item["bytes"] is not None}),
            "retained_representative": ({"path": str(retained.relative_to(repo)), "bytes": retained.stat().st_size,
                                          "sha256": sha256(retained)} if retained.is_file() else None),
            "interpretation": "The durable temperature file proves execution reached temperature save/poll or later; it does not prove typed read or sampling completed.",
        },
        "saved_crash_material_inventory": dump_files,
        "boundary_table": [
            {"order": 1, "boundary": "public readback return", "status": "confirmed", "basis": "phase6gl_readback_after"},
            {"order": 2, "boundary": "seven-handle count", "status": "confirmed", "basis": "returned_handle_count=7 on marker"},
            {"order": 3, "boundary": "schema handle array/volume metadata", "status": "inferred-complete", "basis": "code order required before requested-channel loop"},
            {"order": 4, "boundary": "raw schema validation", "status": "inferred-complete", "basis": "code order required before requested-channel loop"},
            {"order": 5, "boundary": "velocity save/sample/collector", "status": "inferred-complete", "basis": "velocity precedes temperature and temperature file exists"},
            {"order": 6, "boundary": "temperature buffer_to_volume and save", "status": "confirmed-reached", "basis": "47,641,541-byte temperature file"},
            {"order": 7, "boundary": "temperature typed read or sampling", "status": "unknown-for-primary-timeouts", "basis": "no durable sub-operation markers"},
            {"order": 8, "boundary": "temperature sampling", "status": "boundary-reference-only", "basis": "launch23 saved Python stack; sample is user-intervention-contaminated"},
            {"order": 9, "boundary": "release and lifecycle", "status": "not-reached", "basis": "timeline_playing and operation report remained running"},
        ],
        "conclusion": {
            "confirmed_minimum": "temperature temporary NanoVDB became durable",
            "first_unresolved_boundary": "temperature typed read versus ROI sampling/collector",
            "native_outcome_claim": "31 unintervened samples support timeout reproduction only; launch23 access violation is excluded from mechanism inference",
        },
    }
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > 256 * 1024:
        raise RuntimeError("bounded audit exceeded 256 KiB")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(json.dumps({"passed": len(primary) == 31 and len(contaminated) == 1, "primary": len(primary), "contaminated": len(contaminated)}))
    return 0 if len(primary) == 31 and len(contaminated) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
