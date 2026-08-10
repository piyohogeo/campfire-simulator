"""Intentionally crash an isolated Kit after persisting safety evidence."""

from __future__ import annotations

import asyncio
import ctypes
import json
import time
from pathlib import Path

import carb
import omni.kit.app


KEYS = (
    "/app/uploadDumpsOnStartup",
    "/crashreporter/devOnlyOverridePrivacyAndForceUpload",
    "/crashreporter/compressDumpFiles",
    "/crashreporter/gatherUserStory",
    "/crashreporter/preserveDump",
    "/crashreporter/skipOldDumpUpload",
    "/crashreporter/url",
    "/privacy/performance",
    "/privacy/personalization",
    "/privacy/usage",
    "/structuredLog/privacySettingsFile",
)


def _durable_write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
        stream.flush()


async def _run():
    app = omni.kit.app.get_app()
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/campfire/crashFixture/output")).resolve()
    marker = Path(settings.get_as_string("/campfire/crashFixture/marker")).resolve()
    library = Path(settings.get_as_string("/campfire/crashFixture/library")).resolve()
    await app.next_update_async()
    values = {key: settings.get(key) for key in KEYS}
    _durable_write(output, {
        "schema": "campfire.isolated-kit-native-crash-fixture.v1",
        "settings": values,
        "expected_exception": "0xC0000005",
        "sensitive_dump_expected": True,
    })
    _durable_write(marker, {
        "marker": "before_intentional_native_access_violation",
        "unix_ns": time.time_ns(),
        "library": str(library),
    })
    trigger_library = ctypes.WinDLL(str(library))
    trigger = trigger_library.phasev3tj_trigger_access_violation
    trigger.argtypes = []
    trigger.restype = ctypes.c_int
    if not trigger():
        raise RuntimeError("failed to start intentional native access-violation thread")
    while True:
        await app.next_update_async()


asyncio.ensure_future(_run())
