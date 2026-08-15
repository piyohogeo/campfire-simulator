"""Bounded ROI image evidence for Phase 6HV static Flow occlusion."""

from __future__ import annotations

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


def _metrics(values: np.ndarray, threshold: int, bounds: list[float]) -> dict:
    return {
        "bounds_normalized": bounds,
        "pixel_count": int(values.size),
        "changed_pixels": int(np.count_nonzero(values >= threshold)),
        "mean_delta": float(np.mean(values)) if values.size else 0.0,
        "maximum_delta": int(np.max(values)) if values.size else 0,
    }


def _flow_mask(rgb: np.ndarray, definition: dict) -> np.ndarray:
    red, green, blue = (rgb[:, :, index].astype(np.int16) for index in range(3))
    return (
        (red >= definition["red_minimum"])
        & (green >= definition["green_minimum"])
        & (blue <= definition["blue_maximum"])
        & ((green - blue) >= definition["green_minus_blue_minimum"])
        & (red >= green)
        & ((red - green) <= definition["red_minus_green_maximum"])
    )


def _roi(delta: np.ndarray, mask: np.ndarray, bounds: list[float], threshold: int) -> dict:
    ys, xs = _rect(delta.shape, bounds)
    result = _metrics(delta[ys, xs], threshold, bounds)
    result["flow_color_pixels"] = int(np.count_nonzero(mask[ys, xs]))
    return result


def _condition(root: Path, condition: str, visual: dict) -> tuple[dict, np.ndarray, np.ndarray]:
    capture_root = root / condition / "captures"
    baseline_path = capture_root / "baseline.png"
    final_path = capture_root / "final.png"
    baseline = np.asarray(Image.open(baseline_path).convert("RGB"), dtype=np.uint8)
    final = np.asarray(Image.open(final_path).convert("RGB"), dtype=np.uint8)
    if baseline.shape != final.shape or baseline.shape[:2][::-1] != tuple(visual["capture_resolution"]):
        raise RuntimeError(f"{condition} capture shape mismatch: {baseline.shape} {final.shape}")
    delta = np.max(np.abs(final.astype(np.int16) - baseline.astype(np.int16)), axis=2)
    mask = _flow_mask(final, visual["flow_color_mask"])
    threshold = int(visual["pixel_change_threshold_per_channel"])
    rois = {name: _roi(delta, mask, bounds, threshold) for name, bounds in visual["rois_normalized"].items()}
    return ({
        "baseline": {"path": str(baseline_path), "sha256": _sha256(baseline_path), "bytes": baseline_path.stat().st_size},
        "final": {"path": str(final_path), "sha256": _sha256(final_path), "bytes": final_path.stat().st_size},
        "resolution": list(baseline.shape[:2][::-1]),
        "total_changed_pixels": int(np.count_nonzero(delta >= threshold)),
        "total_mean_delta": float(np.mean(delta)),
        "rois": rois,
    }, baseline, final)


