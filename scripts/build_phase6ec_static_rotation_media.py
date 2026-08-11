"""Build and validate the Phase 6EC three-condition diagnostic video."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FRAMES = (60, 120, 180, 200)
WIDTH, HEIGHT = 1280, 720


def _font(size: int, bold: bool = False):
    path = Path("C:/Windows/Fonts") / ("seguisb.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def _fit(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    scale = max(size[0] / image.width, size[1] / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - size[0]) // 2
    top = (resized.height - size[1]) // 2
    return resized.crop((left, top, left + size[0], top + size[1]))


def _source(root: Path, label: str, mode: str, frame: int) -> Path:
    return root / "visual" / label / "frames" / f"{mode}_r1_{frame:04d}.png"


def _compose(root: Path, frame: int, report: dict) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#0a111b")
    draw = ImageDraw.Draw(canvas)
    title, subtitle, label, body, small = _font(30, True), _font(18), _font(19, True), _font(17), _font(15)
    draw.text((36, 24), "Phase 6EC — Static rotated Flow CollisionProxy", fill="#f8fafc", font=title)
    draw.text((36, 66), "Same closed Mesh, emitter and Flow settings; only Y rotation or collision switch changes", fill="#a8b6c8", font=subtitle)
    panels = (
        ("axis_on", "phase6ec_rotated_mesh", "Axis aligned · collision ON", "#155e75"),
        ("rotate_y40_on", "phase6ec_rotated_mesh", "Y 40° · collision ON", "#166534"),
        ("rotate_y40_off", "phase6ec_rotated_mesh_collision_off", "Y 40° · collision OFF", "#9a3412"),
    )
    panel_size = (390, 300)
    for index, (folder, mode, heading, color) in enumerate(panels):
        x = 30 + index * 415
        draw.rectangle((x, 108, x + panel_size[0], 140), fill=color)
        draw.text((x + 12, 113), heading, fill="white", font=label)
        canvas.paste(_fit(_source(root, folder, mode, frame), panel_size), (x, 140))
    ratio = report["comparison"]["rotated_on_over_off_core_maximum"]["temperature"]
    ratio_text = "n/a" if ratio is None else f"{ratio:.3g}"
    draw.text((36, 476), f"Simulation sample frame {frame}", fill="#7dd3fc", font=label)
    draw.text((36, 516), "Look for flame/smoke detouring around the blue collision proxy in the center panel.", fill="#e2e8f0", font=body)
    draw.text((36, 550), "The right panel is the positive control: the same rotated proxy is visible but Flow collision is disabled.", fill="#e2e8f0", font=body)
    draw.text((36, 590), f"Public NanoVDB temperature core ratio, rotated ON/OFF: {ratio_text}", fill="#a7f3d0", font=label)
    draw.text((36, 638), "Diagnostic-only Flow stage · no RenderSurface, PhysX sharing, dynamic transform, or production change", fill="#94a3b8", font=small)
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--poster", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.root / "report.json").read_text(encoding="utf-8"))
    work = args.root / "composed-frames"
    work.mkdir(parents=True, exist_ok=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    hashes = []
    for index, frame in enumerate(FRAMES):
        image = _compose(args.root, frame, report)
        target = work / f"frame_{index:04d}.png"
        image.save(target, optimize=True)
        hashes.append(hashlib.sha256(target.read_bytes()).hexdigest())
        if frame == FRAMES[-1]:
            image.save(args.poster, optimize=True)
    if len(set(hashes)) != len(FRAMES):
        raise RuntimeError("Phase 6EC composite frames are not unique")
    ffmpeg = shutil.which("ffmpeg.exe") or "C:/tools/ffmpeg/bin/ffmpeg.exe"
    ffprobe = shutil.which("ffprobe.exe") or "C:/tools/ffmpeg/bin/ffprobe.exe"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-framerate", "0.5", "-i", str(work / "frame_%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.output)],
        check=True,
    )
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames:format=duration", "-of", "json", str(args.output)],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    stream = metadata["streams"][0]
    duration = float(metadata["format"]["duration"])
    if (stream["width"], stream["height"]) != (WIDTH, HEIGHT) or not 7.9 <= duration <= 8.1:
        raise RuntimeError(f"Unexpected Phase 6EC video metadata: {metadata}")
    manifest = {
        "schema": "campfire.phase6ec.media-manifest.v1",
        "phase": "phase6ec",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "video": str(args.output.resolve()),
        "poster": str(args.poster.resolve()),
        "duration_seconds": duration,
        "width": stream["width"],
        "height": stream["height"],
        "encoded_frames": int(stream.get("nb_frames", 0)),
        "sample_frames": list(FRAMES),
        "unique_composite_frames": len(set(hashes)),
        "source_conditions": ["axis_on", "rotate_y40_on", "rotate_y40_off"],
        "visual_review_contract": "actual renderer captures; numeric qualification remains independent",
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
