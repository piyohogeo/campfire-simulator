"""Bounded image evidence and comparison media for Phase 6HT."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _rect(shape: tuple[int, int], normalized: list[float]) -> tuple[slice, slice]:
    height, width = shape
    x0, y0, x1, y1 = normalized
    return slice(round(y0 * height), round(y1 * height)), slice(round(x0 * width), round(x1 * width))


def _roi_metrics(delta: np.ndarray, normalized: list[float], threshold: int) -> dict:
    ys, xs = _rect(delta.shape, normalized)
    values = delta[ys, xs]
    return {
        "bounds_normalized": normalized,
        "pixel_count": int(values.size),
        "changed_pixels": int(np.count_nonzero(values >= threshold)),
        "mean_delta": float(np.mean(values)) if values.size else 0.0,
        "maximum_delta": int(np.max(values)) if values.size else 0,
    }


def _condition(root: Path, condition: str, visual: dict) -> dict:
    capture_root = root / condition / "captures"
    baseline_path = capture_root / "baseline.png"
    final_path = capture_root / "final.png"
    baseline = np.asarray(Image.open(baseline_path).convert("RGB"), dtype=np.int16)
    final = np.asarray(Image.open(final_path).convert("RGB"), dtype=np.int16)
    if baseline.shape != final.shape or baseline.shape[:2][::-1] != tuple(visual["capture_resolution"]):
        raise RuntimeError(f"{condition} capture shape mismatch: {baseline.shape} {final.shape}")
    delta = np.max(np.abs(final - baseline), axis=2)
    threshold = int(visual["pixel_change_threshold_per_channel"])
    flow = _roi_metrics(delta, visual["flow_roi_normalized"], threshold)
    direct = _roi_metrics(delta, visual["direct_above_roi_normalized"], threshold)
    sides = [_roi_metrics(delta, bounds, threshold) for bounds in visual["side_rois_normalized"]]
    side = {
        "rois": sides,
        "changed_pixels": sum(value["changed_pixels"] for value in sides),
        "pixel_count": sum(value["pixel_count"] for value in sides),
        "mean_delta": sum(value["mean_delta"] * value["pixel_count"] for value in sides) / max(1, sum(value["pixel_count"] for value in sides)),
        "maximum_delta": max(value["maximum_delta"] for value in sides),
    }
    return {
        "baseline": {"path": str(baseline_path), "sha256": _sha256(baseline_path), "bytes": baseline_path.stat().st_size},
        "final": {"path": str(final_path), "sha256": _sha256(final_path), "bytes": final_path.stat().st_size},
        "resolution": list(baseline.shape[:2][::-1]),
        "flow": flow,
        "direct_above": direct,
        "side": side,
    }


def evaluate(root: Path, contract: dict, human_review: str) -> dict:
    visual = {**contract["visual_measurement"], "capture_resolution": contract["fixed_scene"]["capture_resolution"]}
    conditions = {name: _condition(root, name, visual) for name in ("collision_on", "collision_off")}
    on, off = conditions["collision_on"], conditions["collision_off"]
    on_final = np.asarray(Image.open(on["final"]["path"]).convert("RGB"), dtype=np.int16)
    off_final = np.asarray(Image.open(off["final"]["path"]).convert("RGB"), dtype=np.int16)
    final_delta = np.max(np.abs(on_final - off_final), axis=2)
    threshold = int(visual["pixel_change_threshold_per_channel"])
    final_changed = int(np.count_nonzero(final_delta >= threshold))
    limits = visual["hard_gates"]
    ratios = {
        "direct_changed_pixels": on["direct_above"]["changed_pixels"] / max(1, off["direct_above"]["changed_pixels"]),
        "direct_mean_delta": on["direct_above"]["mean_delta"] / max(1.0e-12, off["direct_above"]["mean_delta"]),
    }
    gates = {
        "off_flow_visible": off["flow"]["changed_pixels"] >= limits["collision_off_flow_changed_pixels_minimum"],
        "off_direct_sensitive": off["direct_above"]["changed_pixels"] >= limits["collision_off_direct_changed_pixels_minimum"],
        "on_flow_not_extinguished": on["flow"]["changed_pixels"] >= limits["collision_on_flow_changed_pixels_minimum"],
        "on_lateral_or_rising_flow": on["side"]["changed_pixels"] >= limits["collision_on_side_changed_pixels_minimum"],
        "direct_pixel_suppression": ratios["direct_changed_pixels"] <= limits["collision_on_to_off_direct_changed_pixel_ratio_maximum"],
        "direct_intensity_suppression": ratios["direct_mean_delta"] <= limits["collision_on_to_off_direct_mean_delta_ratio_maximum"],
        "on_off_visibly_distinct": final_changed >= limits["on_off_final_changed_pixels_minimum"],
    }
    automated = all(gates.values())
    qualified = automated and human_review == "pass"
    return {
        "schema": "campfire.phase6ht.visual-occlusion-evidence.v1",
        "phase": "phase6ht",
        "conditions": conditions,
        "on_to_off_ratios": ratios,
        "on_off_final_changed_pixels": final_changed,
        "automated_gates": gates,
        "automated_pass": automated,
        "human_review": human_review,
        "qualified": qualified,
        "status": "qualified" if qualified else ("awaiting_human_review" if automated and human_review == "pending" else "safe_stop"),
    }


def _font(size: int, bold: bool = False):
    path = Path("C:/Windows/Fonts") / ("seguisb.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def build_comparison(root: Path, report: dict, output: Path) -> None:
    on = Image.open(report["conditions"]["collision_on"]["final"]["path"]).convert("RGB")
    off = Image.open(report["conditions"]["collision_off"]["final"]["path"]).convert("RGB")
    panel = (640, 360)
    canvas = Image.new("RGB", (1320, 460), "#08111d")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 15), "Phase 6HT — static production-hierarchy Flow occlusion", fill="white", font=_font(24, True))
    draw.text((24, 52), "Same log, proxy, source, camera, timeline, and render settings; only Flow collision differs", fill="#a9b8ca", font=_font(16))
    canvas.paste(on.resize(panel, Image.Resampling.LANCZOS), (15, 96))
    canvas.paste(off.resize(panel, Image.Resampling.LANCZOS), (665, 96))
    draw.rectangle((15, 74, 655, 96), fill="#14532d")
    draw.rectangle((665, 74, 1305, 96), fill="#7f1d1d")
    draw.text((26, 75), "Collision ON", fill="white", font=_font(16, True))
    draw.text((676, 75), "Collision OFF — sensitivity control", fill="white", font=_font(16, True))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--human-review", choices=("pending", "pass", "unclear", "fail"), default="pending")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--comparison", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    report = evaluate(args.root, contract, args.human_review)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.comparison is not None:
        build_comparison(args.root, report, args.comparison)
    return 0 if report["status"] in ("qualified", "awaiting_human_review") else 1


if __name__ == "__main__":
    raise SystemExit(main())
