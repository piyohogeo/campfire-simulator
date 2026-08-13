"""Build the Phase 6FO S93/S100 same-camera comparison video."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1280, 720
START_FRAME, END_FRAME, FPS = 180, 359, 12


def _font(size: int, bold=False):
    path = Path("C:/Windows/Fonts") / ("seguisb.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _capture(root: Path, condition: str, frame: int) -> Path:
    return root / "visual" / condition / "frames" / f"frame_{frame:04d}.png"


def _comparison(left: Image.Image, right: Image.Image, frame: int) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#07111d")
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.text((28, 18), "Phase 6FO — Point supply: 93.33% vs 100%", fill="#f8fafc", font=_font(27, True))
    draw.text((28, 55), f"same corrected four-log fixture / camera / RTX / timeline — frame {frame}", fill="#a5b4c7", font=_font(16))
    panel_w, panel_h = 618, 348
    y = 118
    for image, x, color, title, subtitle in (
        (left, 16, "#38bdf8", "S93 · support-clear", "1,344 / 1,440 Points · assumed 5 cm other-log support overlap disabled"),
        (right, 646, "#f59e0b", "S100 · center-clear", "1,440 / 1,440 Points · other-log center intrusion still forbidden"),
    ):
        draw.rectangle((x, 88, x + panel_w, 118), fill=color)
        draw.text((x + 12, 91), title, fill="#06101c", font=_font(18, True))
        canvas.paste(image.convert("RGB").resize((panel_w, panel_h), Image.Resampling.LANCZOS), (x, y))
        draw.text((x + 8, y + panel_h + 12), subtitle, fill="#dbeafe", font=_font(13))
    draw.text((28, 526), "Look at the upper crossed logs, the contact gap, and the far side of each proxy.", fill="#f8fafc", font=_font(20, True))
    draw.text((28, 566), "Decision question: does recovering 96 Points strengthen continuity without adding visible direct penetration?", fill="#cbd5e1", font=_font(17))
    draw.text((28, 608), "The oblique camera exposes both top passage and side detours; numerical deep/flux gates remain authoritative.", fill="#93c5fd", font=_font(15))
    draw.text((28, 657), "Flow 110.0.0 · Candidate Performance RTX · diagnostic default-OFF · production unchanged", fill="#94a3b8", font=_font(14))
    return canvas


def _encode(frames: Path, target: Path) -> dict:
    ffmpeg = shutil.which("ffmpeg.exe") or "C:/tools/ffmpeg/bin/ffmpeg.exe"
    ffprobe = shutil.which("ffprobe.exe") or "C:/tools/ffmpeg/bin/ffprobe.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-framerate", str(FPS), "-i", str(frames / "frame_%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)], check=True)
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(target), "-f", "null", "-"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if decoded.returncode:
        raise RuntimeError(f"Phase 6FO decode verification failed: {decoded.stderr[-1000:]}")
    probe = json.loads(subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames,r_frame_rate:format=duration", "-of", "json", str(target)], check=True, capture_output=True, text=True).stdout)
    stream = probe["streams"][0]
    expected = END_FRAME - START_FRAME + 1
    duration = float(probe["format"]["duration"])
    if int(stream["width"]) != WIDTH or int(stream["height"]) != HEIGHT or int(stream["nb_frames"]) != expected or not 14.9 <= duration <= 15.1:
        raise RuntimeError(f"Unexpected Phase 6FO media metadata: {probe}")
    return {"path": str(target), "sha256": _sha(target), "bytes": target.stat().st_size, "duration_seconds": duration, "frame_count": expected, "width": WIDTH, "height": HEIGHT, "fps": FPS, "full_decode_pass": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--asset-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    if args.work.exists():
        raise FileExistsError(f"Phase 6FO media work refuses reuse: {args.work}")
    frame_dir = args.work / "comparison"
    frame_dir.mkdir(parents=True)
    unique = set()
    for output_index, frame in enumerate(range(START_FRAME, END_FRAME + 1)):
        left_path = _capture(args.root, "S93", frame)
        right_path = _capture(args.root, "S100", frame)
        if not left_path.is_file() or not right_path.is_file():
            raise FileNotFoundError(f"Missing Phase 6FO capture at frame {frame}")
        image = _comparison(Image.open(left_path), Image.open(right_path), frame)
        target = frame_dir / f"frame_{output_index:04d}.png"
        image.save(target)
        unique.add(_sha(target))
    if len(unique) < 150:
        raise RuntimeError(f"Phase 6FO insufficient unique comparison frames: {len(unique)}")
    video = args.asset_dir / "phase6fo_s93_s100_comparison.mp4"
    media = _encode(frame_dir, video)
    poster = args.asset_dir / "phase6fo_s93_s100_comparison_poster.png"
    shutil.copy2(frame_dir / "frame_0179.png", poster)
    manifest = {
        "schema": "campfire.phase6fo.supply-comparison-media.v1",
        "phase": "phase6fo",
        "source_frames_per_condition": 180,
        "comparison_unique_frames": len(unique),
        "same_camera_timeline_flow_rtx": True,
        "media": media,
        "poster": {"path": str(poster), "sha256": _sha(poster), "bytes": poster.stat().st_size},
        "full_decode_verified": True,
        "visually_reviewed": False,
        "latest_demo_updated": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Phase 6FO comparison media encoded and fully decoded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
