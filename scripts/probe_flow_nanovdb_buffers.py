"""Inspect the fixed Flow build's five point-voxelization buffers.

This default-off Kit probe only calls bundled public Python bindings.  It does
not attach a stage or alter the campfire production extension and scenes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
import omni.volume
from omni.flowusd import _flowusd


def _grid_metadata(flow_interface, volume_interface, buffer):
    grid_data = flow_interface.buffer_to_volume(buffer)
    grid_count = volume_interface.get_num_grids(grid_data)
    return {
        "python_type": type(grid_data).__name__,
        "grid_count": grid_count,
        "grids": [
            {
                "index": index,
                "short_name": volume_interface.get_short_grid_name(grid_data, index),
                "grid_class": volume_interface.get_grid_class(grid_data, index),
                "grid_type": volume_interface.get_grid_type(grid_data, index),
                "index_bounding_box": volume_interface.get_index_bounding_box(
                    grid_data, index
                ),
                "world_bounding_box": volume_interface.get_world_bounding_box(
                    grid_data, index
                ),
            }
            for index in range(grid_count)
        ],
    }


def _buffer_metadata(flow_interface, volume_interface, value, index):
    array = np.asarray(value)
    result = {
        "index": index,
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "element_count": int(array.size),
        "byte_count": int(array.nbytes),
        "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
    }
    try:
        result["volume"] = _grid_metadata(flow_interface, volume_interface, array)
    except Exception as error:
        result["volume_error"] = f"{type(error).__name__}: {error}"
    return result


def _write_report(output, report):
    output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


settings = carb.settings.get_settings()
output = Path(settings.get_as_string("/phase6bs/output")).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
report = {
    "schema_version": 1,
    "phase": "phase6bs",
    "status": "running",
    "default_off": True,
    "production_code_changed": False,
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "scope": (
        "Public fixed-build bindings only; no USD stage, Flow emitter, solver, "
        "or renderer is attached."
    ),
    "cases": [],
}
_write_report(output, report)

flow_interface = None
persistent_context_initialized = False
try:
    points = np.asarray(
        [
            (-0.075, -0.075, 0.0),
            (0.075, -0.075, 0.0),
            (-0.075, 0.075, 0.0),
            (0.075, 0.075, 0.0),
            (-0.075, -0.075, 0.15),
            (0.075, -0.075, 0.15),
            (-0.075, 0.075, 0.15),
            (0.075, 0.075, 0.15),
        ],
        dtype=np.float32,
    )
    identity = np.eye(4, dtype=np.float64).reshape(-1)
    cases = {
        "red_only": (2.0, 0.0, 0.0),
        "green_only": (0.0, 0.8, 0.0),
        "blue_only": (0.0, 0.0, 0.2),
        "rgb": (2.0, 0.8, 0.2),
    }
    flow_interface = _flowusd.acquire_flowusd_interface()
    volume_interface = omni.volume.get_volume_interface()
    flow_interface.init_persistent_voxelize_context()
    persistent_context_initialized = True
    for case_name, color in cases.items():
        colors = np.tile(np.asarray(color, dtype=np.float32), (len(points), 1))
        buffers = flow_interface.voxelize_points_and_sync_v2(
            points,
            colors,
            identity,
            identity,
            0.025,
            64,
        )
        case_report = {
            "name": case_name,
            "input_rgb": list(color),
            "buffer_count": len(buffers),
            "buffers": [],
        }
        report["cases"].append(case_report)
        for index, buffer in enumerate(buffers):
            case_report["buffers"].append(
                _buffer_metadata(flow_interface, volume_interface, buffer, index)
            )
            _write_report(output, report)
    report["status"] = "ok"
except Exception as error:
    report["status"] = "error"
    report["error"] = f"{type(error).__name__}: {error}"
finally:
    if flow_interface is not None:
        if persistent_context_initialized:
            flow_interface.release_persistent_voxelize_context()
        _flowusd.release_flowusd_interface(flow_interface)
    _write_report(output, report)
    omni.kit.app.get_app().post_uncancellable_quit(
        0 if report["status"] == "ok" else 1
    )
