"""Bounded interpreter/guard import probe; never launches Kit or the guard."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-interpreter", type=Path, required=True)
    parser.add_argument("--guard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selected = args.selected_interpreter.resolve()
    guard = args.guard.resolve()
    report = {
        "schema": "campfire.phase6hl.guard-interpreter-observation.v1",
        "selected_interpreter": str(selected),
        "sys_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "psutil_imported": False,
        "psutil_file": None,
        "psutil_version": None,
        "guard_path": str(guard),
        "guard_imported": False,
        "guard_resolved_file": None,
        "guard_main_callable": False,
        "errors": [],
    }
    try:
        import psutil

        report["psutil_imported"] = True
        report["psutil_file"] = str(Path(psutil.__file__).resolve())
        report["psutil_version"] = str(psutil.__version__)
    except Exception as error:
        report["errors"].append(f"psutil_import_failed:{type(error).__name__}:{error}")
    if not guard.is_file():
        report["errors"].append("guard_path_missing")
    else:
        inserted = str(guard.parent) not in sys.path
        if inserted:
            sys.path.insert(0, str(guard.parent))
        try:
            spec = importlib.util.spec_from_file_location("campfire_phase6hl_guard_import", guard)
            if spec is None or spec.loader is None:
                raise ImportError("guard module spec has no loader")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            report["guard_imported"] = True
            report["guard_resolved_file"] = str(Path(module.__file__).resolve())
            report["guard_main_callable"] = callable(getattr(module, "main", None))
            if not report["guard_main_callable"]:
                report["errors"].append("guard_main_not_callable")
        except Exception as error:
            report["errors"].append(f"guard_import_failed:{type(error).__name__}:{error}")
        finally:
            if inserted:
                sys.path.pop(0)
    report["status"] = "pass" if not report["errors"] else "fail"
    _write(args.output.resolve(), report)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
