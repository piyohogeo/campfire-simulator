"""Exercise native, USD, shutdown, and same-stage restart recovery in Kit."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import carb
import omni.kit.app
from pxr import Usd, UsdGeom

import campfire.app
from campfire.app.phase3_scene import (
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_MODEL_DT_SECONDS,
)


def _settings_arguments():
    settings = carb.settings.get_settings()
    return (
        Path(settings.get_as_string("/phase6bx/nativeLibrary")),
        Path(settings.get_as_string("/phase6bx/output")),
    )


def _backend_digest(backend):
    digest = hashlib.sha256()
    for name in sorted(backend._arrays):
        digest.update(name.encode("utf-8"))
        digest.update(backend._arrays[name].tobytes())
    for values in (
        backend._elapsed,
        backend._cumulative,
        backend._step_output,
        backend._published_output,
    ):
        digest.update(values.tobytes())
    status = backend.status()
    digest.update(
        f'{status["revision"]}:{status["tick"]}:{status["step_count"]}'.encode(
            "ascii"
        )
    )
    return digest.hexdigest()


def _model_digest(models):
    payload = [model.to_dict() for model in models]
    return hashlib.sha256(
        json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _usd_signature(stage, log_ids):
    emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
    values = [
        emitter.GetAttribute(name).Get()
        for name in (
            "fuel",
            "temperature",
            "smoke",
            "coupleRateFuel",
            "coupleRateTemperature",
            "coupleRateSmoke",
            "campfire:residentRevision",
        )
    ]
    for log_id in log_ids:
        prim = stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        values.extend(
            [
                tuple(UsdGeom.Gprim(prim).GetDisplayColorAttr().Get()),
                prim.GetAttribute("campfire:surfaceTemperatureK").Get(),
                prim.GetAttribute("campfire:charFraction").Get(),
                prim.GetAttribute("campfire:remainingMassRatio").Get(),
                prim.GetAttribute("campfire:weakestSupportRatio").Get(),
                prim.GetAttribute("campfire:residentRevision").Get(),
            ]
        )
    return tuple(values)


def _consumer_revisions(stage, log_ids):
    emitter = stage.GetPrimAtPath(campfire.app.FLOW_EMITTER_PATH)
    return tuple(
        stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        .GetAttribute("campfire:residentRevision")
        .Get()
        for log_id in log_ids
    ) + (emitter.GetAttribute("campfire:residentRevision").Get(),)


async def _run(native_library: Path, output: Path):
    app = omni.kit.app.get_app()
    exit_code = 1
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        models = tuple(
            campfire.app.load_model_from_prim(
                stage.GetPrimAtPath(f"/World/Logs/{log_id}")
            )
            for log_id in log_ids
        )
        initial_dry_mass = {
            log_id: sum(
                cell.dry_wood_mass_kg + cell.char_mass_kg + cell.ash_mass_kg
                for cell in model.cells
            )
            for log_id, model in zip(log_ids, models)
        }
        failure = {"enabled": False, "revision_writes": 0}

        def inject_after_emitter_revision(_write_index, name):
            if failure["enabled"] and name == "campfire:residentRevision":
                failure["revision_writes"] += 1
                if failure["revision_writes"] == 3:
                    raise RuntimeError("Injected downstream revision-last failure")

        backend = campfire.app.ResidentNativeBackend(
            models,
            native_library,
            dt_seconds=PHASE3_MODEL_DT_SECONDS,
            heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
        )
        adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            write_observer=inject_after_emitter_revision,
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            coalesce_lightweight_notices=True,
        )
        adapter.on_timeline_started()

        first = backend.step(tick=1)
        adapter.publish(first.snapshot)
        first_signature = _usd_signature(stage, log_ids)
        native_before_failure = _backend_digest(backend)
        native_failure_rejected = False
        try:
            backend.step(tick=2, inject_failure_after_native=True)
        except RuntimeError as error:
            native_failure_rejected = "post-native failure" in str(error)
        native_failure_rollback_exact = _backend_digest(backend) == native_before_failure
        native_failure_preserved_usd = _usd_signature(stage, log_ids) == first_signature

        second = backend.step(tick=2)
        adapter.publish(second.snapshot)
        second_signature = _usd_signature(stage, log_ids)
        failure["enabled"] = True
        failure["revision_writes"] = 0
        third = backend.step(tick=3)
        downstream_failure_rejected = False
        try:
            adapter.publish(third.snapshot)
        except RuntimeError as error:
            downstream_failure_rejected = "revision-last failure" in str(error)
        failure["enabled"] = False
        downstream_replay_exact = _usd_signature(stage, log_ids) == second_signature
        downstream_kept_adapter_revision = adapter.status()["revision"] == 2
        downstream_kept_native_snapshot = (
            third.snapshot.revision == 3 and backend.status()["revision"] == 3
        )
        adapter.publish(third.snapshot)
        downstream_retry_committed = (
            adapter.status()["revision"] == 3
            and _consumer_revisions(stage, log_ids) == (3, 3, 3)
        )

        adapter.on_timeline_stopped()
        adapter_close_first = adapter.close()
        adapter_close_second = adapter.close()
        first_shutdown = backend.close()
        first_model_digest = _model_digest(models)
        backend_close_second = backend.close()
        shutdown_export_once = (
            first_shutdown["export_count"] == 1
            and not first_shutdown["already_closed"]
            and backend_close_second["already_closed"]
            and backend_close_second["export_count"] == 1
        )

        resumed_backend = campfire.app.ResidentNativeBackend(
            models,
            native_library,
            dt_seconds=PHASE3_MODEL_DT_SECONDS,
            heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
            initial_revision=3,
            initial_tick=3,
        )
        restart_import_exact = _model_digest(models) == first_model_digest
        resumed_adapter = campfire.app.UsdResidentSnapshotAdapter(
            stage,
            log_ids,
            initial_dry_mass,
            cache_usd_handles=True,
            lightweight_commits=True,
            skip_unchanged_derived=True,
            coalesce_lightweight_notices=True,
            initial_revision=3,
        )
        resumed_adapter.on_timeline_started()
        fourth = resumed_backend.step(tick=4)
        resumed_adapter.publish(fourth.snapshot)
        restart_revision_continuous = (
            fourth.snapshot.revision == 4
            and _consumer_revisions(stage, log_ids) == (4, 4, 4)
        )
        resumed_adapter.on_timeline_stopped()
        resumed_adapter.close()
        resumed_shutdown = resumed_backend.close()

        inconsistent_resume_rejected = False
        stage.GetPrimAtPath(f"/World/Logs/{log_ids[0]}").GetAttribute(
            "campfire:residentRevision"
        ).Set(3)
        try:
            campfire.app.UsdResidentSnapshotAdapter(
                stage,
                log_ids,
                initial_dry_mass,
                initial_revision=4,
            )
        except ValueError as error:
            inconsistent_resume_rejected = "matching consumer revisions" in str(error)

        gates = {
            "native_failure_rejected": native_failure_rejected,
            "native_failure_rollback_exact": native_failure_rollback_exact,
            "native_failure_preserved_usd": native_failure_preserved_usd,
            "downstream_failure_rejected": downstream_failure_rejected,
            "downstream_replay_exact": downstream_replay_exact,
            "downstream_kept_adapter_revision": downstream_kept_adapter_revision,
            "downstream_kept_native_snapshot": downstream_kept_native_snapshot,
            "downstream_retry_committed": downstream_retry_committed,
            "adapter_close_idempotent": adapter_close_first and not adapter_close_second,
            "shutdown_export_once": shutdown_export_once,
            "restart_import_exact": restart_import_exact,
            "restart_revision_continuous": restart_revision_continuous,
            "inconsistent_resume_rejected": inconsistent_resume_rejected,
            "resumed_shutdown_export_once": resumed_shutdown["export_count"] == 1,
        }
        report = {
            "schema_version": 1,
            "phase": "phase6bx",
            "status": "ok" if all(gates.values()) else "failed",
            "scope": {
                "production_default_changed": False,
                "physics_changed": False,
                "json_schema_changed": False,
            },
            "sequence": [
                "revision 1 commit",
                "native step failure and exact rollback",
                "revision 2 retry commit",
                "revision 3 downstream failure and old snapshot replay",
                "revision 3 publication retry",
                "shutdown export and idempotent close",
                "same-stage resume from revision/tick 3",
                "revision 4 commit",
            ],
            "gates": gates,
            "status_detail": {
                "first_shutdown": first_shutdown,
                "resumed_initial": {
                    "backend_revision": 3,
                    "backend_tick": 3,
                    "adapter_revision": 3,
                },
                "resumed_shutdown": resumed_shutdown,
                "final_consumer_revisions_before_negative_probe": [4, 4, 4],
            },
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not all(gates.values()):
            raise RuntimeError("One or more Phase 6BX lifecycle gates failed")
        exit_code = 0
    except asyncio.CancelledError:
        raise
    except Exception as error:
        output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "phase": "phase6bx",
                    "status": "error",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        carb.log_error(f"[phase6bx] {type(error).__name__}: {error}")
    finally:
        app.post_uncancellable_quit(exit_code)


native_library, output = _settings_arguments()
asyncio.ensure_future(_run(native_library, output))
