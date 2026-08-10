"""Read-only runtime observer used only by isolated Phase V3T-Q apps."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.ext
import omni.kit.app
import omni.timeline


SETTING_PATHS = (
    "/app/runLoops/main/rateLimitEnabled",
    "/app/runLoops/main/rateLimitFrequency",
    "/app/runLoops/main/syncToPresent",
    "/app/runLoops/rendering_0/rateLimitEnabled",
    "/app/runLoops/rendering_0/rateLimitFrequency",
    "/app/runLoops/rendering_0/syncToPresent",
    "/app/runLoops/present/rateLimitEnabled",
    "/app/runLoops/present/rateLimitFrequency",
    "/app/runLoops/present/syncToPresent",
    "/app/runLoopsGlobal/syncToPresent",
    "/persistent/app/viewport/defaults/tickRate",
    "/persistent/simulation/minFrameRate",
    "/renderer/vsync",
    "/app/vsync",
)


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


class Extension(omni.ext.IExt):
    def on_startup(self, _ext_id):
        self._settings = carb.settings.get_settings()
        output_value = self._settings.get_as_string("/phasev3tq/output")
        self._output = Path(output_value).resolve() if output_value else None
        self._condition = self._settings.get_as_string("/phasev3tq/condition")
        self._app = omni.kit.app.get_app()
        self._timeline = omni.timeline.get_timeline_interface()
        self._started_perf_ns = time.perf_counter_ns()
        self._updates = 0
        self._play_started_perf_ns = None
        self._saw_play = False
        self._stop_captured = False
        self._warmup_captured = False
        self._last_update_perf_ns = None
        self._play_update_intervals_ms = []
        self._snapshots = []
        self._changes = []
        self._last_values = self._settings_values()
        self._manager_surface = sorted(
            name
            for name in dir(self._app.get_extension_manager())
            if not name.startswith("_")
        )
        self._capture("diagnostic_extension_startup")
        self._update_subscription = (
            self._app.get_update_event_stream().create_subscription_to_pop(
                self._on_update, name="campfire-phasev3tq-runtime-observer"
            )
        )
        self._timeline_subscription = (
            self._timeline.get_timeline_event_stream().create_subscription_to_pop(
                self._on_timeline_event,
                name="campfire-phasev3tq-timeline-observer",
            )
        )

    def _settings_values(self):
        return {
            path: _json_value(self._settings.get(path)) for path in SETTING_PATHS
        }

    def _enabled_extension_inventory(self):
        manager = self._app.get_extension_manager()
        result = []
        get_extensions = getattr(manager, "get_extensions", None)
        if get_extensions is None:
            return result
        try:
            extensions = get_extensions()
        except Exception as error:
            return [{"inventory_error": f"{type(error).__name__}: {error}"}]
        for entry in extensions:
            item = _json_value(entry)
            if not isinstance(item, dict):
                continue
            extension_id = item.get("id") or item.get("extension_id")
            package = item.get("package") if isinstance(item.get("package"), dict) else {}
            name = package.get("name") or item.get("name")
            enabled_id = manager.get_enabled_extension_id(str(name)) if name else None
            if extension_id and manager.is_extension_enabled(str(extension_id)):
                result.append(item)
            elif enabled_id:
                result.append(item)
        return result

    def _capture(self, marker):
        now_perf_ns = time.perf_counter_ns()
        snapshot = {
            "marker": marker,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "perf_ns": now_perf_ns,
            "seconds_since_start": (now_perf_ns - self._started_perf_ns) / 1e9,
            "update_index": self._updates,
            "timeline_playing": bool(self._timeline.is_playing()),
            "timeline_seconds": float(self._timeline.get_current_time()),
            "settings": self._settings_values(),
        }
        if marker == "diagnostic_extension_startup":
            snapshot["enabled_extension_inventory"] = self._enabled_extension_inventory()
        self._snapshots.append(snapshot)
        self._write("running")

    def _record_play(self):
        if self._saw_play:
            return
        self._saw_play = True
        self._play_started_perf_ns = time.perf_counter_ns()
        self._last_update_perf_ns = self._play_started_perf_ns
        self._capture("timeline_play")

    def _on_timeline_event(self, _event):
        playing = bool(self._timeline.is_playing())
        if playing:
            self._record_play()
        elif self._saw_play and not self._stop_captured:
            self._stop_captured = True
            self._capture("timeline_stop")
            self._write("ok")

    def _on_update(self, _event):
        update_perf_ns = time.perf_counter_ns()
        self._updates += 1
        values = self._settings_values()
        for path, value in values.items():
            if self._last_values.get(path) != value:
                self._changes.append(
                    {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "update_index": self._updates,
                        "timeline_playing": bool(self._timeline.is_playing()),
                        "path": path,
                        "before": self._last_values.get(path),
                        "after": value,
                    }
                )
        self._last_values = values
        playing = bool(self._timeline.is_playing())
        if playing:
            self._record_play()
            if (
                self._last_update_perf_ns is not None
                and update_perf_ns > self._last_update_perf_ns
            ):
                self._play_update_intervals_ms.append(
                    (update_perf_ns - self._last_update_perf_ns) / 1e6
                )
            self._last_update_perf_ns = update_perf_ns
        if (
            playing
            and not self._warmup_captured
            and self._play_started_perf_ns is not None
            and time.perf_counter_ns() - self._play_started_perf_ns >= 5_000_000_000
        ):
            self._warmup_captured = True
            self._capture("warmup_after_play")

    def _write(self, status):
        if self._output is None:
            return
        report = {
            "schema": "campfire.phasev3tq.runtime-diagnostic.v1",
            "status": status,
            "condition": self._condition,
            "kit": str(self._app.get_kit_version()),
            "app_name": str(self._app.get_app_name()),
            "snapshots": self._snapshots,
            "setting_changes": self._changes,
            "observed_update_count": self._updates,
            "play_update_intervals_ms": self._play_update_intervals_ms,
            "extension_manager_public_surface": self._manager_surface,
            "read_only": True,
            "settings_forced": False,
            "production_app_changed": False,
        }
        self._output.parent.mkdir(parents=True, exist_ok=True)
        self._output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def on_shutdown(self):
        try:
            self._capture("shutdown")
            self._write("ok")
        except Exception as error:
            carb.log_error(
                f"[phasev3tq] Failed to finalize runtime diagnostic: {error}"
            )
        self._timeline_subscription = None
        self._update_subscription = None
