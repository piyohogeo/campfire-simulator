"""Build Phase 6EP OFF, unfiltered, candidate, and comparison videos."""

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
CONDITIONS = (
    ("collision_off", "Collision OFF", "Positive control: source passes the upper log", "#ef4444"),
    ("collision_on_unfiltered", "Collision ON / raw points", "Unfiltered points intersect the source log proxy", "#f59e0b"),
    ("collision_on_candidate", "Collision ON / filtered + offset", "1.5-cell offset; support sphere clears every proxy", "#22c55e"),
)


def _font(size: int, bold: bool = False):
    name = "seguisb.ttf" if bold else "segoeui.ttf"
    path = Path("C:/Windows/Fonts") / name
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _capture(root: Path, condition: str, frame: int) -> Path:
    return root / "visual" / condition / "frames" / f"frame_{frame:04d}.png"


def _label(source: Image.Image, title: str, subtitle: str, color: str) -> Image.Image:
    image = source.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, WIDTH, 92), fill=(5, 12, 22, 215))
    draw.rectangle((0, 88, WIDTH, 92), fill=color)
    draw.text((30, 16), title, fill="white", font=_font(28, True))
    draw.text((30, 54), subtitle, fill="#cbd5e1", font=_font(17))
    return image


def _comparison(images: list[Image.Image], frame: int) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#07111d")
    draw = ImageDraw.Draw(canvas)
    draw.text((30, 18), "Phase 6EP — PointEmitter / CollisionProxy coexistence", fill="#f8fafc", font=_font(26, True))
    draw.text((30, 54), f"same camera / timeline / Flow settings — frame {frame}", fill="#94a3b8", font=_font(16))
    panel_width, panel_height = 408, 230
    x_positions = (14, 436, 858)
    titles = ("OFF", "ON / raw", "ON / candidate")
    colors = ("#ef4444", "#f59e0b", "#22c55e")
    for image, x, title, color in zip(images, x_positions, titles, colors):
        draw.rectangle((x, 102, x + panel_width, 136), fill=color)
        draw.text((x + 12, 106), title, fill="white", font=_font(18, True))
        canvas.paste(image.resize((panel_width, panel_height), Image.Resampling.LANCZOS), (x, 136))
    draw.text((30, 410), "Lower log: Point source    Upper log: collision blocker", fill="#e2e8f0", font=_font(20, True))
    draw.text((30, 452), "Candidate keeps point order and length; unsafe points receive zero fuel / temperature / smoke.", fill="#cbd5e1", font=_font(17))
    draw.text((30, 490), "Chosen offset: 1.5 velocity voxels = 0.075 m    Conservative support radius: 0.050 m", fill="#7dd3fc", font=_font(17))
    draw.text((30, 548), "Look for: source remains visible at the lower surface while the upper log blocks direct passage.", fill="#f8fafc", font=_font(19))
    draw.text((30, 602), "Visual evidence accompanies NanoVDB deep / center and source-supply gates; it is not the gate itself.", fill="#94a3b8", font=_font(16))
    return canvas


def _encode(frames: Path, target: Path) -> dict:
    ffmpeg = shutil.which("ffmpeg.exe") or "C:/tools/ffmpeg/bin/ffmpeg.exe"
    ffprobe = shutil.which("ffprobe.exe") or "C:/tools/ffmpeg/bin/ffprobe.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-framerate", str(FPS), "-i", str(frames / "frame_%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)],
        check=True,
    )
    probe = json.loads(subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames,r_frame_rate:format=duration", "-of", "json", str(target)],
        check=True, capture_output=True, text=True,
    ).stdout)
    stream = probe["streams"][0]
    duration = float(probe["format"]["duration"])
    expected = END_FRAME - START_FRAME + 1
    if int(stream["width"]) != WIDTH or int(stream["height"]) != HEIGHT or int(stream["nb_frames"]) != expected or not 11.9 <= duration <= 12.1:
        raise RuntimeError(f"Unexpected media metadata for {target}: {probe}")
    return {"path": str(target), "sha256": _hash(target), "bytes": target.stat().st_size, "duration_seconds": duration, "frame_count": expected, "width": WIDTH, "height": HEIGHT, "fps": FPS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--asset-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    if args.work.exists():
        raise RuntimeError(f"Phase 6EP media work directory already exists: {args.work}")
    args.work.mkdir(parents=True)
    frame_dirs = {name: args.work / name for name, *_ in CONDITIONS}
    frame_dirs["comparison"] = args.work / "comparison"
    for directory in frame_dirs.values():
        directory.mkdir()
    unique = {name: set() for name in frame_dirs}
    for index, frame in enumerate(range(START_FRAME, END_FRAME + 1)):
        raw_images = []
        for name, title, subtitle, color in CONDITIONS:
            path = _capture(args.root, name, frame)
            if not path.is_file():
                raise FileNotFoundError(f"Missing Phase 6EP capture: {path}")
            raw = Image.open(path).convert("RGB")
            raw_images.append(raw)
            labelled = _label(raw, title, subtitle, color)
            target = frame_dirs[name] / f"frame_{index:04d}.png"
            labelled.save(target)
            unique[name].add(_hash(target))
        comparison = _comparison(raw_images, frame)
        target = frame_dirs["comparison"] / f"frame_{index:04d}.png"
        comparison.save(target)
        unique["comparison"].add(_hash(target))
    if any(len(values) < 150 for values in unique.values()):
        raise RuntimeError(f"Insufficient unique Phase 6EP frames: { {k: len(v) for k, v in unique.items()} }")
    args.asset_dir.mkdir(parents=True, exist_ok=True)
    media = {}
    posters = {}
    for name, directory in frame_dirs.items():
        media[name] = _encode(directory, args.asset_dir / f"phase6ep_point_collision_{name}.mp4")
        poster = args.asset_dir / f"phase6ep_point_collision_{name}_poster.png"
        shutil.copy2(directory / f"frame_{END_FRAME - START_FRAME:04d}.png", poster)
        posters[name] = {"path": str(poster), "sha256": _hash(poster), "bytes": poster.stat().st_size}
    manifest = {
        "schema": "campfire.phase6ep.point-collision-media.v1",
        "phase": "phase6ep",
        "source_frames": END_FRAME - START_FRAME + 1,
        "unique_frames": {name: len(values) for name, values in unique.items()},
        "media": media,
        "posters": posters,
        "visually_reviewed": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Phase 6EP media encoded")


if __name__ == "__main__":
    main()
