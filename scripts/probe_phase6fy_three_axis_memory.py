"""Phase 6FY synchronization wrapper around the frozen Phase 6FO probe.

The physical stage, Flow evolution, sampling, and lifecycle remain implemented
by ``probe_phase6fo_supply_comparison``.  This wrapper only blocks after that
probe has durably written ``measurement_complete`` until the external bounded
committer acknowledges the pre-close measurement artifact.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import time

import carb

import probe_phase6fo_supply_comparison as shared


_original_append = shared._append_resource_marker


def _synchronized_append(path, marker, *args, **kwargs):
    _original_append(path, marker, *args, **kwargs)
    if marker != "measurement_complete":
        return
    settings = carb.settings.get_settings()
    acknowledgement = Path(settings.get_as_string("/phase6fy/measurementCommitAck")).resolve()
    failure = Path(settings.get_as_string("/phase6fy/measurementCommitFailure")).resolve()
    timeout = float(settings.get_as_float("/phase6fy/measurementCommitTimeoutSeconds") or 60.0)
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if acknowledgement.is_file():
            return
        if failure.is_file():
            raise RuntimeError("Phase 6FY pre-close measurement committer failed")
        time.sleep(0.01)
    raise RuntimeError(f"Phase 6FY pre-close measurement commit exceeded {timeout:.3f} seconds")


shared._append_resource_marker = _synchronized_append
asyncio.ensure_future(shared._run())
