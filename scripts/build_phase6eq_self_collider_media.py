"""Encode four Phase 6EQ visual conditions and a same-frame comparison."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from build_phase6ep_point_collision_media import END_FRAME, START_FRAME, _encode, _font, _hash


CONDITIONS = (
    ("collision_off", "Collision OFF", "unoccluded positive control", "#ef4444"),
    ("strict_all", "Strict all intersections", "+0.075 m; self and other support clear", "#3b82f6"),
    ("allow_self_support", "Allow self support overlap", "+0.025 m; center remains outside", "#f59e0b"),
    ("allow_self_center", "Allow self center inside", "-0.0125 m; other support still forbidden", "#22c55e"),
)


def _source(root: Path, condition: str, frame: int) -> Path:
    return root / "visual" / condition / "frames" / f"frame_{frame:04d}.png"


def _label(image: Image.Image, title: str, subtitle: str, color: str) -> Image.Image:
    result = image.convert("RGB")
    draw = ImageDraw.Draw(result, "RGBA")
    draw.rectangle((0, 0, 1280, 90), fill=(4, 12, 24, 218))
    draw.rectangle((0, 86, 1280, 90), fill=color)
    draw.text((28, 14), title, font=_font(28, True), fill="white")
    draw.text((28, 53), subtitle, font=_font(17), fill="#cbd5e1")
    return result


def _comparison(images: list[Image.Image], frame: int) -> Image.Image:
    canvas = Image.new("RGB", (1280, 720), "#07111d")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 14), "Phase 6EQ — self-Collider tolerance", font=_font(25, True), fill="#f8fafc")
    draw.text((24, 50), f"same camera / timeline / Flow — frame {frame}", font=_font(15), fill="#94a3b8")
    positions = ((16, 94), (648, 94), (16, 386), (648, 386))
    panel_w, panel_h = 616, 220
    for image, (name, title, subtitle, color), (x, y) in zip(images, CONDITIONS, positions):
        draw.rectangle((x, y, x + panel_w, y + 34), fill=color)
        draw.text((x + 10, y + 5), title, font=_font(16, True), fill="white")
        canvas.paste(image.resize((panel_w, panel_h), Image.Resampling.LANCZOS), (x, y + 34))
        draw.text((x + 8, y + 258), subtitle, font=_font(13), fill="#cbd5e1")
    draw.text((24, 686), "Look for source lift and any flame emerging through the upper log; numeric deep-field gates remain authoritative.", font=_font(14), fill="#e2e8f0")
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--asset-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    if args.work.exists():
        raise RuntimeError(f"Phase 6EQ media work directory exists: {args.work}")
    args.work.mkdir(parents=True)
    directories = {name: args.work / name for name, *_ in CONDITIONS}
    directories["comparison"] = args.work / "comparison"
    for directory in directories.values():
        directory.mkdir()
    unique = {name: set() for name in directories}
    for output_index, frame in enumerate(range(START_FRAME, END_FRAME + 1)):
        raw_images = []
        for name, title, subtitle, color in CONDITIONS:
            source = _source(args.root, name, frame)
            if not source.is_file():
                raise FileNotFoundError(source)
            raw = Image.open(source).convert("RGB")
            raw_images.append(raw)
            labelled = _label(raw, title, subtitle, color)
            target = directories[name] / f"frame_{output_index:04d}.png"
            labelled.save(target)
            unique[name].add(_hash(target))
        comparison = _comparison(raw_images, frame)
        target = directories["comparison"] / f"frame_{output_index:04d}.png"
        comparison.save(target)
        unique["comparison"].add(_hash(target))
    if any(len(values) < 150 for values in unique.values()):
        raise RuntimeError(f"insufficient unique frames: { {key: len(value) for key, value in unique.items()} }")
    args.asset_dir.mkdir(parents=True, exist_ok=True)
    media, posters = {}, {}
    for name, directory in directories.items():
        target = args.asset_dir / f"phase6eq_self_collider_{name}.mp4"
        media[name] = _encode(directory, target)
        poster = args.asset_dir / f"phase6eq_self_collider_{name}_poster.png"
        shutil.copy2(directory / f"frame_{END_FRAME - START_FRAME:04d}.png", poster)
        posters[name] = {"path": str(poster), "sha256": _hash(poster), "bytes": poster.stat().st_size}
    manifest = {
        "schema": "campfire.phase6eq.self-collider-media.v1",
        "phase": "phase6eq",
        "source_frame_count": END_FRAME - START_FRAME + 1,
        "unique_frames": {key: len(value) for key, value in unique.items()},
        "media": media,
        "posters": posters,
        "visually_reviewed": False,
        "latest_demo_updated": False,
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Phase 6EQ media encoded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
