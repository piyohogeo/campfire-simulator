"""Build continuous OFF, ON, and side-by-side Phase 6EO videos."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1280, 720
START_FRAME, END_FRAME, FPS = 21, 200, 15


def _font(size: int, bold: bool = False):
    name = "seguisb.ttf" if bold else "segoeui.ttf"
    path = Path("C:/Windows/Fonts") / name
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _capture(root: Path, condition: str, frame: int) -> Path:
    mode = f"phase6eo_box_mesh_collision_{'off' if condition == 'box_off' else 'on'}"
    return root / "formal" / condition / "frames" / f"{mode}_r1_{frame:04d}.png"


def _label(source: Image.Image, title: str, subtitle: str, color: str) -> Image.Image:
    image = source.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, WIDTH, 92), fill=(5, 12, 22, 210))
    draw.rectangle((0, 88, WIDTH, 92), fill=color)
    draw.text((30, 16), title, fill="white", font=_font(28, True))
    draw.text((30, 54), subtitle, fill="#cbd5e1", font=_font(17))
    return image


def _comparison(off: Image.Image, on: Image.Image, frame: int) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#07111d")
    draw = ImageDraw.Draw(canvas)
    draw.text((34, 20), "Phase 6EO — known-good Mesh Box occlusion", fill="#f8fafc", font=_font(27, True))
    draw.text((34, 58), "Source below Box · same camera/timeline · frame %d" % frame, fill="#94a3b8", font=_font(17))
    panel = (620, 349)
    off = off.resize(panel, Image.Resampling.LANCZOS)
    on = on.resize(panel, Image.Resampling.LANCZOS)
    canvas.paste(off, (15, 132))
    canvas.paste(on, (645, 132))
    draw.rectangle((15, 98, 635, 132), fill="#7f1d1d")
    draw.rectangle((645, 98, 1265, 132), fill="#14532d")
    draw.text((30, 103), "Collision OFF — positive control", fill="white", font=_font(19, True))
    draw.text((660, 103), "Collision ON — closed Mesh proxy", fill="white", font=_font(19, True))
    draw.text((34, 520), "Box center Z=1.00 m · source center Z=0.55 m · support radius 0.10 m", fill="#e2e8f0", font=_font(18))
    draw.text((34, 557), "Surface clearance 0.225 m (4.5 velocity voxels)", fill="#7dd3fc", font=_font(18, True))
    draw.text((34, 610), "OFF reaches the upper region; ON is blocked and diverts laterally.", fill="#e2e8f0", font=_font(20))
    draw.text((34, 657), "Visual evidence paired with exact-Mesh NanoVDB qualification", fill="#94a3b8", font=_font(16))
    return canvas


def _encode(frames: Path, target: Path) -> dict:
    ffmpeg = shutil.which("ffmpeg.exe") or "C:/tools/ffmpeg/bin/ffmpeg.exe"
    ffprobe = shutil.which("ffprobe.exe") or "C:/tools/ffmpeg/bin/ffprobe.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-framerate", str(FPS), "-i", str(frames / "frame_%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)],
        check=True,
    )
    probe = json.loads(
        subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames,r_frame_rate:format=duration", "-of", "json", str(target)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    stream = probe["streams"][0]
    duration = float(probe["format"]["duration"])
    if int(stream["width"]) != WIDTH or int(stream["height"]) != HEIGHT or int(stream["nb_frames"]) != END_FRAME - START_FRAME + 1 or not 11.9 <= duration <= 12.1:
        raise RuntimeError(f"Unexpected media metadata for {target}: {probe}")
    return {"path": str(target), "sha256": _hash(target), "bytes": target.stat().st_size, "duration_seconds": duration, "frame_count": int(stream["nb_frames"]), "width": WIDTH, "height": HEIGHT, "fps": FPS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--asset-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    if args.work.exists():
        raise RuntimeError(f"Phase 6EO media work directory already exists: {args.work}")
    args.work.mkdir(parents=True)
    outputs = {name: args.work / name for name in ("off", "on", "comparison")}
    for directory in outputs.values():
        directory.mkdir()
    unique = {name: set() for name in outputs}
    for index, frame in enumerate(range(START_FRAME, END_FRAME + 1)):
        off_path = _capture(args.root, "box_off", frame)
        on_path = _capture(args.root, "box_on", frame)
        if not off_path.is_file() or not on_path.is_file():
            raise FileNotFoundError(f"Missing capture at frame {frame}")
        off_raw = Image.open(off_path).convert("RGB")
        on_raw = Image.open(on_path).convert("RGB")
        off = _label(off_raw, "Collision OFF — positive control", "Flow passes through the Box volume", "#ef4444")
        on = _label(on_raw, "Collision ON — closed Mesh CollisionProxy", "Flow is blocked and diverts around the Box", "#22c55e")
        frames = {"off": off, "on": on, "comparison": _comparison(off_raw, on_raw, frame)}
        for name, image in frames.items():
            path = outputs[name] / f"frame_{index:04d}.png"
            image.save(path, optimize=True)
            unique[name].add(_hash(path))
    if any(len(values) < 150 for values in unique.values()):
        raise RuntimeError(f"Insufficient unique Phase 6EO frames: { {k: len(v) for k,v in unique.items()} }")
    args.asset_dir.mkdir(parents=True, exist_ok=True)
    media = {
        "collision_off": _encode(outputs["off"], args.asset_dir / "phase6eo_box_collision_off.mp4"),
        "collision_on": _encode(outputs["on"], args.asset_dir / "phase6eo_box_collision_on.mp4"),
        "comparison": _encode(outputs["comparison"], args.asset_dir / "phase6eo_box_collision_comparison.mp4"),
    }
    posters = {}
    for name, directory in outputs.items():
        target = args.asset_dir / f"phase6eo_box_collision_{name}_poster.png"
        shutil.copy2(directory / f"frame_{END_FRAME - START_FRAME:04d}.png", target)
        posters[name] = {"path": str(target), "sha256": _hash(target), "bytes": target.stat().st_size}
    manifest = {
        "schema": "campfire.phase6eo.box-occlusion-media.v1",
        "phase": "phase6eo",
        "source_frames": END_FRAME - START_FRAME + 1,
        "unique_frames": {name: len(values) for name, values in unique.items()},
        "media": media,
        "posters": posters,
        "visually_reviewed": False,
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Phase 6EO media encoded")


if __name__ == "__main__":
    main()
