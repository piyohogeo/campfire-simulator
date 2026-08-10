"""Record the effective crash-reporting settings of an isolated Kit process."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import carb
import omni.kit.app


KEYS = (
    "/app/uploadDumpsOnStartup",
    "/crashreporter/enabled",
    "/crashreporter/compressDumpFiles",
    "/crashreporter/skipOldDumpUpload",
    "/crashreporter/preserveDump",
    "/crashreporter/gatherUserStory",
    "/crashreporter/devOnlyOverridePrivacyAndForceUpload",
    "/crashreporter/url",
    "/crashreporter/dumpDir",
    "/structuredLog/privacySettingsFile",
    "/privacy/externalBuild",
    "/privacy/performance",
    "/privacy/usage",
    "/privacy/personalization",
    "/privacy/extraDiagnosticDataOptIn",
)


async def _run():
    app = omni.kit.app.get_app()
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/campfire/crashSafety/output")).resolve()
    await app.next_update_async()
    values = {key: settings.get(key) for key in KEYS}
    report = {
        "schema": "campfire.isolated-kit-crash-safety.v1",
        "status": "ok",
        "captured_unix_ns": time.time_ns(),
        "effective_settings": values,
        "gates": {
            "startup_dump_upload_disabled": values["/app/uploadDumpsOnStartup"] is False,
            "old_dump_upload_disabled": values["/crashreporter/skipOldDumpUpload"] is True,
            "compressed_dump_enabled": values["/crashreporter/compressDumpFiles"] is True,
            "forced_upload_disabled": values["/crashreporter/devOnlyOverridePrivacyAndForceUpload"] is False,
            "upload_url_empty": not values["/crashreporter/url"],
            "repo_local_privacy_file_selected": bool(values["/structuredLog/privacySettingsFile"]),
            "performance_consent_disabled": values["/privacy/performance"] is False,
            "preserve_dump_enabled": values["/crashreporter/preserveDump"] is True,
            "interactive_user_story_disabled": values["/crashreporter/gatherUserStory"] is False,
        },
    }
    report["all_gates_passed"] = all(report["gates"].values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    app.post_uncancellable_quit(0 if report["all_gates_passed"] else 1)


asyncio.ensure_future(_run())
