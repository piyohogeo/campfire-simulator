"""Build the reproducible Phase 6EO primitive-source stage offline.

The formal ON/OFF processes both flatten this byte-identical stage, disable the
display Cube's collision, and add the same closed Mesh CollisionProxy before
the stage is connected to Kit.  Only Flow's collision switch differs.
"""

from __future__ import annotations

import importlib.util
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app


def _load_phase6ds():
    path = Path(__file__).with_name("probe_phase6ds_flow_collision.py")
    spec = importlib.util.spec_from_file_location("campfire_phase6ds_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Phase 6DS source builder: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _main() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6eo/sourceStage")).resolve()
    report_path = Path(settings.get_as_string("/phase6eo/preflightReport")).resolve()
    if output.exists() or report_path.exists():
        raise RuntimeError("Phase 6EO source preparation refuses output reuse")
    output.parent.mkdir(parents=True, exist_ok=True)
    phase6ds = _load_phase6ds()
    audit = phase6ds._build_stage(output, True, 0.0)
    payload = {
        "schema": "campfire.phase6eo.box-source-preflight.v1",
        "phase": "phase6eo",
        "status": "ok",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "stage": str(output),
        "audit": audit,
        "contract": {
            "axis_aligned": True,
            "dimensions_m": [2.0, 2.0, 0.25],
            "emitter_center_m": [0.0, 0.0, 0.55],
            "emitter_radius_m": 0.1,
            "minimum_surface_clearance_m": 0.225,
            "density_cell_size_m": 0.025,
        },
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    omni.kit.app.get_app().post_uncancellable_quit(0)


if carb.settings.get_settings().get_as_string("/phase6eo/sourceStage"):
    try:
        _main()
    except Exception:
        traceback.print_exc()
        omni.kit.app.get_app().post_uncancellable_quit(1)
