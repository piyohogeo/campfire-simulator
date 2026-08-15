"""Derive the Phase 6HU Collision-OFF visible-Flow baseline probe."""

from __future__ import annotations

from pathlib import Path

from phase6ht_probe_source import build_probe_source as build_phase6ht_source


def build_probe_source(source_path: Path) -> str:
    source = build_phase6ht_source(source_path)
    replacements = (
        (
            "from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics",
            "from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics\nfrom phase6hu_atomic_report import atomic_write_json\nfrom phase6hu_runtime_report import DurableOperationReporter",
        ),
        (
            "EMITTER_CENTER = (0.0, -0.42, 0.0)\nCAMERA_PATH = Sdf.Path(\"/World/Cameras/FlowOcclusion\")\nCAMERA_EYE = (0.0, -4.2, 1.2)\nCAMERA_TARGET = (0.0, -0.42, 0.58)\nCAPTURE_RESOLUTION = (960, 540)",
            "EMITTER_CENTER = (0.0, 0.0, 0.55)\nEMITTER_RADIUS_M = 0.20\nCAMERA_PATH = Sdf.Path(\"/World/Cameras/FlowBaseline\")\nCAMERA_EYE = (2.65, -4.2, 2.35)\nCAMERA_TARGET = (0.0, 0.0, 1.05)\nCAPTURE_RESOLUTION = (1280, 720)",
        ),
        (
            '''def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\\n", encoding="utf-8")
    os.replace(temporary, path)''',
            '''def _write(path: Path, value: dict) -> None:
    atomic_write_json(path, value)''',
        ),
        (
            '    condition = settings.get_as_string("/phase6ht/condition")\n    collision_enabled = condition == "collision_on"\n    if condition not in ("collision_on", "collision_off"):\n        raise RuntimeError("Phase 6HT condition invalid")',
            '    condition = "collision_off"\n    collision_enabled = False',
        ),
        (
            '    exit_code = 1\n\n    def mark(name: str, **values) -> None:\n        record = {"timestamp_utc": _utc(), "name": name, "attempt_id": attempt_id, **values}\n        markers.parent.mkdir(parents=True, exist_ok=True)\n        with markers.open("a", encoding="utf-8") as stream:\n            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\\n")\n            stream.flush()\n            os.fsync(stream.fileno())\n        report["last_marker"] = name\n        _write(output, report)',
            '    exit_code = 1\n    atomic_markers = output.parent / "atomic_report_markers.jsonl"\n    reporter = DurableOperationReporter(output, markers, atomic_markers, report, attempt_id)\n\n    def mark(name: str, **values) -> None:\n        reporter.mark(name, **values)',
        ),
        (
            "    known_good.EMITTER_CENTER = EMITTER_CENTER\n    known_good._define_flow(stage, collision_enabled)",
            "    known_good.EMITTER_CENTER = EMITTER_CENTER\n    known_good.EMITTER_RADIUS_M = EMITTER_RADIUS_M\n    known_good._define_flow(stage, collision_enabled)",
        ),
        (
            '        "diagnostic_phase": "phase6ht",',
            '        "diagnostic_phase": "phase6hu",',
        ),
        (
            '            "source_center_m": list(EMITTER_CENTER),',
            '            "source_center_m": list(EMITTER_CENTER),\n            "source_radius_m": EMITTER_RADIUS_M,',
        ),
        (
            "    finally:\n        try:\n            mark(\"timeline_stop_started\")",
            "    finally:\n        reporter.enter_cleanup()\n        try:\n            mark(\"timeline_stop_started\")",
        ),
        (
            '            _write(output, report)\n        app.post_uncancellable_quit(exit_code)',
            '            reporter.try_final_write()\n        app.post_uncancellable_quit(exit_code)',
        ),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError("Phase 6HU probe replacement cardinality mismatch")
        source = source.replace(before, after)
    return source

