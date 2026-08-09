"""Exercise the immutable Resident Point layout-representation contract in Kit."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import carb
import numpy as np
import omni.kit.app
from pxr import Gf, Sdf, Usd

import campfire.app


class Producer:
    def __init__(self):
        self.np = np
        self.point_count = 1
        self.positions = np.zeros((1, 3), dtype=np.float32)
        self.origins = np.zeros((1, 3), dtype=np.float64)
        self.axes = np.zeros(1, dtype=np.uint32)

    def build_layout(self):
        return self.point_count


class Backend:
    revision = 1

    def status(self):
        return {"revision": self.revision, "active": True}

    def close(self):
        return {"revision": self.revision, "active": False}


class Adapter:
    def __init__(self, revision):
        self.revision = revision
        self.active = False
        self.closed = False

    def on_timeline_started(self):
        self.active = True

    def on_timeline_stopped(self):
        self.active = False

    def status(self):
        return {
            "revision": self.revision,
            "active": self.active,
            "closed": self.closed,
        }

    def close(self):
        self.active = False
        self.closed = True
        return True


class StatusSidecar:
    def __init__(self, revision, representation):
        self.revision = revision
        self.representation = representation
        self.closed = False

    def status(self):
        return {
            "revision": self.revision,
            "layout_representation": self.representation,
            "closed": self.closed,
        }

    def close(self):
        self.closed = True
        return True


def build_stage(representation, revision=0):
    stage = Usd.Stage.CreateInMemory()
    campfire.app.populate_phase3_scene(stage)
    contract = campfire.app.configure_resident_point_application_scene(
        stage,
        (Gf.Vec3f(0.0, 0.0, 0.4),),
        initial_revision=revision,
        layout_representation=representation,
    )
    return stage, contract


def make_sidecar(stage, representation, revision=0):
    layout = {
        "revision": 1,
        "origins": ((0.0, 0.0, 0.0),),
        "axes": (0,),
        "representation": representation,
    }
    return campfire.app.ResidentPointSidecar(
        Backend(),
        stage,
        campfire.app.RESIDENT_POINT_EMITTER_PATH,
        lambda: stage,
        initial_revision=revision,
        initial_layout=layout,
        producer=Producer(),
        layout_state=dict(layout),
        layout_representation=representation,
    )


async def run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phase6dn/output")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    legacy = campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_LEGACY
    rigid = campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATION_RIGID_FRAME
    gates = {}
    report = None
    exit_code = 1
    try:
        stage, contract = build_stage(legacy)
        emitter = stage.GetPrimAtPath(campfire.app.RESIDENT_POINT_EMITTER_PATH)
        token = emitter.GetAttribute("campfire:layoutRepresentation")
        gates["token_is_preauthored_before_connection"] = bool(token)
        gates["token_type_is_token"] = token.GetTypeName() == Sdf.ValueTypeNames.Token
        gates["legacy_default_is_explicit"] = (
            token.Get() == legacy and contract["layout_representation"] == legacy
        )

        sidecar = make_sidecar(stage, legacy)
        gates["sidecar_status_exposes_representation"] = (
            sidecar.status()["layout_representation"] == legacy
        )
        payload = campfire.app.ImmutableSurfacePayload(
            revision=1,
            tick=1,
            layout_revision=1,
            point_count=1,
            positions=np.zeros((1, 3), dtype=np.float32).tobytes(),
            fuels=np.asarray((0.5,), dtype=np.float32).tobytes(),
            temperatures=np.asarray((0.7,), dtype=np.float32).tobytes(),
            smokes=np.asarray((0.1,), dtype=np.float32).tobytes(),
            layout_representation=legacy,
        )
        mismatched = campfire.app.ImmutableSurfacePayload(
            **{
                **payload.__dict__,
                "layout_representation": rigid,
            }
        )
        try:
            sidecar.publish(mismatched)
        except ValueError:
            pass
        gates["payload_mismatch_rejected_before_attempt"] = (
            not sidecar.attempt_payload_ids and not sidecar.attempt_payload_digests
        )
        token_before = token.Get()
        sidecar.publish(payload)
        gates["matching_payload_publishes"] = (
            sidecar.status()["revision"] == 1
            and emitter.GetAttribute("campfire:residentRevision").Get() == 1
        )
        gates["publication_never_rewrites_token"] = token.Get() == token_before == legacy

        rigid_stage, _ = build_stage(rigid)
        try:
            make_sidecar(rigid_stage, legacy)
        except ValueError:
            gates["stage_token_mismatch_fails_closed"] = True
        else:
            gates["stage_token_mismatch_fails_closed"] = False

        missing_stage, _ = build_stage(legacy)
        missing_stage.GetPrimAtPath(
            campfire.app.RESIDENT_POINT_EMITTER_PATH
        ).RemoveProperty("campfire:layoutRepresentation")
        try:
            make_sidecar(missing_stage, legacy)
        except RuntimeError:
            gates["legacy_stage_without_token_fails_closed"] = True
        else:
            gates["legacy_stage_without_token_fails_closed"] = False

        adapter = Adapter(1)
        session = campfire.app.ResidentApplicationSession(
            Backend(), adapter, sidecar=sidecar
        )
        session.start()
        session.stop()
        mismatched_adapter = Adapter(1)
        mismatched_sidecar = StatusSidecar(1, rigid)
        try:
            session.replace_consumers(
                mismatched_adapter, sidecar=mismatched_sidecar
            )
        except ValueError:
            pass
        gates["replacement_mismatch_preserves_old_consumers"] = (
            not adapter.closed
            and not sidecar.status()["closed"]
            and not mismatched_sidecar.closed
        )

        replacement_stage, _ = build_stage(legacy, revision=1)
        replacement_sidecar = make_sidecar(replacement_stage, legacy, revision=1)
        replacement_adapter = Adapter(1)
        replacement = session.replace_consumers(
            replacement_adapter, sidecar=replacement_sidecar
        )
        gates["matching_replacement_succeeds_before_retry"] = (
            replacement["revision"] == 1
            and adapter.closed
            and sidecar.status()["closed"]
            and not replacement_sidecar.status()["closed"]
        )
        close = session.close()
        gates["session_closes_cleanly"] = (
            close["sidecar_closed"] is True and close["pending_discarded"] is False
        )
        gates["rigid_frame_remains_reserved_only"] = (
            rigid in campfire.app.RESIDENT_POINT_LAYOUT_REPRESENTATIONS
            and contract["layout_representation"] == legacy
        )
        report = {
            "schema": "campfire.phase6dn.layout_representation_probe.v1",
            "phase": "phase6dn",
            "status": "ok" if all(gates.values()) else "failed",
            "gates": gates,
            "contract": contract,
            "representations": {
                "active": legacy,
                "reserved_unconnected": rigid,
            },
            "publication": {
                "attempt_count": len(sidecar.attempt_payload_ids),
                "published_revision": 1,
                "token_before": token_before,
                "token_after": token.Get(),
            },
            "non_changes": {
                "point_array_shape": True,
                "resident_snapshot": True,
                "wood_authority": True,
                "flow": True,
                "checkpoint_v1": True,
            },
        }
        exit_code = 0 if report["status"] == "ok" else 2
    except Exception as error:
        report = {
            "schema": "campfire.phase6dn.layout_representation_probe.v1",
            "phase": "phase6dn",
            "status": "error",
            "gates": gates,
            "error": f"{type(error).__name__}: {error}",
        }
        carb.log_error(f"[phase6dn] {type(error).__name__}: {error}")
    finally:
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        await omni.kit.app.get_app().next_update_async()
        omni.kit.app.get_app().post_uncancellable_quit(exit_code)


asyncio.ensure_future(run())
