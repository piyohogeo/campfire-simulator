"""Create isolated Phase V3T-Q app variants without editing production apps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


DIAGNOSTIC_EXTENSION = "omni.campfire.phasev3tq.diagnostic"
DEVELOPER_LOCK_NAMES = (
    "omni.kit.developer.bundle",
    "omni.kit.dev.utilities.bundle",
    "omni.kit.debug.settings",
)
VARIANTS = {
    "normal_baseline": ("normal", ("omni.kit.developer.bundle",)),
    "normal_without_developer_bundle": ("normal", ()),
    "benchmark_with_developer_bundle": (
        "benchmark",
        ("omni.kit.developer.bundle",),
    ),
    "benchmark_baseline": ("benchmark", ()),
    "normal_debug_python": ("normal_no_dev", ("omni.kit.debug.python",)),
    "normal_debug_python_no_listen": (
        "normal_no_dev",
        ("omni.kit.debug.python",),
    ),
    "normal_debug_vscode": ("normal_no_dev", ("omni.kit.debug.vscode",)),
    "normal_debug_settings": ("normal_no_dev", ("omni.kit.debug.settings",)),
    "normal_developer_windows": (
        "normal_no_dev",
        (
            "omni.kit.window.commands",
            "omni.kit.window.extensions",
            "omni.kit.window.script_editor",
        ),
    ),
    "normal_dev_utilities_bundle": (
        "normal_no_dev",
        ("omni.kit.dev.utilities.bundle",),
    ),
}
VARIANT_SETTINGS = {
    "normal_debug_python_no_listen": {
        "/exts/omni.kit.debug.python/mode": "disabled"
    }
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remove_dependency(text: str, name: str) -> str:
    pattern = rf'(?m)^"{re.escape(name)}"\s*=.*\r?\n'
    return re.sub(pattern, "", text, count=1)


def _remove_enabled_lock(text: str, name: str) -> str:
    pattern = rf'(?m)^\s*"{re.escape(name)}-[^"]+",\s*\r?\n'
    return re.sub(pattern, "", text)


def _add_dependency(text: str, name: str) -> str:
    dependency = f'"{name}" = {{}}'
    dependencies_end = text.find("\n\n", text.index("[dependencies]"))
    existing = re.search(rf'(?m)^"{re.escape(name)}"\s*=', text)
    if existing:
        return text
    return text[:dependencies_end] + "\n" + dependency + text[dependencies_end:]


def _normal_without_developer_bundle(normal_text: str) -> str:
    text = _remove_dependency(normal_text, "omni.kit.developer.bundle")
    for name in DEVELOPER_LOCK_NAMES:
        text = _remove_enabled_lock(text, name)
    return text


def _variant_text(normal_text: str, benchmark_text: str, variant: str) -> str:
    base, dependencies = VARIANTS[variant]
    if base == "normal":
        text = normal_text
    elif base == "benchmark":
        text = benchmark_text
    else:
        text = _normal_without_developer_bundle(normal_text)
    if variant == "normal_without_developer_bundle":
        text = _normal_without_developer_bundle(normal_text)
    for dependency in dependencies:
        text = _add_dependency(text, dependency)
    text = _add_dependency(text, DIAGNOSTIC_EXTENSION)
    settings = VARIANT_SETTINGS.get(variant, {})
    if settings:
        text += "\n[settings.exts.\"omni.kit.debug.python\"]\n"
        text += 'mode = "disabled"\n'
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    normal = args.normal.resolve()
    benchmark = args.benchmark.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    normal_text = normal.read_text(encoding="utf-8")
    benchmark_text = benchmark.read_text(encoding="utf-8")
    rows = []
    for name in VARIANTS:
        destination = output_dir / f"campfire.phasev3tq.{name}.kit"
        destination.write_text(
            _variant_text(normal_text, benchmark_text, name), encoding="utf-8"
        )
        rows.append(
            {
                "condition": name,
                "path": str(destination),
                "sha256": _sha256(destination),
                "base": VARIANTS[name][0],
                "added_dependencies": list(VARIANTS[name][1]),
                "setting_overrides": VARIANT_SETTINGS.get(name, {}),
                "diagnostic_extension": DIAGNOSTIC_EXTENSION,
            }
        )
    manifest = {
        "schema": "campfire.phasev3tq.derived-apps.v1",
        "production_changed": False,
        "normal": {"path": str(normal), "sha256": _sha256(normal)},
        "benchmark": {"path": str(benchmark), "sha256": _sha256(benchmark)},
        "variants": rows,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
