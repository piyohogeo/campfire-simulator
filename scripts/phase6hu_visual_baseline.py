"""Bounded image-change evidence for the single Phase 6HU Flow baseline."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def evaluate(root: Path, contract: dict, human_review: str = "pending") -> dict:
    capture_root = root / "collision_off" / "captures"
    baseline_path = capture_root / "baseline.png"
    final_path = capture_root / "final.png"
    baseline = np.asarray(Image.open(baseline_path).convert("RGB"), dtype=np.int16)
    final = np.asarray(Image.open(final_path).convert("RGB"), dtype=np.int16)
    runtime = contract["runtime"]
    expected = tuple(runtime["capture_resolution"])
    if baseline.shape != final.shape or baseline.shape[:2][::-1] != expected:
        raise RuntimeError("Phase 6HU capture shape mismatch")
    delta = np.max(np.abs(final - baseline), axis=2)
    threshold = int(runtime["pixel_change_threshold_per_channel"])
    changed = int(np.count_nonzero(delta >= threshold))
    mean_delta = float(np.mean(delta))
    automated = changed >= int(runtime["changed_pixels_minimum"])
    qualified = automated and human_review == "pass"
    return {
        "schema": "campfire.phase6hu.visible-flow-evidence.v1",
        "phase": "phase6hu",
        "baseline": {"path": str(baseline_path), "bytes": baseline_path.stat().st_size, "sha256": _sha256(baseline_path)},
        "final": {"path": str(final_path), "bytes": final_path.stat().st_size, "sha256": _sha256(final_path)},
        "resolution": list(expected),
        "pixel_change_threshold_per_channel": threshold,
        "changed_pixels": changed,
        "changed_pixels_minimum": int(runtime["changed_pixels_minimum"]),
        "mean_delta": mean_delta,
        "automated_pass": automated,
        "human_review": human_review,
        "qualified": qualified,
        "status": "qualified" if qualified else ("awaiting_human_review" if automated and human_review == "pending" else "safe_stop"),
        "interpretation_limit": "Image change is sensitivity evidence only; human review must identify a visible flame, smoke plume, or Flow volume.",
    }
