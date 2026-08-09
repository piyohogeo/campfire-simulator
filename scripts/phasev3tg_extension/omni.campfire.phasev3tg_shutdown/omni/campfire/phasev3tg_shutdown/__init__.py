"""Real extension-shutdown marker for the isolated Phase V3T-G probe."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import carb
import omni.ext


def _append(name: str, detail: dict | None = None) -> None:
    path = carb.settings.get_settings().get_as_string("/phasev3tg/markers")
    if not path:
        return
    record = {"name": name, "wall_ns": time.time_ns(), "detail": detail or {}}
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8", buffering=1) as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class PhaseV3TGShutdownExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self.ext_id = ext_id
        _append("extension_on_startup")

    def on_shutdown(self):
        _append("extension_on_shutdown_begin")
        _append("extension_on_shutdown_end")

