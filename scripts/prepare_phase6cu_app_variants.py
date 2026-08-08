"""Create isolated Phase 6CU Kit app variants without editing production apps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


VARIANTS = (
    "editor_declared_head",
    "editor_declared_tail",
    "campfire_editor_order",
    "campfire_editor_order_window_extensions",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dependency_section(text: str) -> tuple[int, int, list[str]]:
    match = re.search(r"(?ms)^\[dependencies\]\r?\n(.*?)(?=^\[)", text)
    if match is None:
        raise ValueError("Kit app has no [dependencies] section")
    return match.start(1), match.end(1), match.group(1).splitlines()


def _dependency_name(line: str) -> str | None:
    match = re.match(r'^"([^"]+)"\s*=', line.strip())
    return match.group(1) if match else None


def _replace_dependencies(text: str, lines: list[str]) -> str:
    start, end, _ = _dependency_section(text)
    body = "\n".join(lines).rstrip() + "\n\n"
    return text[:start] + body + text[end:]


def _dependency_lines(text: str) -> list[str]:
    _, _, lines = _dependency_section(text)
    return [line for line in lines if _dependency_name(line)]


def _editor_declared(editor_text: str, *, head: bool) -> str:
    lines = _dependency_lines(editor_text)
    additions = [
        '"campfire.app" = {} # Phase 6CU diagnostic declaration',
        '"omni.flowusd" = {} # Phase 6CU diagnostic declaration',
    ]
    lines = additions + lines if head else lines + additions
    return _replace_dependencies(editor_text, lines)


def _campfire_editor_order(
    campfire_text: str,
    editor_text: str,
    *,
    add_window_extensions: bool,
) -> str:
    campfire_lines = _dependency_lines(campfire_text)
    editor_lines = _dependency_lines(editor_text)
    campfire_by_name = {
        _dependency_name(line): line for line in campfire_lines
    }
    editor_names = [_dependency_name(line) for line in editor_lines]
    ordered = [campfire_by_name[name] for name in editor_names if name in campfire_by_name]
    if add_window_extensions:
        window_line = next(
            line
            for line in editor_lines
            if _dependency_name(line) == "omni.kit.window.extensions"
        )
        insert_at = next(
            index
            for index, line in enumerate(ordered)
            if _dependency_name(line) == "omni.kit.window.property"
        )
        ordered.insert(insert_at, window_line + " # Phase 6CU diagnostic addition")
    editor_name_set = set(editor_names)
    ordered.extend(
        line
        for line in campfire_lines
        if _dependency_name(line) not in editor_name_set
    )
    # Keep the proven editor root-app lifecycle and settings so the diagnostic
    # --exec hook remains comparable.  Only substitute Campfire's direct
    # dependency set and its declaration order.
    return _replace_dependencies(editor_text, ordered)


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
    campfire_text = campfire.read_text(encoding="utf-8-sig")
    editor_text = editor.read_text(encoding="utf-8-sig")
    production_sha_before = _sha256(campfire)
    if args.variant == "editor_declared_head":
        result = _editor_declared(editor_text, head=True)
        base = editor
    elif args.variant == "editor_declared_tail":
        result = _editor_declared(editor_text, head=False)
        base = editor
    else:
        result = _campfire_editor_order(
            campfire_text,
            editor_text,
            add_window_extensions=(
                args.variant == "campfire_editor_order_window_extensions"
            ),
        )
        base = editor

    result = result.replace(
        'title = "Kit Base Editor App"',
        f'title = "Phase 6CU {args.variant}"',
        1,
    ).replace(
        'title = "Campfire Simulator"',
        f'title = "Phase 6CU {args.variant}"',
        1,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    production_sha_after = _sha256(campfire)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase": "phase6cu",
                "status": "ok",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "variant": args.variant,
                "base_app": str(base),
                "output_app": str(output),
                "base_sha256": _sha256(base),
                "output_sha256": _sha256(output),
                "production_app_sha256_before": production_sha_before,
                "production_app_sha256_after": production_sha_after,
                "production_changed": production_sha_before != production_sha_after,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
