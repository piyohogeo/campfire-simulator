"""Measure one profiler-off FlowUsd StageUpdate enablement case.

The probe creates the complete Resident Point stage offline, configures the
FlowUsd StageUpdate node before connecting that stage, and restores the node
before process exit.  It is a default-off derived diagnostic; it does not
change the production application or publication contracts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import carb
import carb.profiler
import omni.kit.app
import omni.kit.viewport.utility
import omni.stageupdate
import omni.timeline
import omni.usd
from omni.flowusd import _flowusd
from pxr import Tf, Usd

import campfire.app
from campfire.app.phase3_scene import (
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_MODEL_DT_SECONDS,
)


FLOW_NODE_NAME = "FlowUsd"
FLOW_VERSION = "110.0.0"
LOG_IDS = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
TOTAL_TICKS = 500
STEPS_PER_UPDATE = 5
UPDATE_WARMUP = 20
EDIT_TICK = 345
CAPTURE_RESOLUTION = (1280, 720)


def _settings() -> tuple[carb.settings.ISettings, dict]:
    settings = carb.settings.get_settings()
    return settings, {
        "output": Path(settings.get_as_string("/phase6df/output")),
        "scene": Path(settings.get_as_string("/phase6df/scene")),
        "native_library": Path(
            settings.get_as_string("/phase6df/nativeLibrary")
        ),
        "flow_usd_enabled": bool(
            settings.get_as_bool("/phase6df/flowUsdEnabled")
        ),
        "label": settings.get_as_string("/phase6df/label"),
    }


def _write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _node_records(interface) -> list[dict]:
    return [
        {
            "index": int(node["index"]),
            "name": str(node["name"]),
            "enabled": bool(node["enabled"]),
            "order": int(node["order"]),
        }
        for node in interface.get_stage_update_nodes()
    ]


def _flow_node(interface) -> dict:
    matches = [node for node in _node_records(interface) if node["name"] == FLOW_NODE_NAME]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one FlowUsd StageUpdate node, got {matches}")
    return matches[0]


def _hash_array(np, value, dtype) -> dict:
    array = np.asarray(value, dtype=dtype)
    return {
        "count": int(array.size),
        "bytes": int(array.nbytes),
        "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    }


def _hash_native_state(backend) -> str:
    digest = hashlib.sha256()
    for name in sorted(backend._arrays):
        digest.update(name.encode("ascii"))
        digest.update(backend._arrays[name].tobytes(order="C"))
    digest.update(backend._elapsed.tobytes(order="C"))
    digest.update(backend._cumulative.tobytes(order="C"))
    digest.update(backend._published_output.tobytes(order="C"))
    digest.update(str((backend.revision, backend.status()["tick"])).encode("ascii"))
    return digest.hexdigest()


def _point_hashes(stage, np) -> dict:
    emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
    return {
        "positions": _hash_array(
            np, emitter.GetAttribute("pointPositions").Get(), np.float32
        ),
        "fuels": _hash_array(np, emitter.GetAttribute("pointFuels").Get(), np.float32),
        "temperatures": _hash_array(
            np, emitter.GetAttribute("pointTemperatures").Get(), np.float32
        ),
        "smokes": _hash_array(np, emitter.GetAttribute("pointSmokes").Get(), np.float32),
        "resident_revision": int(
            emitter.GetAttribute("campfire:residentRevision").Get()
        ),
        "layout_revision": int(
            emitter.GetAttribute("campfire:layoutRevision").Get()
        ),
    }


def _readback(flow_interface, np) -> dict:
    names = ("temperature", "fuel", "burn", "smoke", "velocity", "divergence")
    raw = flow_interface.get_latest_nanovdb_readback()
    result = {}
    for index, name in enumerate(names):
        value = raw[index] if index < len(raw) else []
        result[name] = _hash_array(np, value, np.uint32)
    return result


def _make_offline_stage(scene_path: Path, native_library: Path):
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.unlink(missing_ok=True)
    stage = Usd.Stage.CreateNew(str(scene_path))
    campfire.app.populate_phase3_scene(stage)
    models = tuple(
        campfire.app.load_model_from_prim(stage.GetPrimAtPath(f"/World/Logs/{log_id}"))
        for log_id in LOG_IDS
    )
    backend = campfire.app.ResidentNativeBackend(
        models,
        native_library,
        dt_seconds=PHASE3_MODEL_DT_SECONDS,
        heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    )
    layout = campfire.app.resident_point_layout_for_logs(stage, LOG_IDS)
    producer = campfire.app.ResidentNativeSurfaceProducer(
        backend, layout["origins"], layout["axes"]
    )
    producer.build_layout()
    scene_contract = campfire.app.configure_resident_point_application_scene(
        stage, producer.positions
    )
    campfire.app.preauthor_resident_snapshot_consumers(stage, LOG_IDS)
    stage.GetRootLayer().customLayerData = {
        **stage.GetRootLayer().customLayerData,
        "campfire:phase": "phase6df",
        "campfire:flowVersion": FLOW_VERSION,
        "campfire:stageBuiltBeforeConnection": True,
        "campfire:derivedDiagnostic": True,
    }
    if not stage.GetRootLayer().Save():
        raise RuntimeError(f"Unable to save Phase 6DF stage: {scene_path}")
    del producer
    del stage
    return backend, layout, scene_contract


async def _close_current_stage(context) -> dict:
    existing = context.get_stage()
    if existing is None:
        return {"stage_existed": False, "closed": True, "error": None}
    closed, error = await context.close_stage_async()
    if not closed or error:
        raise RuntimeError(f"Unable to close initial stage: {error}")
    for _ in range(4):
        await omni.kit.app.get_app().next_update_async()
    return {"stage_existed": True, "closed": bool(closed), "error": str(error)}


async def _prepare_viewport(app) -> dict:
    viewport = None
    for _ in range(120):
        viewport = omni.kit.viewport.utility.get_active_viewport()
        if viewport is not None:
            break
        await app.next_update_async()
    if viewport is None:
        raise RuntimeError("Phase 6DF requires an active viewport")
    viewport.camera_path = campfire.app.CAMERA_PATH
    viewport.fill_frame = False
    viewport.resolution = CAPTURE_RESOLUTION
    viewport.updates_enabled = True
    await omni.kit.viewport.utility.next_viewport_frame_async(viewport)
    return {
        "camera_path": str(viewport.camera_path),
        "resolution": [int(value) for value in viewport.resolution],
        "updates_enabled": bool(viewport.updates_enabled),
    }


async def _run() -> None:
    settings, arguments = _settings()
    output = arguments["output"].resolve()
    report = {
        "schema_version": 1,
        "phase": "phase6df",
        "status": "running",
        "label": arguments["label"],
        "flow_usd_enabled": arguments["flow_usd_enabled"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write(output, report)

    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    stage_update = omni.stageupdate.get_stage_update_interface()
    profiler = carb.profiler.acquire_profiler_interface()
    flow_interface = None
    owner = None
    listener = None
    backend = None
    target_stage_connected = False
    node_restored = False
    exit_code = 1
    try:
        if not arguments["output"].name or not arguments["label"]:
            raise ValueError("Phase 6DF output and label are required")
        capture_mask_before = int(profiler.get_capture_mask())
        if capture_mask_before != 0:
            raise RuntimeError("Phase 6DF performance run requires profiler mask 0")
        backend, layout, scene_contract = _make_offline_stage(
            arguments["scene"].resolve(), arguments["native_library"].resolve()
        )
        initial_stage = await _close_current_stage(context)
        node_initial = _flow_node(stage_update)
        stage_update.set_stage_update_node_enabled(
            node_initial["index"], arguments["flow_usd_enabled"]
        )
        node_before_connection = _flow_node(stage_update)

        opened, open_error = await context.open_stage_async(
            str(arguments["scene"].resolve())
        )
        if not opened or open_error:
            raise RuntimeError(f"Unable to open Phase 6DF stage: {open_error}")
        target_stage_connected = True
        stage = context.get_stage()
        owner = campfire.app.ResidentPointApplicationOwner.compose(
            backend,
            stage,
            context,
            timeline,
            app.next_update_async,
            layout,
            track_dynamic_translation=True,
            skip_unchanged_translation_layout=True,
        )
        viewport_contract = await _prepare_viewport(app)
        np = backend._np
        point_prefix = str(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        point_resyncs = []
        point_changes = []

        def observe(notice, _sender):
            point_resyncs.extend(
                str(path)
                for path in notice.GetResyncedPaths()
                if str(path).startswith(point_prefix)
            )
            point_changes.extend(
                str(path)
                for path in notice.GetChangedInfoOnlyPaths()
                if str(path).startswith(point_prefix)
            )

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, observe, stage)
        flow_interface = _flowusd.acquire_flowusd_interface()
        timeline.stop()
        timeline.set_current_time(0.0)
        timeline.set_auto_update(True)
        timeline.set_looping(True)
        timeline.commit()
        owner.start()
        timeline.play()
        timeline.commit()

        update_records = []
        update_durations = []
        changed_update_durations = []
        unchanged_update_durations = []
        emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        prior_layout_revision = int(
            emitter.GetAttribute("campfire:layoutRevision").Get()
        )
        for tick in range(1, TOTAL_TICKS + 1):
            if tick == EDIT_TICK:
                origin = campfire.app.get_log_world_position(
                    stage, campfire.app.PHASE3_DRY_LOG_ID
                )
                campfire.app.move_log(
                    stage,
                    campfire.app.PHASE3_DRY_LOG_ID,
                    (origin[0], origin[1] + 0.02, origin[2]),
                    0.0,
                )
            owner.step()
            if tick % STEPS_PER_UPDATE:
                continue
            started = time.perf_counter_ns()
            await app.next_update_async()
            duration_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
            revision = int(emitter.GetAttribute("campfire:residentRevision").Get())
            layout_revision = int(
                emitter.GetAttribute("campfire:layoutRevision").Get()
            )
            layout_changed = layout_revision > prior_layout_revision
            active_blocks = int(flow_interface.get_active_block_count())
            record = {
                "update": len(update_records) + 1,
                "tick": tick,
                "revision": revision,
                "layout_revision": layout_revision,
                "layout_changed": layout_changed,
                "duration_ms": round(duration_ms, 6),
                "active_blocks": active_blocks,
                "timeline_playing": bool(timeline.is_playing()),
            }
            update_records.append(record)
            update_durations.append(duration_ms)
            if len(update_records) > UPDATE_WARMUP:
                target = (
                    changed_update_durations
                    if layout_changed
                    else unchanged_update_durations
                )
                target.append(duration_ms)
            prior_layout_revision = layout_revision

        running_status = owner.status()
        native_state_sha256 = _hash_native_state(backend)
        point_hashes = _point_hashes(stage, np)
        readback = _readback(flow_interface, np)
        timeline.pause()
        timeline.commit()
        owner.stop()
        stopped_status = owner.status()
        revisions = [
            int(stopped_status["session"][name]["revision"])
            for name in ("backend", "adapter", "sidecar")
        ]
        sidecar = stopped_status["session"]["sidecar"]
        allowed_changes = {
            f"{point_prefix}.pointPositions",
            f"{point_prefix}.pointFuels",
            f"{point_prefix}.pointTemperatures",
            f"{point_prefix}.pointSmokes",
            f"{point_prefix}.campfire:layoutRevision",
            f"{point_prefix}.campfire:residentRevision",
        }
        unexpected_changes = sorted(set(point_changes).difference(allowed_changes))
        active_blocks = [record["active_blocks"] for record in update_records]
        readback_nonempty = {
            name: value["count"] > 0 for name, value in readback.items()
        }
        expected_flow_state = (
            max(active_blocks) > 0
            and all(readback_nonempty[name] for name in ("temperature", "fuel", "burn", "smoke", "velocity"))
            if arguments["flow_usd_enabled"]
            else max(active_blocks) == 0
            and not any(readback_nonempty.values())
        )
        gates = {
            "flow_node_initially_enabled": node_initial["enabled"],
            "flow_node_configured_before_target_connection": (
                node_before_connection["enabled"]
                == arguments["flow_usd_enabled"]
            ),
            "offline_point_graph_complete": (
                scene_contract["point_count"] == 720
                and scene_contract["emitter_count"] == 1
            ),
            "profiler_capture_disabled": (
                capture_mask_before == 0 and int(profiler.get_capture_mask()) == 0
            ),
            "all_revisions_committed": revisions == [TOTAL_TICKS] * 3,
            "all_publications_succeeded": (
                sidecar["prepare_count"] == TOTAL_TICKS
                and sidecar["publish_count"] == TOTAL_TICKS
                and sidecar["failure_count"] == 0
                and sidecar["rollback_count"] == 0
            ),
            "dynamic_layout_was_published": sidecar[
                "live_translation_publish_count"
            ] > 0,
            "no_point_resync_or_unexpected_change": (
                not point_resyncs and not unexpected_changes
            ),
            "timeline_remained_playing": all(
                record["timeline_playing"] for record in update_records
            ),
            "update_samples_exact": len(update_records)
            == TOTAL_TICKS // STEPS_PER_UPDATE,
            "flow_state_matches_node_enablement": expected_flow_state,
        }
        report.update(
            {
                "status": "ok" if all(gates.values()) else "failed",
                "runtime": {
                    "kit_version": str(app.get_kit_version()),
                    "app_name": str(app.get_app_name()),
                    "flow_version": FLOW_VERSION,
                    "profiler_capture_mask": int(profiler.get_capture_mask()),
                    "viewport": viewport_contract,
                },
                "control": {
                    "initial_stage": initial_stage,
                    "node_initial": node_initial,
                    "node_before_target_connection": node_before_connection,
                    "node_restored": None,
                    "target_stage_built_offline": True,
                },
                "publication": {
                    "revisions": revisions,
                    "point_resyncs": point_resyncs,
                    "unexpected_point_changes": unexpected_changes,
                    "point_change_count": len(point_changes),
                    "sidecar": sidecar,
                },
                "update": {
                    "records": update_records,
                    "all_ms": campfire.app.summarize_timing_ms(
                        update_durations, UPDATE_WARMUP
                    ),
                    "changed_ms": campfire.app.summarize_timing_ms(
                        changed_update_durations, 0
                    ),
                    "unchanged_ms": campfire.app.summarize_timing_ms(
                        unchanged_update_durations, 0
                    ),
                    "warmup_updates": UPDATE_WARMUP,
                    "profiler_capture_enabled": False,
                    "scope": "one app update after five committed Resident steps",
                },
                "flow": {
                    "active_blocks_min": min(active_blocks),
                    "active_blocks_max": max(active_blocks),
                    "active_blocks_final": active_blocks[-1],
                    "readback": readback,
                },
                "outputs": {
                    "native_state_sha256": native_state_sha256,
                    "point": point_hashes,
                },
                "gates": gates,
                "scope": {
                    "default_off": True,
                    "derived_diagnostic": True,
                    "production_changed": False,
                    "performance_profiler_capture": False,
                    "node_disablement_is_not_a_production_candidate": True,
                },
                "known_limit": (
                    "Disabling the FlowUsd StageUpdate node also suppresses Flow output; "
                    "the disabled case cannot qualify output equivalence or adoption."
                ),
            }
        )
        exit_code = 0 if all(gates.values()) else 2
    except asyncio.CancelledError:
        raise
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        carb.log_error(f"[phase6df] {type(error).__name__}: {error}")
    finally:
        if listener is not None:
            listener.Revoke()
        if owner is not None:
            try:
                if owner.status()["session"]["state"] == "running":
                    owner.stop()
                owner.close(discard_pending=True)
            except Exception as error:
                report.setdefault("cleanup_errors", []).append(
                    f"owner: {type(error).__name__}: {error}"
                )
        if flow_interface is not None:
            _flowusd.release_flowusd_interface(flow_interface)
        if target_stage_connected:
            try:
                await context.close_stage_async()
            except Exception as error:
                report.setdefault("cleanup_errors", []).append(
                    f"stage: {type(error).__name__}: {error}"
                )
        try:
            current = _flow_node(stage_update)
            stage_update.set_stage_update_node_enabled(current["index"], True)
            node_restored = _flow_node(stage_update)["enabled"]
        except Exception as error:
            report.setdefault("cleanup_errors", []).append(
                f"node: {type(error).__name__}: {error}"
            )
        report.setdefault("control", {})["node_restored"] = bool(node_restored)
        report.setdefault("runtime", {})["profiler_capture_mask_after"] = int(
            profiler.get_capture_mask()
        )
        if report.get("status") == "ok" and not node_restored:
            report["status"] = "failed"
            exit_code = 2
        _write(output, report)
        settings.set("/app/fastShutdown", True)
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(_run())
