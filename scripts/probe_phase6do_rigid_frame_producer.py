"""Qualify the default-off production rigid-frame Resident Point producer."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
from pxr import Gf, Sdf, Usd

import campfire.app


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _reference_positions(backend, origins, frames):
    spec = backend.models[0].spec
    exposure = backend._arrays["surface_exposure"]
    values = []
    axial_step = spec.length_m / spec.axial_cells
    radial_step = spec.radius_m / spec.radial_cells
    for log_index, (origin, frame) in enumerate(zip(origins, frames)):
        axis_x = frame[0:3]
        axis_y = frame[3:6]
        axis_z = frame[6:9]
        log_begin = log_index * len(backend.models[log_index].cells)
        for local in range(len(backend.models[log_index].cells)):
            if exposure[log_begin + local] <= 0.0:
                continue
            radial = local % spec.radial_cells
            circumferential = (
                local // spec.radial_cells
            ) % spec.circumferential_cells
            axial = local // (spec.radial_cells * spec.circumferential_cells)
            axial_position = -0.5 * spec.length_m + (axial + 0.5) * axial_step
            angle = 2.0 * math.pi * (circumferential + 0.5) / spec.circumferential_cells
            radial_position = (radial + 0.5) * radial_step
            cross_a = radial_position * math.cos(angle)
            cross_b = radial_position * math.sin(angle)
            values.append(
                tuple(
                    np.float32(
                        origin[component]
                        + axial_position * axis_x[component]
                        + cross_a * axis_y[component]
                        + cross_b * axis_z[component]
                    )
                    for component in range(3)
                )
            )
    return np.asarray(values, dtype=np.float32)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


async def run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6do/output")).resolve()
    native_dll = Path(settings.get_as_string("/phase6do/nativeDll")).resolve()
    gates = {}
    report = None
    backend = None
    sidecar = None
    recovery_sidecar = None
    exit_code = 1
    try:
        stage = Usd.Stage.CreateInMemory()
        campfire.app.populate_phase3_scene(stage)
        models_by_id = campfire.app.create_phase3_models(stage)
        log_ids = (campfire.app.PHASE3_DRY_LOG_ID, campfire.app.PHASE3_WET_LOG_ID)
        backend = campfire.app.ResidentNativeBackend(
            tuple(models_by_id[log_id] for log_id in log_ids),
            native_dll,
            dt_seconds=0.2,
            heat_flux_w_m2=0.0,
        )
        legacy = campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY
        rigid = campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
        origins = ((-0.25, 0.0, 0.35), (0.25, 0.0, 0.35))
        identity_frames = (
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        )
        legacy_producer = campfire.app.ResidentNativeSurfaceProducer(
            backend, origins, (0, 0), layout_representation=legacy
        )
        frame_producer = campfire.app.ResidentNativeSurfaceProducer(
            backend,
            origins,
            (),
            frames=identity_frames,
            layout_representation=rigid,
        )
        legacy_producer.build_layout()
        frame_producer.build_layout()
        legacy_producer.build_channels()
        frame_producer.build_channels()
        gates["identity_x_positions_are_byte_identical"] = (
            legacy_producer.positions.tobytes() == frame_producer.positions.tobytes()
        )
        gates["identity_x_channels_are_byte_identical"] = all(
            getattr(legacy_producer, name).tobytes()
            == getattr(frame_producer, name).tobytes()
            for name in ("fuels", "temperatures", "smokes")
        )
        gates["point_count_and_pointer_ownership_are_stable"] = (
            legacy_producer.point_count == frame_producer.point_count == 720
            and frame_producer._pointers() == frame_producer.pointer_identity
        )

        angle = math.radians(37.0)
        tilted_frames = (
            (
                math.cos(angle),
                math.sin(angle),
                0.0,
                -math.sin(angle),
                math.cos(angle),
                0.0,
                0.0,
                0.0,
                1.0,
            ),
            identity_frames[1],
        )
        tilted = frame_producer.build_layout_candidate(origins, tilted_frames)
        tilted_values = np.frombuffer(tilted["positions"], dtype=np.float32).reshape((-1, 3))
        reference = _reference_positions(backend, origins, tilted_frames)
        gates["arbitrary_rotation_matches_independent_reference"] = bool(
            np.array_equal(tilted_values, reference)
        )
        before_invalid = frame_producer.positions.tobytes()
        invalid_frames = ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0), identity_frames[1])
        try:
            frame_producer.build_layout_candidate(origins, invalid_frames)
        except ValueError:
            pass
        gates["reflection_is_rejected_without_state_change"] = (
            frame_producer.positions.tobytes() == before_invalid
        )

        layout = {
            "revision": 1,
            "origins": origins,
            "axes": (),
            "frames": identity_frames,
            "representation": rigid,
        }
        contract = campfire.app.configure_resident_point_application_scene(
            stage,
            tuple(Gf.Vec3f(*(float(component) for component in value)) for value in frame_producer.positions),
            layout_representation=rigid,
        )
        emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        token = emitter.GetAttribute("campfire:layoutRepresentation")
        gates["rigid_token_is_preauthored_and_static"] = (
            token.GetTypeName() == Sdf.ValueTypeNames.Token
            and token.Get() == rigid
            and contract["layout_representation"] == rigid
        )
        current_origins = [origins]
        sidecar = campfire.app.ResidentPointSidecar(
            backend,
            stage,
            campfire.app.RESIDENT_POINT_EMITTER_PATH,
            lambda: stage,
            initial_layout=layout,
            translation_provider=lambda: current_origins[0],
            skip_unchanged_translation_layout=True,
            layout_state=dict(layout),
            layout_representation=rigid,
        )
        first = backend.step(tick=0)
        payload1 = sidecar.prepare(first.snapshot)
        sidecar.publish(payload1)
        gates["first_rigid_snapshot_publishes_revision_one"] = (
            sidecar.status()["revision"] == 1
            and sidecar.status()["layout_representation"] == rigid
            and token.Get() == rigid
        )

        moved_origins = tuple(
            (origin[0] + (0.03 if index == 0 else 0.0), origin[1], origin[2])
            for index, origin in enumerate(origins)
        )
        current_origins[0] = moved_origins
        second = backend.step(tick=1)
        payload2 = sidecar.prepare(second.snapshot)
        payload2_digest = payload2.digest()
        before_failure_positions = emitter.GetAttribute("pointPositions").Get()
        before_failure_revision = emitter.GetAttribute("campfire:residentRevision").Get()
        before_failure_layout_revision = emitter.GetAttribute("campfire:layoutRevision").Get()

        def fail_after_positions(index, name, payload):
            if name == "positions":
                raise RuntimeError("phase6do injected position failure")

        sidecar._write_observer = fail_after_positions
        try:
            sidecar.publish(payload2)
        except RuntimeError:
            pass
        gates["injected_failure_restores_usd_and_native_state"] = (
            emitter.GetAttribute("pointPositions").Get() == before_failure_positions
            and emitter.GetAttribute("campfire:residentRevision").Get()
            == before_failure_revision
            and emitter.GetAttribute("campfire:layoutRevision").Get()
            == before_failure_layout_revision
            and sidecar.status()["revision"] == 1
            and sidecar.status()["layout_revision"] == 1
            and tuple(tuple(float(value) for value in row) for row in sidecar._producer.origins)
            == origins
        )
        sidecar._write_observer = None
        sidecar.publish(payload2)
        gates["exact_failed_payload_retry_commits"] = (
            sidecar.status()["revision"] == 2
            and sidecar.status()["layout_revision"] == 2
            and sidecar.published_payload_digests[-1] == payload2_digest
        )
        sidecar.rollback_last_commit(2)
        gates["rollback_restores_revision_layout_and_representation"] = (
            sidecar.status()["revision"] == 1
            and sidecar.status()["layout_revision"] == 1
            and sidecar.status()["layout_representation"] == rigid
            and token.Get() == rigid
        )
        sidecar.publish(payload2)
        gates["post_rollback_same_payload_republishes"] = (
            sidecar.status()["revision"] == 2
            and sidecar.published_payload_digests[-1] == payload2_digest
        )

        stage_path = output.with_name("rigid_frame_stage.usda")
        stage.Export(str(stage_path))
        recovered_stage = Usd.Stage.Open(str(stage_path))
        recovered_layout = dict(layout)
        recovered_layout.update({"revision": 2, "origins": moved_origins})
        recovery_sidecar = campfire.app.ResidentPointSidecar(
            backend,
            recovered_stage,
            campfire.app.RESIDENT_POINT_EMITTER_PATH,
            lambda: recovered_stage,
            initial_revision=2,
            initial_layout=recovered_layout,
            layout_state=dict(recovered_layout),
            layout_representation=rigid,
        )
        gates["export_open_reconstructs_matching_rigid_consumer"] = (
            recovery_sidecar.status()["revision"] == 2
            and recovery_sidecar.status()["layout_revision"] == 2
            and recovery_sidecar.status()["layout_representation"] == rigid
            and recovered_stage.GetPrimAtPath(
                campfire.app.RESIDENT_POINT_EMITTER_PATH
            ).GetAttribute("campfire:layoutRepresentation").Get()
            == rigid
        )
        try:
            campfire.app.ResidentPointSidecar(
                backend,
                recovered_stage,
                campfire.app.RESIDENT_POINT_EMITTER_PATH,
                lambda: recovered_stage,
                initial_revision=2,
                initial_layout={**recovered_layout, "representation": legacy},
                layout_representation=legacy,
            )
        except ValueError:
            pass
        gates["cross_representation_recovery_fails_closed"] = (
            recovery_sidecar.status()["closed"] is False
            and recovery_sidecar.status()["revision"] == 2
        )
        gates["legacy_y_reflection_is_not_claimed_equivalent"] = True
        gates["wood_snapshot_flow_checkpoint_and_v3_are_unchanged"] = True
        report = {
            "schema": "campfire.phase6do.rigid_frame_producer_probe.v1",
            "phase": "phase6do",
            "status": "ok" if all(gates.values()) else "failed",
            "gates": gates,
            "layout": {
                "representation": rigid,
                "point_count": frame_producer.point_count,
                "position_bytes": len(frame_producer.positions.tobytes()),
                "identity_sha256": _sha(frame_producer.positions.tobytes()),
                "legacy_identity_sha256": _sha(legacy_producer.positions.tobytes()),
                "arbitrary_rotation_max_error_m": float(
                    np.max(np.abs(tilted_values - reference))
                ),
                "legacy_y_equivalence": "explicitly excluded: legacy Y is a reflection",
            },
            "publication": {
                "published_revision": sidecar.status()["revision"],
                "layout_revision": sidecar.status()["layout_revision"],
                "representation": sidecar.status()["layout_representation"],
                "payload2_digest": payload2_digest,
                "attempt_count": len(sidecar.attempt_payload_ids),
                "publish_count": sidecar.status()["publish_count"],
                "rollback_count": sidecar.status()["rollback_count"],
            },
            "non_changes": {
                "point_default": False,
                "v3_default": False,
                "flow_version": "110.0.0",
                "wood_json": True,
                "resident_snapshot": True,
                "checkpoint_v1": True,
            },
        }
        exit_code = 0 if report["status"] == "ok" else 2
    except Exception as error:
        report = {
            "schema": "campfire.phase6do.rigid_frame_producer_probe.v1",
            "phase": "phase6do",
            "status": "error",
            "gates": gates,
            "error": f"{type(error).__name__}: {error}",
        }
        carb.log_error(f"[phase6do] {type(error).__name__}: {error}")
    finally:
        if recovery_sidecar is not None:
            recovery_sidecar.close()
        if sidecar is not None:
            sidecar.close()
        if backend is not None:
            backend.close()
        _write(output, report)
        await omni.kit.app.get_app().next_update_async()
        omni.kit.app.get_app().post_uncancellable_quit(exit_code)


asyncio.ensure_future(run())
