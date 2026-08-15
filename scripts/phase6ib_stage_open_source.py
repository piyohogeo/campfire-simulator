"""App-ready Phase 6IB parser fixture and one OFF stage-open smoke."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import traceback
from pathlib import Path

import carb
import omni.kit.app
import omni.timeline
import omni.usd


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def start_smoke(authoring, atomic_report, emit, policy: dict, audit_path: Path, stage_root: Path, attempt_id: str) -> None:
    async def run() -> None:
        from pxr import Sdf, Usd
        atomic_write_json = atomic_report.atomic_write_json

        app = omni.kit.app.get_app()
        context = omni.usd.get_context()
        timeline = omni.timeline.get_timeline_interface()
        report = {
            "schema": "campfire.phase6ib.stage-open-audit.v1",
            "phase": "phase6ib",
            "attempt_id": attempt_id,
            "status": "running",
            "operation_complete": False,
            "shutdown_complete": False,
            "stage_created": True,
            "flow_interface_calls": 0,
            "readback_calls": 0,
            "capture_calls": 0,
            "timeline_play_calls": 0,
            "parser_fixture": {},
            "lifecycle": {},
        }
        exit_code = 1
        opened_identifier = None

        def persist() -> None:
            atomic_write_json(audit_path, report)

        try:
            frozen_path = Path(policy["frozen_probe_contract"]["path"])
            if not frozen_path.is_absolute():
                frozen_path = Path(policy["repository_root"]) / frozen_path
            if _sha(frozen_path) != policy["frozen_probe_contract"]["sha256"]:
                raise RuntimeError("frozen_probe_contract_digest_mismatch")
            frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
            stage_root.mkdir(parents=True, exist_ok=False)
            off_path = stage_root / "collision_off.usda"
            on_path = stage_root / "collision_on.usda"
            emit("stage_generation_started", condition="collision_off_and_collision_on_fixture")
            off_authored = authoring.author_stage(off_path, frozen, "collision_off")
            on_authored = authoring.author_stage(on_path, frozen, "collision_on")
            off_sha, on_sha = _sha(off_path), _sha(on_path)
            emit("stage_generation_complete", off_sha256=off_sha, on_sha256=on_sha)

            emit("stage_parse_started", parser="pxr.Usd.Stage.Open and pxr.Sdf.Layer.FindOrOpen")
            off = Usd.Stage.Open(str(off_path))
            on = Usd.Stage.Open(str(on_path))
            if off is None or on is None:
                raise RuntimeError("openusd_positive_parse_failed")
            off_validation = authoring.validate_stage(off, frozen, "collision_off")
            on_validation = authoring.validate_stage(on, frozen, "collision_on")
            difference = authoring.one_variable_diff(off, on)
            if not difference["accepted"]:
                raise RuntimeError("off_on_semantic_difference_invalid")

            negative_results = []
            legacy = stage_root / "negative_legacy_inline.usda"
            legacy.write_text('#usda 1.0\ndef Xform "World"\n{\n def FlowAdvectionCombustionParams "advection"\n {\n  def FlowAdvectionChannelParams "temperature" { float secondOrderBlendFactor = 0.9 }\n }\n}\n', encoding="utf-8")
            try:
                legacy_layer = Sdf.Layer.FindOrOpen(str(legacy))
                legacy_rejected = legacy_layer is None
                legacy_reason = "parser_rejected" if legacy_rejected else "unexpectedly_parsed"
            except Exception as error:
                legacy_rejected = True
                legacy_reason = f"{type(error).__name__}:{error}"
            negative_results.append({"name": "legacy_inline_rejected", "passed": legacy_rejected, "reason": legacy_reason})

            def mutated(name: str, mutate) -> None:
                path = stage_root / f"negative_{name}.usda"
                rejected = False
                reason = None
                try:
                    stage = authoring.author_stage(path, frozen, "collision_off")
                    mutate(stage)
                    if not stage.GetRootLayer().Save():
                        raise RuntimeError("negative_stage_save_failed:" + name)
                    reopened = Usd.Stage.Open(str(path))
                    if reopened is None:
                        rejected = True; reason = "parser_rejected"
                    else:
                        authoring.validate_stage(reopened, frozen, "collision_off")
                except Exception as error:
                    rejected = True; reason = f"{type(error).__name__}:{error}"
                negative_results.append({"name": name, "passed": rejected, "reason": reason})

            mutated("missing", lambda stage: stage.RemovePrim("/World/Flow/Simulate/advection/burn"))
            mutated("duplicate", lambda stage: stage.DefinePrim("/World/Flow/Simulate/advection/temperatureDuplicate", "FlowAdvectionChannelParams"))
            mutated("type_mismatch", lambda stage: stage.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").SetTypeName("Xform"))
            mutated("nan", lambda stage: stage.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").GetAttribute("secondOrderBlendFactor").Set(float("nan")))
            mutated("unknown_schema", lambda stage: stage.GetPrimAtPath("/World/Flow/Simulate/advection/temperature").SetTypeName("FutureFlowChannelParams"))
            if not all(item["passed"] for item in negative_results):
                raise RuntimeError("openusd_negative_fixture_failed")
            parser_report = {
                "positive_count": 2,
                "negative_count": len(negative_results),
                "positive": {"off": off_validation, "on": on_validation},
                "negative": negative_results,
                "one_variable_difference": difference,
                "stage_sha256": {"collision_off": off_sha, "collision_on": on_sha},
                "maximum_stage_bytes": max(path.stat().st_size for path in stage_root.iterdir()),
            }
            if parser_report["maximum_stage_bytes"] >= policy["parser_fixture"]["maximum_stage_bytes"]:
                raise RuntimeError("parser_fixture_stage_oversize")
            report["parser_fixture"] = parser_report
            emit("stage_parse_complete", positive_count=2, negative_count=len(negative_results))

            del off_authored, on_authored, off, on
            timeline.stop()
            opened, error = await context.open_stage_async(str(off_path))
            if not opened or error:
                raise RuntimeError("usd_context_stage_open_failed:" + str(error))
            live_stage = context.get_stage()
            if live_stage is None:
                raise RuntimeError("usd_context_stage_missing")
            opened_identifier = str(live_stage.GetRootLayer().identifier)
            emit("stage_open_complete", stage_identifier=opened_identifier, root_layer_identifier=str(live_stage.GetRootLayer().realPath or live_stage.GetRootLayer().identifier))
            live_validation = authoring.validate_stage(live_stage, frozen, "collision_off")
            report["stage"] = {
                "identifier": opened_identifier,
                "root_layer_identifier": str(live_stage.GetRootLayer().identifier),
                "root_layer_real_path": str(live_stage.GetRootLayer().realPath),
                "sha256": off_sha,
                "validation": live_validation,
                "geometry_contract": {
                    "proxy_topology": [26, 36, 120],
                    "source_surface_gap_m": frozen["fixed_scene"]["source_surface_gap_m"],
                    "end_clearance_m": frozen["fixed_scene"]["source_to_nearest_end_clearance_m"],
                    "camera_eye_m": frozen["fixed_scene"]["camera_eye_m"],
                    "roi_sha256": authoring.sha256_bytes(authoring.canonical_bytes(frozen["temporal_measurement"]["rois_normalized"])),
                    "numeric_gate_sha256": authoring.sha256_bytes(authoring.canonical_bytes(frozen["temporal_measurement"]["hard_gates"])),
                },
            }
            emit("required_prims_validated", prim_count=live_validation["required_prim_count"], flow_setting_count=len(live_validation["advection_evidence"]))
            report["operation_complete"] = True
            report["status"] = "operation_pass"
            emit("operation_complete", scope="registered_schema_stage_open_only")
            persist()
            exit_code = 0
        except Exception as error:
            report["status"] = "error"
            report["error"] = f"{type(error).__name__}: {error}"
            report["traceback"] = traceback.format_exc()
            persist()
        finally:
            try:
                timeline.stop()
                if context.get_stage() is not None:
                    identifier = opened_identifier or str(context.get_stage().GetRootLayer().identifier)
                    emit("stage_close_started", stage_identifier=identifier)
                    await asyncio.wait_for(context.close_stage_async(), timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
                    if context.get_stage() is not None:
                        raise RuntimeError("usd_context_not_empty_after_close")
                    emit("stage_close_complete", context_empty=True)
                    report["lifecycle"]["stage_close_complete"] = True
                else:
                    report["lifecycle"]["stage_close_complete"] = False
                if report["status"] == "operation_pass" and report["lifecycle"]["stage_close_complete"]:
                    report["status"] = "qualified"
                report["shutdown_complete"] = True
                report["lifecycle"]["shutdown_complete"] = True
                emit("shutdown_complete", requested=True)
            except Exception as shutdown_error:
                report["status"] = "error"
                report["shutdown_error"] = f"{type(shutdown_error).__name__}: {shutdown_error}"
                report["shutdown_complete"] = False
                exit_code = 1
            persist()
            app.post_uncancellable_quit(exit_code)

    asyncio.ensure_future(run())
