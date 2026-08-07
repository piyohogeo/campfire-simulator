"""Record callable metadata for the fixed omni.flowusd native boundary."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import carb
import omni.kit.app
from omni.flowusd import _flowusd


METHODS = (
    "init_persistent_voxelize_context",
    "release_persistent_voxelize_context",
    "voxelize_points_and_sync",
    "voxelize_points_and_sync_v2",
    "voxelize_velocity_points_and_sync",
    "voxelize_velocity_points_and_sync_v2",
    "voxelize_velocity_points_and_sync_v3",
)


def _callable_metadata(method):
    try:
        signature = str(inspect.signature(method))
    except (TypeError, ValueError) as error:
        signature = f"unavailable: {type(error).__name__}: {error}"
    return {
        "repr": repr(method),
        "signature": signature,
        "text_signature": getattr(method, "__text_signature__", None),
        "doc": inspect.getdoc(method),
    }


output = Path(
    carb.settings.get_settings().get_as_string("/phase6br/output")
).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
interface = _flowusd.acquire_flowusd_interface()
try:
    report = {
        "schema_version": 1,
        "phase": "phase6br",
        "status": "ok",
        "production_code_changed": False,
        "methods": {
            name: _callable_metadata(getattr(interface, name)) for name in METHODS
        },
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
finally:
    _flowusd.release_flowusd_interface(interface)
omni.kit.app.get_app().post_uncancellable_quit(0)
