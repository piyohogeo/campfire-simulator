"""Find public omni.stats nodes that numerically match the visible viewport FPS HUD source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    if payload["status"] != "ok":
        raise RuntimeError(payload.get("error", "inventory probe failed"))
    series = {}
    for snapshot in payload["snapshots"]:
        for scope in snapshot["scopes"]:
            scope_name = scope["scope"].get("name", "")
            for index, node in enumerate(scope["nodes"]):
                identity = (scope_name, node.get("name", ""), node.get("description", ""), index)
                series.setdefault(identity, []).append(node.get("value"))
    fps_values = [row["viewport_fps"] for row in payload["snapshots"]]
    exact = []
    candidates = []
    for identity, values in series.items():
        if len(values) != len(fps_values) or not all(_numeric(value) for value in values):
            continue
        errors = [abs(float(value) - fps) for value, fps in zip(values, fps_values)]
        frame_errors = [abs(float(value) - (1000.0 / fps if fps > 0.0 else 0.0)) for value, fps in zip(values, fps_values)]
        row = {
            "scope": identity[0], "name": identity[1], "description": identity[2],
            "values": values, "fps_absolute_error_max": max(errors),
            "overlay_frame_time_absolute_error_max": max(frame_errors),
        }
        text = f"{identity[0]} {identity[1]} {identity[2]}".lower()
        if max(errors) <= 0.05 or max(frame_errors) <= 0.05:
            exact.append(row)
        if "fps" in text or "frame" in text:
            candidates.append(row)
    payload["analysis"] = {
        "scope_count": len(payload["snapshots"][0]["scopes"]) if payload["snapshots"] else 0,
        "total_node_count": sum(scope["total_count"] for scope in payload["snapshots"][0]["scopes"]) if payload["snapshots"] else 0,
        "exact_numeric_matches": exact,
        "name_candidates": candidates,
        "viewport_fps_values": fps_values,
        "conclusion": "matching omni.stats node found" if exact else "no omni.stats node numerically matched the visible viewport FPS HUD source",
    }
    args.input.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["analysis"], ensure_ascii=False))


if __name__ == "__main__":
    main()
