"""Read-only audit of the frozen Phase 6EZ C0/C1 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def boundary(raw):
    return next((item["readback_boundary"] for item in raw.get("samples", []) if item.get("readback_boundary")), {})


def active_summary(raw):
    frame = [{"frame": item["frame"], "active_blocks": item["active_blocks"]} for item in raw.get("samples", [])]
    stability = (raw.get("stability_observation") or {}).get("samples", [])
    history = raw.get("flow_liveness_history") or []
    return {
        "sample_frames": frame,
        "stability_count": len(stability),
        "stability_minimum": min((item["active_blocks"] for item in stability), default=None),
        "stability_mean": sum(item["active_blocks"] for item in stability) / len(stability) if stability else None,
        "stability_maximum": max((item["active_blocks"] for item in stability), default=None),
        "stability_unique_values": sorted({item["active_blocks"] for item in stability}),
        "full_history_present": bool(history),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    c0 = load(args.prior_root / "C0_acquire_discard" / "raw.json")
    c1 = load(args.prior_root / "C1_fuel_convert" / "raw.json")
    b0, b1 = boundary(c0), boundary(c1)
    differing_arguments = {
        key: {"c0": c0["arguments"].get(key), "c1": c1["arguments"].get(key)}
        for key in sorted(set(c0["arguments"]) | set(c1["arguments"]))
        if c0["arguments"].get(key) != c1["arguments"].get(key)
    }
    payload_equal = all(
        c0.get("point_payload", {}).get(key) == c1.get("point_payload", {}).get(key)
        for key in ("scenario", "policy", "original_point_count", "active_point_count", "payload_sha256")
    )
    c1_frames = {item["frame"]: item["active_blocks"] for item in c1.get("samples", [])}
    report = {
        "schema": "campfire.phase6fa.phase6ez-read-only-audit.v1",
        "source_root": str(args.prior_root),
        "source_artifacts_modified": False,
        "c0": {
            "raw_sha256": hashlib.sha256((args.prior_root / "C0_acquire_discard" / "raw.json").read_bytes()).hexdigest().upper(),
            "stage_sha256": c0.get("stage_sha256"),
            "point_payload": c0.get("point_payload"),
            "source_sums": c0.get("source_sums"),
            "revision": c0.get("revision"),
            "active_blocks": active_summary(c0),
            "returned_channels": b0.get("channel_objects"),
        },
        "c1": {
            "raw_sha256": hashlib.sha256((args.prior_root / "C1_fuel_convert" / "raw.json").read_bytes()).hexdigest().upper(),
            "stage_sha256": c1.get("stage_sha256"),
            "point_payload": c1.get("point_payload"),
            "source_sums": c1.get("source_sums"),
            "revision": c1.get("revision"),
            "active_blocks": active_summary(c1),
            "returned_channels": b1.get("channel_objects"),
            "numpy_allocation": (b1.get("observable_copy_contract") or {}).get("allocation_classification"),
        },
        "comparison": {
            "stage_sha256_equal": c0.get("stage_sha256") == c1.get("stage_sha256"),
            "point_payload_equal": payload_equal,
            "source_sums_equal": c0.get("source_sums") == c1.get("source_sums"),
            "revision_equal": c0.get("revision") == c1.get("revision"),
            "differing_arguments": differing_arguments,
            "c1_frame30_active_blocks": c1_frames.get(30),
            "c1_readback_frame": 60,
            "c1_collapse_preceded_readback": c1_frames.get(30) == 24,
            "telemetry_stale_unlikely": bool(
                (c1.get("stability_observation") or {}).get("extra_update_count", 0) > 0
                and len({item.get("timeline_time") for item in (c1.get("stability_observation") or {}).get("samples", [])}) > 1
                and (b1.get("channel_objects") or []) != (b0.get("channel_objects") or [])
            ),
        },
        "ranked_hypotheses_before_new_runtime": [
            {"rank": 1, "candidate": "Flow field did not grow because runtime Point-emitter ingestion or fixture lifecycle differed nondeterministically", "status": "strongest inference, not yet direct proof"},
            {"rank": 2, "candidate": "C0/C1 process order or initialization state changed ingestion despite identical offline stage", "status": "plausible"},
            {"rank": 3, "candidate": "observation began too early", "status": "weakened because C1 stayed at 24 through the full running window"},
            {"rank": 4, "candidate": "readback or alias release reduced the field", "status": "cannot explain frame 30, which preceded frame-60 readback"},
            {"rank": 5, "candidate": "numpy.asarray reduced the field", "status": "excluded as the direct initial cause by marker order"},
            {"rank": 6, "candidate": "active-block telemetry was stale", "status": "unlikely; fresh timestamps/timeline and smaller public buffers corroborate a smaller field"},
            {"rank": 7, "candidate": "24 blocks were a meaningful physical steady state", "status": "not accepted without public-field and Emitter liveness evidence"}
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
