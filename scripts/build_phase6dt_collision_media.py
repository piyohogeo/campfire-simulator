"""Build the Phase 6DT official-reference comparison media."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FRAMES = (60, 120, 180, 200)
WIDTH, HEIGHT = 1280, 720


def _font(size: int, bold: bool = False):
    name = "seguisb.ttf" if bold else "segoeui.ttf"
    path = Path("C:/Windows/Fonts") / name
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    scale = max(size[0] / image.width, size[1] / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - size[0]) // 2
    top = (resized.height - size[1]) // 2
    return resized.crop((left, top, left + size[0], top + size[1]))


def _compose(off_path: Path, on_path: Path, frame: int) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#07131f")
    draw = ImageDraw.Draw(canvas)
    title = _font(32, True)
    subtitle = _font(20)
    label = _font(22, True)
    body = _font(18)
    small = _font(16)
    draw.text((44, 28), "Phase 6DT — NVIDIA Flow collision reference", fill="#f8fafc", font=title)
    draw.text(
        (44, 74),
        "Same bundled PhysicsCollision.usda · public Flow 110.0.0 path",
        fill="#94a3b8",
        font=subtitle,
    )
    panel_size = (590, 332)
    off = _fit(Image.open(off_path).convert("RGB"), panel_size)
    on = _fit(Image.open(on_path).convert("RGB"), panel_size)
    canvas.paste(off, (44, 145))
    canvas.paste(on, (646, 145))
    draw.rectangle((44, 112, 634, 145), fill="#7f1d1d")
    draw.rectangle((646, 112, 1236, 145), fill="#14532d")
    draw.text((60, 115), "Collision OFF — volume passes through", fill="white", font=label)
    draw.text((662, 115), "Collision ON — volume is blocked", fill="white", font=label)
    draw.text((44, 510), f"Simulation sample frame {frame}", fill="#7dd3fc", font=label)
    draw.text(
        (44, 552),
        "ON / OFF mean ratios: temperature core 0.1677 · above 0.00315 · far above 0",
        fill="#e2e8f0",
        font=body,
    )
    draw.text(
        (44, 587),
        "The sample uses automatic PhysX collision on a Mesh; it does not use a collision emitter.",
        fill="#e2e8f0",
        font=body,
    )
    draw.text(
        (44, 638),
        "Diagnostic evidence only · production unchanged · latest demo pointer unchanged",
        fill="#94a3b8",
        font=small,
    )
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--poster", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    arguments = parser.parse_args()
    arguments.work.mkdir(parents=True, exist_ok=True)
    arguments.poster.parent.mkdir(parents=True, exist_ok=True)
    off_dir = arguments.input / "reference_numeric_off" / "run-1" / "frames"
    on_dir = arguments.input / "reference_numeric_on" / "run-1" / "frames"
    hashes = []
    for index, frame in enumerate(FRAMES):
        image = _compose(
            off_dir / f"reference_numeric_off_r1_{frame:04d}.png",
            on_dir / f"reference_numeric_on_r1_{frame:04d}.png",
            frame,
        )
        target = arguments.work / f"frame_{index:04d}.png"
        image.save(target, optimize=True)
        hashes.append(hash(target.read_bytes()))
        if frame == FRAMES[-1]:
            image.save(arguments.poster, optimize=True)
    if len(set(hashes)) != len(FRAMES):
        raise RuntimeError("Phase 6DT comparison frames are not unique")
    ffmpeg = shutil.which("ffmpeg.exe") or "C:/tools/ffmpeg/bin/ffmpeg.exe"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-framerate",
            "0.5",
            "-i",
            str(arguments.work / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(arguments.video),
        ],
        check=True,
    )
    ffprobe = shutil.which("ffprobe.exe") or "C:/tools/ffmpeg/bin/ffprobe.exe"
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_frames:format=duration",
            "-of",
            "json",
            str(arguments.video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    stream = metadata["streams"][0]
    duration = float(metadata["format"]["duration"])
    if (stream["width"], stream["height"]) != (WIDTH, HEIGHT) or not 7.9 <= duration <= 8.1:
        raise RuntimeError(f"Unexpected Phase 6DT video metadata: {metadata}")
    print(
        "Phase 6DT media written: "
        f"{arguments.video} ({stream.get('nb_frames')} frames, {duration:.3f}s)"
    )


if __name__ == "__main__":
    main()
