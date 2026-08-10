"""Phase V3T-O rate-limit diagnostic using the qualified V3T-K scene probe.

The stage, camera, visible-viewport metric, and measurement loop stay identical.
Only the audit list is extended; run-loop settings are supplied before Kit starts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_phasev3tk_rtx_stage_cost as base


base.SETTING_PATHS = base.SETTING_PATHS + (
    "/rtx/rendermode",
    "/rtx/rtpt/maxBounces",
    "/rtx/ambientOcclusion/enabled",
    "/rtx/ambientOcclusion/minSamples",
    "/rtx/ambientOcclusion/maxSamples",
)


asyncio.ensure_future(base._run(base._arguments()))