def evaluate(root: Path, contract: dict, human_review: str = "pending") -> dict:
    visual = {**contract["visual_measurement"], "capture_resolution": contract["fixed_scene"]["capture_resolution"]}
    off, off_baseline, off_final = _condition(root, "collision_off", visual)
    on, on_baseline, on_final = _condition(root, "collision_on", visual)
    threshold = int(visual["pixel_change_threshold_per_channel"])
    final_delta = np.max(np.abs(on_final.astype(np.int16) - off_final.astype(np.int16)), axis=2)
    baseline_delta = np.max(np.abs(on_baseline.astype(np.int16) - off_baseline.astype(np.int16)), axis=2)
    background = visual["rois_normalized"]["background_control"]
    yb, xb = _rect(final_delta.shape, background)
    background_final = _metrics(final_delta[yb, xb], threshold, background)
    background_baseline = _metrics(baseline_delta[yb, xb], threshold, background)
    off_direct, on_direct = off["rois"]["direct_path"], on["rois"]["direct_path"]
    side_or_upper = on["rois"]["side_left"]["changed_pixels"] + on["rois"]["side_right"]["changed_pixels"] + on["rois"]["upper"]["changed_pixels"]
    ratios = {
        "direct_changed_pixels": on_direct["changed_pixels"] / max(1, off_direct["changed_pixels"]),
        "direct_mean_delta": on_direct["mean_delta"] / max(1.0e-12, off_direct["mean_delta"]),
        "direct_flow_color_pixels": on_direct["flow_color_pixels"] / max(1, off_direct["flow_color_pixels"]),
    }
    limits = visual["hard_gates"]
    gates = {
        "off_total_flow_sensitive": off["total_changed_pixels"] >= limits["collision_off_total_changed_pixels_minimum"],
        "off_direct_path_sensitive": off_direct["changed_pixels"] >= limits["collision_off_direct_changed_pixels_minimum"],
        "off_direct_flow_visible": off_direct["flow_color_pixels"] >= limits["collision_off_direct_flow_color_pixels_minimum"],
        "on_source_near_dynamic": on["rois"]["source_near"]["changed_pixels"] >= limits["collision_on_source_near_changed_pixels_minimum"],
        "on_source_near_visible": on["rois"]["source_near"]["flow_color_pixels"] >= limits["collision_on_source_near_flow_color_pixels_minimum"],
        "on_side_or_upper_flow": side_or_upper >= limits["collision_on_side_or_upper_changed_pixels_minimum"],
        "direct_pixel_suppression": ratios["direct_changed_pixels"] <= limits["collision_on_to_off_direct_changed_pixel_ratio_maximum"],
        "direct_intensity_suppression": ratios["direct_mean_delta"] <= limits["collision_on_to_off_direct_mean_delta_ratio_maximum"],
        "direct_color_suppression": ratios["direct_flow_color_pixels"] <= limits["collision_on_to_off_direct_flow_color_ratio_maximum"],
        "on_off_visibly_distinct": int(np.count_nonzero(final_delta >= threshold)) >= limits["on_off_final_changed_pixels_minimum"],
        "background_final_stable": background_final["changed_pixels"] <= limits["background_final_changed_pixels_maximum"] and background_final["mean_delta"] <= limits["background_final_mean_delta_maximum"],
        "background_baseline_stable": background_baseline["changed_pixels"] <= limits["background_baseline_changed_pixels_maximum"] and background_baseline["mean_delta"] <= limits["background_baseline_mean_delta_maximum"],
    }
    automated = all(gates.values())
    qualified = automated and human_review == "pass"
    return {
        "schema": "campfire.phase6hv.visual-occlusion-evidence.v1",
        "phase": "phase6hv",
        "conditions": {"collision_off": off, "collision_on": on},
        "on_to_off_ratios": ratios,
        "on_side_or_upper_changed_pixels": side_or_upper,
        "on_off_final_changed_pixels": int(np.count_nonzero(final_delta >= threshold)),
        "background_control": {"baseline": background_baseline, "final": background_final},
        "automated_gates": gates,
        "automated_pass": automated,
        "human_review": human_review,
        "qualified": qualified,
        "status": "qualified" if qualified else ("awaiting_human_review" if automated and human_review == "pending" else "safe_stop"),
        "interpretation_limit": "ROI metrics are image-space transport evidence, not a conserved physical flux. Ambiguous human evidence fails closed.",
    }


def _font(size: int, bold: bool = False):
    path = Path("C:/Windows/Fonts") / ("seguisb.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def build_media(root: Path, contract: dict, report: dict, comparison: Path, difference: Path) -> None:
    on = Image.open(report["conditions"]["collision_on"]["final"]["path"]).convert("RGB")
    off = Image.open(report["conditions"]["collision_off"]["final"]["path"]).convert("RGB")
    panel = (640, 360)
    canvas = Image.new("RGB", (1320, 500), "#08111d")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 14), "Phase 6HV — static production-hierarchy Flow occlusion", fill="white", font=_font(24, True))
    draw.text((24, 50), "Fresh OFF / ON processes; only physicsCollisionEnabled differs", fill="#a9b8ca", font=_font(16))
    canvas.paste(off.resize(panel, Image.Resampling.LANCZOS), (15, 105))
    canvas.paste(on.resize(panel, Image.Resampling.LANCZOS), (665, 105))
    draw.text((25, 78), "Collision OFF — sensitivity", fill="#fecaca", font=_font(17, True))
    draw.text((675, 78), "Collision ON — static proxy", fill="#bbf7d0", font=_font(17, True))
    colors = {"direct_path": "#ff3b30", "side_left": "#34c759", "side_right": "#34c759", "upper": "#ffd60a", "background_control": "#64d2ff"}
    width, height = contract["fixed_scene"]["capture_resolution"]
    for offset in (15, 665):
        for name, bounds in contract["visual_measurement"]["rois_normalized"].items():
            if name not in colors:
                continue
            x0, y0, x1, y1 = bounds
            box = (offset + round(x0 * panel[0]), 105 + round(y0 * panel[1]), offset + round(x1 * panel[0]), 105 + round(y1 * panel[1]))
            draw.rectangle(box, outline=colors[name], width=2)
    comparison.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(comparison, optimize=True)
    off_array = np.asarray(off, dtype=np.int16)
    on_array = np.asarray(on, dtype=np.int16)
    delta = np.max(np.abs(on_array - off_array), axis=2).astype(np.uint8)
    heat = np.zeros((*delta.shape, 3), dtype=np.uint8)
    heat[:, :, 0] = np.minimum(255, delta.astype(np.uint16) * 4).astype(np.uint8)
    heat[:, :, 1] = np.minimum(255, np.maximum(0, delta.astype(np.int16) - 24) * 3).astype(np.uint8)
    Image.fromarray(heat, "RGB").save(difference, optimize=True)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--human-review", choices=("pending", "pass", "unclear", "fail"), default="pending")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--difference", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    report = evaluate(args.root, contract, args.human_review)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.comparison is not None and args.difference is not None:
        build_media(args.root, contract, report, args.comparison, args.difference)
    return 0 if report["status"] in ("qualified", "awaiting_human_review") else 1


if __name__ == "__main__":
    raise SystemExit(main())
