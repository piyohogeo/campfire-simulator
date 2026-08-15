"""Temporal Flow-color occupancy and media for Phase 6HW."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _font(size: int, bold: bool = False):
    path = Path("C:/Windows/Fonts") / ("seguisb.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


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


def _rect(shape: tuple[int, int], normalized: list[float]) -> tuple[slice, slice]:
    height, width = shape
    x0, y0, x1, y1 = normalized
    return slice(round(y0 * height), round(y1 * height)), slice(round(x0 * width), round(x1 * width))


def _roi(occupancy: np.ndarray, bounds: list[float], threshold: float) -> dict:
    ys, xs = _rect(occupancy.shape, bounds)
    values = occupancy[ys, xs]
    return {
        "bounds_normalized": bounds,
        "pixel_count": int(values.size),
        "mean_occupancy": float(np.mean(values)) if values.size else 0.0,
        "median_occupancy": float(np.median(values)) if values.size else 0.0,
        "maximum_occupancy": float(np.max(values)) if values.size else 0.0,
        "pixel_fraction_at_threshold": float(np.count_nonzero(values >= threshold) / values.size) if values.size else 0.0,
    }


def _condition(root: Path, condition: str, contract: dict) -> tuple[dict, np.ndarray, np.ndarray, list[np.ndarray]]:
    temporal = contract["temporal_measurement"]
    frames = temporal["stable_window_frames"]
    capture_root = root / condition / "captures"
    arrays: list[np.ndarray] = []
    records = []
    for frame in frames:
        path = capture_root / f"flow_only_f{frame:04d}.png"
        rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
        if tuple(rgb.shape[:2][::-1]) != tuple(contract["fixed_scene"]["capture_resolution"]):
            raise RuntimeError(f"capture resolution mismatch: {path} {rgb.shape}")
        arrays.append(rgb)
        records.append({"frame": frame, "path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size})
    masks = np.stack([_flow_mask(rgb, temporal["flow_color_mask"]) for rgb in arrays], axis=0)
    occupancy = masks.mean(axis=0, dtype=np.float32)
    mean_rgb = np.mean(np.stack(arrays, axis=0).astype(np.float32), axis=0).astype(np.uint8)
    threshold = float(temporal["occupancy_pixel_threshold"])
    rois = {name: _roi(occupancy, bounds, threshold) for name, bounds in temporal["rois_normalized"].items()}
    result = {
        "frames": records,
        "frame_count": len(records),
        "total_mean_occupancy": float(np.mean(occupancy)),
        "total_pixel_fraction_at_threshold": float(np.count_nonzero(occupancy >= threshold) / occupancy.size),
        "rois": rois,
    }
    return result, occupancy, mean_rgb, arrays


def _ratios(on: dict, off: dict) -> dict:
    on_direct, off_direct = on["rois"]["direct_interior"], off["rois"]["direct_interior"]
    on_bypass = max(on["rois"]["left_bypass"]["mean_occupancy"], on["rois"]["right_bypass"]["mean_occupancy"])
    off_bypass = max(off["rois"]["left_bypass"]["mean_occupancy"], off["rois"]["right_bypass"]["mean_occupancy"])
    return {
        "direct_mean_occupancy": on_direct["mean_occupancy"] / max(off_direct["mean_occupancy"], 1.0e-12),
        "direct_pixel_fraction": on_direct["pixel_fraction_at_threshold"] / max(off_direct["pixel_fraction_at_threshold"], 1.0e-12),
        "maximum_bypass_mean_occupancy": on_bypass / max(off_bypass, 1.0e-12),
        "on_maximum_bypass_mean_occupancy": on_bypass,
        "off_maximum_bypass_mean_occupancy": off_bypass,
    }


def evaluate(root: Path, contract: dict, human_review: str = "pending") -> tuple[dict, dict]:
    off, off_occ, off_mean, off_frames = _condition(root, "collision_off", contract)
    on, on_occ, on_mean, on_frames = _condition(root, "collision_on", contract)
    ratios = _ratios(on, off)
    limits = contract["temporal_measurement"]["hard_gates"]
    off_direct = off["rois"]["direct_interior"]
    on_source = on["rois"]["source"]
    background_difference = abs(on["rois"]["background_control"]["mean_occupancy"] - off["rois"]["background_control"]["mean_occupancy"])
    gates = {
        "off_direct_mean": off_direct["mean_occupancy"] >= limits["off_direct_mean_occupancy_minimum"],
        "off_direct_frequency": off_direct["pixel_fraction_at_threshold"] >= limits["off_direct_pixel_fraction_minimum"],
        "on_source_mean": on_source["mean_occupancy"] >= limits["on_source_mean_occupancy_minimum"],
        "on_source_frequency": on_source["pixel_fraction_at_threshold"] >= limits["on_source_pixel_fraction_minimum"],
        "direct_mean_suppression": ratios["direct_mean_occupancy"] <= limits["on_to_off_direct_mean_occupancy_ratio_maximum"],
        "direct_frequency_suppression": ratios["direct_pixel_fraction"] <= limits["on_to_off_direct_pixel_fraction_ratio_maximum"],
        "on_bypass_present": ratios["on_maximum_bypass_mean_occupancy"] >= limits["on_bypass_mean_occupancy_minimum"],
        "on_bypass_increased": ratios["maximum_bypass_mean_occupancy"] >= limits["on_bypass_to_off_ratio_minimum"],
        "on_upper_present": on["rois"]["upper"]["mean_occupancy"] >= limits["on_upper_mean_occupancy_minimum"],
        "on_field_not_extinguished": on["total_mean_occupancy"] >= limits["on_total_mean_occupancy_minimum"],
        "off_background_stable": off["rois"]["background_control"]["mean_occupancy"] <= limits["background_mean_occupancy_maximum"],
        "on_background_stable": on["rois"]["background_control"]["mean_occupancy"] <= limits["background_mean_occupancy_maximum"],
        "background_condition_difference": background_difference <= limits["background_on_off_absolute_difference_maximum"],
    }
    automated = all(gates.values())
    qualified = automated and human_review == "pass"
    report = {
        "schema": "campfire.phase6hw.temporal-occlusion-evidence.v1",
        "phase": "phase6hw",
        "conditions": {"collision_off": off, "collision_on": on},
        "ratios": ratios,
        "background_absolute_difference": background_difference,
        "automated_gates": gates,
        "automated_pass": automated,
        "human_review": human_review,
        "qualified": qualified,
        "status": "qualified" if qualified else ("awaiting_human_review" if automated and human_review == "pending" else "safe_stop"),
        "interpretation_limit": "Rendered Flow-color temporal occupancy is a visual signature, not a conserved physical flux or NanoVDB measurement.",
    }
    arrays = {"off_occ": off_occ, "on_occ": on_occ, "off_mean": off_mean, "on_mean": on_mean, "off_frames": off_frames, "on_frames": on_frames}
    return report, arrays


def _overlay(image: Image.Image, contract: dict, title: str) -> Image.Image:
    result = image.convert("RGB")
    draw = ImageDraw.Draw(result)
    width, height = result.size
    outline = contract["temporal_measurement"]["proxy_outline_normalized"]
    cx, cy = outline["center"]
    rx, ry = outline["radius_x"], outline["radius_y"]
    draw.ellipse(((cx - rx) * width, (cy - ry) * height, (cx + rx) * width, (cy + ry) * height), outline="#f8fafc", width=3)
    colors = {"source": "#ff9f0a", "direct_interior": "#ff453a", "left_bypass": "#30d158", "right_bypass": "#30d158", "upper": "#ffd60a", "background_control": "#64d2ff"}
    for name, bounds in contract["temporal_measurement"]["rois_normalized"].items():
        x0, y0, x1, y1 = bounds
        draw.rectangle((x0 * width, y0 * height, x1 * width, y1 * height), outline=colors[name], width=2)
    draw.rectangle((0, 0, width, 46), fill=(4, 10, 20))
    draw.text((18, 9), title, fill="white", font=_font(22, True))
    return result


def _occupancy_image(occupancy: np.ndarray) -> Image.Image:
    value = np.clip(occupancy * 255.0, 0, 255).astype(np.uint8)
    rgb = np.zeros((*value.shape, 3), dtype=np.uint8)
    rgb[:, :, 0] = value
    rgb[:, :, 1] = np.minimum(255, value.astype(np.uint16) * 2).astype(np.uint8)
    rgb[:, :, 2] = np.maximum(0, value.astype(np.int16) - 160).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def _encode(frame_dir: Path, target: Path, frame_count: int, fps: int = 6) -> dict:
    ffmpeg = shutil.which("ffmpeg.exe") or "C:/tools/ffmpeg/bin/ffmpeg.exe"
    ffprobe = shutil.which("ffprobe.exe") or "C:/tools/ffmpeg/bin/ffprobe.exe"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-framerate", str(fps), "-i", str(frame_dir / "frame_%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(fps), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)], check=True)
    probe = json.loads(subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames,r_frame_rate:format=duration", "-of", "json", str(target)], check=True, capture_output=True, text=True).stdout)
    stream = probe["streams"][0]
    if int(stream["nb_frames"]) != frame_count:
        raise RuntimeError(f"video frame count mismatch: {probe}")
    return {"path": str(target), "sha256": _sha256(target), "bytes": target.stat().st_size, "frame_count": frame_count, "fps": fps, "duration_seconds": float(probe["format"]["duration"]), "width": int(stream["width"]), "height": int(stream["height"])}


def build_media(root: Path, contract: dict, report: dict, arrays: dict, media_dir: Path) -> dict:
    if media_dir.exists():
        raise RuntimeError(f"Phase 6HW media directory reuse refused: {media_dir}")
    media_dir.mkdir(parents=True)
    images = {}
    for condition, prefix in (("collision_off", "off"), ("collision_on", "on")):
        mean = Image.fromarray(arrays[f"{prefix}_mean"], "RGB")
        occupancy = _occupancy_image(arrays[f"{prefix}_occ"])
        for name, image in (("temporal_mean", mean), ("occupancy", occupancy)):
            path = media_dir / f"{condition}_{name}.png"
            _overlay(image, contract, f"{condition.replace('_', ' ').title()} · {name.replace('_', ' ')}").save(path, optimize=True)
            images[f"{condition}_{name}"] = {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
    delta = arrays["off_occ"] - arrays["on_occ"]
    heat = np.zeros((*delta.shape, 3), dtype=np.uint8)
    heat[:, :, 1] = np.clip(np.maximum(delta, 0.0) * 255.0, 0, 255).astype(np.uint8)
    heat[:, :, 0] = np.clip(np.maximum(-delta, 0.0) * 255.0, 0, 255).astype(np.uint8)
    difference = media_dir / "occupancy_difference_off_minus_on.png"
    _overlay(Image.fromarray(heat, "RGB"), contract, "Occupancy difference · green=OFF excess / red=ON excess").save(difference, optimize=True)
    images["occupancy_difference"] = {"path": str(difference), "sha256": _sha256(difference), "bytes": difference.stat().st_size}
    work = media_dir / "comparison_frames"
    work.mkdir()
    frames = contract["temporal_measurement"]["stable_window_frames"]
    for index, frame in enumerate(frames):
        off = _overlay(Image.fromarray(arrays["off_frames"][index], "RGB"), contract, f"Collision OFF · frame {frame}")
        on = _overlay(Image.fromarray(arrays["on_frames"][index], "RGB"), contract, f"Collision ON · frame {frame}")
        panel = (640, 360)
        canvas = Image.new("RGB", (1280, 420), "#07111d")
        canvas.paste(off.resize(panel, Image.Resampling.LANCZOS), (0, 60))
        canvas.paste(on.resize(panel, Image.Resampling.LANCZOS), (640, 60))
        draw = ImageDraw.Draw(canvas)
        draw.text((20, 14), "Phase 6HW · end-on single-log Flow-only comparison", fill="white", font=_font(24, True))
        canvas.save(work / f"frame_{index:04d}.png", optimize=True)
    video = _encode(work, media_dir / "phase6hw_end_on_comparison.mp4", len(frames))
    return {"images": images, "comparison_video": video, "source_frame_count": len(frames)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--media-dir", type=Path, required=True)
    parser.add_argument("--human-review", choices=("pending", "pass", "unclear", "fail"), default="pending")
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    report, arrays = evaluate(args.root, contract, args.human_review)
    report["media"] = build_media(args.root, contract, report, arrays, args.media_dir)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] in ("qualified", "awaiting_human_review") else 1


if __name__ == "__main__":
    raise SystemExit(main())
