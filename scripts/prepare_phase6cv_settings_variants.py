"""Create Editor-rooted Phase 6CV variants with isolated Campfire settings."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from prepare_phase6cu_app_variants import _campfire_editor_order


VARIANTS = (
    "all_static",
    "core_only",
    "root_without_extension",
    "app_lifecycle_only",
    "extension_defaults_only",
    "lock_only",
    "static_and_lock",
    "package_only",
    "static_lock_package",
    "full_config_absolute_paths",
)

ROOT_BLOCKS = (
    "settings.persistent.app",
    "settings.app",
    "settings.app.environment",
    "settings.app.viewport.defaults",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _table(text: str, name: str) -> tuple[int, int, str]:
    pattern = rf"(?ms)^\[{re.escape(name)}\]\r?\n(.*?)(?=^\[|\Z)"
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"Kit app has no [{name}] table")
    return match.start(), match.end(), match.group(0).rstrip() + "\n"


def _replace_table(text: str, name: str, replacement: str) -> str:
    start, end, _ = _table(text, name)
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:].lstrip("\r\n")


def _settings_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def _remove_editor_prefixes(editor_settings: str, prefixes: tuple[str, ...]) -> str:
    lines = editor_settings.splitlines()
    kept = []
    for line in lines:
        key = _settings_key(line)
        if key is not None and any(key.startswith(prefix) for prefix in prefixes):
            continue
        kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def _build_variant(
    campfire_text: str,
    editor_text: str,
    variant: str,
    release_root: Path,
) -> str:
    result = _campfire_editor_order(
        campfire_text,
        editor_text,
        add_window_extensions=True,
    )
    _, _, campfire_settings = _table(campfire_text, "settings")
    _, _, editor_settings = _table(result, "settings")
    _, _, extension_defaults = _table(
        campfire_text, 'settings.exts."campfire.app"'
    )
    root_blocks = [_table(campfire_text, name)[2] for name in ROOT_BLOCKS]

    persistent = root_blocks[0]
    app_blocks = root_blocks[1:]
    if variant in (
        "all_static",
        "static_and_lock",
        "static_lock_package",
        "full_config_absolute_paths",
    ):
        ordered_app_blocks = list(app_blocks)
        if variant == "full_config_absolute_paths":
            exts = (release_root / "exts").as_posix()
            extscache = (release_root / "extscache").as_posix()
            search_paths = (
                "[settings.app.exts]\n"
                "folders.'++' = [\n"
                f'    "{exts}",\n'
                f'    "{extscache}"\n'
                "]\n"
            )
            ordered_app_blocks.insert(2, search_paths)
        replacement = "\n".join(
            [persistent, campfire_settings, extension_defaults, *ordered_app_blocks]
        )
    elif variant == "root_without_extension":
        replacement = "\n".join(
            [persistent, campfire_settings, *app_blocks]
        )
    elif variant == "core_only":
        replacement = campfire_settings
    elif variant == "app_lifecycle_only":
        reduced = _remove_editor_prefixes(
            editor_settings,
            ("app.", "persistent.app.viewport."),
        )
        replacement = "\n".join([persistent, reduced, *app_blocks])
    elif variant == "extension_defaults_only":
        replacement = "\n".join([editor_settings, extension_defaults])
    else:
        replacement = editor_settings
    result = _replace_table(result, "settings", replacement)
    if variant in (
        "package_only",
        "static_lock_package",
        "full_config_absolute_paths",
    ):
        _, _, package = _table(campfire_text, "package")
        _, _, template = _table(campfire_text, "template")
        generated_separator = template.find("\n###")
        if generated_separator >= 0:
            template = template[:generated_separator].rstrip() + "\n"
        result = _replace_table(result, "package", package)
        result = result.rstrip() + "\n\n" + template
    if variant in (
        "lock_only",
        "static_and_lock",
        "static_lock_package",
        "full_config_absolute_paths",
    ):
        marker = "# BEGIN GENERATED PART"
        marker_index = campfire_text.find(marker)
        if marker_index < 0:
            raise ValueError("Campfire app has no generated version-lock marker")
        generated_start = campfire_text.rfind("\n", 0, marker_index) + 1
        result = result.rstrip() + "\n\n" + campfire_text[generated_start:].lstrip()
    return result.replace(
        'title = "Kit Base Editor App"',
        f'title = "Phase 6CV {variant}"',
        1,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--campfire-app", type=Path, required=True)
    parser.add_argument("--editor-app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    campfire = args.campfire_app.resolve()
    editor = args.editor_app.resolve()
    output = args.output.resolve()
    manifest = args.manifest.resolve()
    before = _sha256(campfire)
    result = _build_variant(
        campfire.read_text(encoding="utf-8-sig"),
        editor.read_text(encoding="utf-8-sig"),
        args.variant,
        campfire.parent.parent,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    after = _sha256(campfire)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase": "phase6cv",
                "status": "ok",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "variant": args.variant,
                "base_app": str(editor),
                "output_app": str(output),
                "base_sha256": _sha256(editor),
                "output_sha256": _sha256(output),
                "production_app_sha256_before": before,
                "production_app_sha256_after": after,
                "production_changed": before != after,
                "root_app": "editor",
                "generated_version_lock_transplanted": args.variant
                in (
                    "lock_only",
                    "static_and_lock",
                    "static_lock_package",
                    "full_config_absolute_paths",
                ),
                "package_metadata_transplanted": args.variant
                in (
                    "package_only",
                    "static_lock_package",
                    "full_config_absolute_paths",
                ),
                "extension_search_paths_transplanted": args.variant
                == "full_config_absolute_paths",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
