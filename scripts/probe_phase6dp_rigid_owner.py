"""Qualify one new rigid-frame session through the production Point owner."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import carb
import omni.kit.app
import omni.timeline
import omni.usd
from pxr import Usd

import campfire.app
from campfire.app.phase3_scene import (
    PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
    PHASE3_MODEL_DT_SECONDS,
)


LOG_IDS = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _models(stage):
    return tuple(
        campfire.app.load_model_from_prim(
            stage.GetPrimAtPath(f"/World/Logs/{log_id}")
        )
        for log_id in LOG_IDS
    )


async def run() -> None:
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6dp/output")).resolve()
    native_dll = Path(settings.get_as_string("/phase6dp/nativeDll")).resolve()
    initial_path = output.with_suffix(".initial.usda")
    replacement_path = output.with_suffix(".replacement.usda")
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    app = omni.kit.app.get_app()
    owner = None
    event_subscription = None
    report = None
    gates = {}
    exit_code = 1
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        for path in (output, initial_path, replacement_path):
            path.unlink(missing_ok=True)

        offline_stage = Usd.Stage.CreateNew(str(initial_path))
        campfire.app.populate_phase3_scene(offline_stage)
        campfire.app.move_log(
            offline_stage, LOG_IDS[0], (0.04, -0.27, 0.19), 37.0
        )
        models = _models(offline_stage)
        backend = campfire.app.ResidentNativeBackend(
            models,
            native_dll,
            dt_seconds=PHASE3_MODEL_DT_SECONDS,
            heat_flux_w_m2=PHASE3_EXTERNAL_HEAT_FLUX_W_M2,
        )
        layout = campfire.app.resident_point_frame_layout_for_logs(
            offline_stage, LOG_IDS
        )
        producer = campfire.app.ResidentNativeSurfaceProducer(
            backend,
            layout["origins"],
            frames=layout["frames"],
            layout_representation=layout["representation"],
        )
        producer.build_layout()
        contract = campfire.app.configure_resident_point_application_scene(
            offline_stage,
            producer.positions,
            layout_representation=layout["representation"],
        )
        campfire.app.preauthor_resident_snapshot_consumers(offline_stage, LOG_IDS)
        offline_stage.GetRootLayer().customLayerData = {
            **offline_stage.GetRootLayer().customLayerData,
            "campfire:phase": "phase6dp",
            "campfire:stageBuiltBeforeConnection": True,
            "campfire:normalApplicationOwner": True,
        }
        if not offline_stage.GetRootLayer().Save():
            raise RuntimeError("Phase 6DP initial stage did not save")
        del producer
        del offline_stage

        opened, error = await context.open_stage_async(str(initial_path))
        if not opened or error:
            raise RuntimeError(f"Phase 6DP initial stage did not open: {error}")
        for _ in range(4):
            await app.next_update_async()
        stage = context.get_stage()
        owner = campfire.app.ResidentPointApplicationOwner.compose(
            backend,
            stage,
            context,
            timeline,
            app.next_update_async,
            layout,
        )
        backend = None

        initial_status = owner.status()
        gates["new_owner_starts_rigid_and_default_off"] = (
            initial_status["layout_representation"]
            == campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
            and initial_status["layout_revision"] == 1
            and contract["layout_representation"]
            == campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
            and not campfire.app.resident_point_application_enabled(settings)
        )

        owner.start()
        first = owner.step()
        owner.stop()
        after_first = owner.status()
        gates["first_step_commits_existing_snapshot_schema"] = (
            first.snapshot.revision == 1
            and after_first["session"]["adapter"]["revision"] == 1
            and after_first["session"]["sidecar"]["revision"] == 1
        )

        campfire.app.move_log(stage, LOG_IDS[0], (0.07, -0.24, 0.21), 53.0)
        refreshed = owner.refresh_layout(stage)
        after_refresh = owner.status()
        gates["stopped_arbitrary_transform_refreshes_atomically"] = (
            refreshed["changed"]
            and refreshed["revision"] == 2
            and refreshed["representation"]
            == campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
            and after_refresh["layout_revision"] == 2
            and after_refresh["layout_replace_count"] == 1
        )
        unchanged = owner.refresh_layout(stage)
        gates["unchanged_transform_skips_layout_publication"] = (
            not unchanged["changed"]
            and unchanged["revision"] == 2
            and owner.status()["layout_replace_count"] == 1
        )

        owner.start()
        second = owner.step()
        running_layout = {
            **refreshed,
            "revision": 3,
            "origins": tuple(
                (origin[0] + (0.01 if index == 0 else 0.0), origin[1], origin[2])
                for index, origin in enumerate(refreshed["origins"])
            ),
        }
        try:
            owner.replace_layout(running_layout)
        except RuntimeError as error:
            gates["running_layout_replacement_is_rejected"] = (
                "ready or stopped" in str(error)
                and owner.status()["layout_revision"] == 2
            )
        else:
            gates["running_layout_replacement_is_rejected"] = False
        owner.stop()
        gates["second_step_keeps_revision_alignment"] = (
            second.snapshot.revision == 2
            and owner.status()["session"]["adapter"]["revision"] == 2
            and owner.status()["session"]["sidecar"]["revision"] == 2
        )

        try:
            owner.replace_layout(
                {
                    "revision": 3,
                    "origins": refreshed["origins"],
                    "axes": (0, 0),
                    "representation": (
                        campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY
                    ),
                }
            )
        except ValueError as error:
            gates["live_representation_migration_is_rejected"] = (
                "cannot change in a session" in str(error)
                and owner.status()["layout_representation"]
                == campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
            )
        else:
            gates["live_representation_migration_is_rejected"] = False

        if not stage.GetRootLayer().Export(str(replacement_path)):
            raise RuntimeError("Phase 6DP replacement stage did not export")
        replacement_stage = Usd.Stage.Open(str(replacement_path))
        if replacement_stage is None:
            raise RuntimeError("Phase 6DP replacement stage did not reopen")

        event_names = {
            int(omni.usd.StageEventType.CLOSING): "closing",
            int(omni.usd.StageEventType.CLOSED): "closed",
            int(omni.usd.StageEventType.OPENING): "opening",
            int(omni.usd.StageEventType.OPENED): "opened",
        }

        def observe_stage_event(event):
            event_name = event_names.get(int(event.type))
            if event_name is not None and owner is not None:
                owner.observe_stage_event(event_name)

        event_subscription = (
            context.get_stage_event_stream().create_subscription_to_pop(
                observe_stage_event, name="phase6dp-rigid-owner"
            )
        )
        recovery = await owner.replace_stage(replacement_stage)
        after_recovery = owner.status()
        gates["stage_replacement_rebuilds_matching_rigid_consumers"] = (
            recovery["committed_revision"] == 2
            and recovery["consumer_replace_count"] == 1
            and recovery["session_state"] == "stopped"
            and after_recovery["session"]["sidecar"]["layout_representation"]
            == campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
            and after_recovery["layout_revision"] == 2
            and tuple(after_recovery["orchestrator"]["observed_events"])
            == ("closing", "closed", "opening", "opened")
        )

        owner.start()
        third = owner.step()
        owner.stop()
        before_close = owner.status()
        gates["post_recovery_step_commits_revision_three"] = (
            third.snapshot.revision == 3
            and before_close["session"]["adapter"]["revision"] == 3
            and before_close["session"]["sidecar"]["revision"] == 3
        )
        close = owner.close()
        repeated_close = owner.close()
        owner = None
        gates["shutdown_is_idempotent_and_closes_all_owners"] = (
            close["session"]["adapter_closed"] is True
            and close["session"]["sidecar_closed"] is True
            and close["session"]["backend"]["active"] is False
            and repeated_close["already_closed"] is True
        )
        gates["production_contracts_remain_unchanged"] = (
            not campfire.app.resident_point_application_enabled(settings)
        )

        report = {
            "schema": "campfire.phase6dp.rigid_owner_probe.v1",
            "phase": "phase6dp",
            "status": "ok" if all(gates.values()) else "failed",
            "gates": gates,
            "layout": {
                "representation": refreshed["representation"],
                "initial_rotation_degrees": 37.0,
                "refreshed_rotation_degrees": 53.0,
                "layout_revision": before_close["layout_revision"],
            },
            "publication": {
                "revision": before_close["session"]["adapter"]["revision"],
                "step_count": before_close["step_count"],
                "consumer_replace_count": before_close["session"][
                    "consumer_replace_count"
                ],
                "recovery_success_count": before_close["orchestrator"][
                    "success_count"
                ],
            },
            "non_changes": {
                "point_default": False,
                "v3_default": False,
                "sphere_production_default": True,
                "resident_snapshot": True,
                "checkpoint_v1": True,
                "flow_version": "110.0.0",
            },
        }
        exit_code = 0 if report["status"] == "ok" else 2
    except Exception as error:
        report = {
            "schema": "campfire.phase6dp.rigid_owner_probe.v1",
            "phase": "phase6dp",
            "status": "error",
            "gates": gates,
            "error": f"{type(error).__name__}: {error}",
        }
        carb.log_error(f"[phase6dp] {type(error).__name__}: {error}")
    finally:
        event_subscription = None
        if owner is not None:
            try:
                owner.close(discard_pending=True)
            except Exception:
                pass
        _write(output, report)
        await app.next_update_async()
        app.post_uncancellable_quit(exit_code)


asyncio.ensure_future(run())
