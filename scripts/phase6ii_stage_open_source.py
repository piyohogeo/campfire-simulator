"""One minimal stopped-timeline Stage open/close attempt for Phase 6II."""
from __future__ import annotations

import asyncio
import hashlib
import time
import traceback
from pathlib import Path

import omni.kit.app
import omni.timeline
import omni.usd


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def start_probe(authoring, composition, atomic_report, emit, policy, report_path: Path,
                identity_path: Path, stage_root: Path, attempt_id: str,
                condition: str) -> None:
    async def run():
        from pxr import Sdf

        app = omni.kit.app.get_app()
        context = omni.usd.get_context()
        timeline = omni.timeline.get_timeline_interface()
        write = atomic_report.atomic_write_json
        report = None
        exit_code = 1

        def persist():
            if report is not None:
                write(report_path, report)

        try:
            if condition not in composition.CONDITIONS:
                raise ValueError("condition_unknown")
            stage_root.mkdir(parents=True, exist_ok=False)
            protected_path = stage_root / composition.PROTECTED_FILENAME
            protected_stage = authoring.author_stage(protected_path, policy["frozen_contract"], "collision_off")
            protected_sha = _sha(protected_path)
            if protected_sha != policy["composition_contract"]["protected_file_sha256"]:
                raise RuntimeError("protected_generated_hash_mismatch")
            authoring.validate_stage(protected_stage, policy["frozen_contract"], "collision_off")
            del protected_stage
            files = composition.create_condition_files(stage_root, condition)
            file_validation = composition.validate_composition_files(files, policy["composition_contract"])
            if not file_validation["accepted"]:
                raise RuntimeError(file_validation["reasons"][0])
            expected = composition.expected_identity(files)
            report = composition.produce_operation_report(attempt_id, condition, expected)
            persist()

            timeline.stop()
            emit("stage_open_requested", condition=condition, open_path=expected["open_path"])
            report["open_stage_async_calls"] = 1
            open_start = time.perf_counter()
            opened, error = await context.open_stage_async(expected["open_path"])
            report["open_elapsed_seconds"] = float(time.perf_counter() - open_start)
            if not opened or error:
                report["first_failure_boundary"] = "open_stage_async"
                raise RuntimeError("usd_context_stage_open_failed:" + str(error))
            emit("stage_open_completed", condition=condition, elapsed_seconds=report["open_elapsed_seconds"])

            stage = context.get_stage()
            if stage is None:
                raise RuntimeError("opened_stage_missing")
            root = stage.GetRootLayer()
            session = stage.GetSessionLayer()
            sublayers = [str(Path(Sdf.ComputeAssetPathRelativeToLayer(root, value)).resolve()) for value in root.subLayerPaths]
            runtime_empty = False
            if condition == "C":
                runtime_layer = Sdf.Layer.FindOrOpen(str(files["runtime"]))
                runtime_empty = runtime_layer is not None and len(runtime_layer.rootPrims) == 0
            observed = {
                "condition": condition,
                "open_path": str(Path(expected["open_path"]).resolve()),
                "open_sha256": _sha(Path(expected["open_path"])),
                "root_identifier": str(Path(root.realPath or root.identifier).resolve()),
                "sublayer_identifiers": sublayers,
                "session_present": session is not None,
                "session_identifier": str(session.identifier) if session is not None else None,
                "edit_target_identifier": str(Path(stage.GetEditTarget().GetLayer().realPath or stage.GetEditTarget().GetLayer().identifier).resolve()),
                "protected_sha256": _sha(protected_path),
                "runtime_empty": runtime_empty,
            }
            identity_result = composition.validate_identity(observed, expected)
            write(identity_path, {"schema": "campfire.phase6ii.opened-stage-identity.v1", "expected": expected, "observed": observed, "validation": identity_result})
            report["observed_identity"] = observed
            persist()
            emit("opened_stage_identity_recorded", condition=condition, root_identifier=observed["root_identifier"])
            if not identity_result["accepted"]:
                report["first_failure_boundary"] = "opened_stage_identity"
                raise RuntimeError(identity_result["reasons"][0])

            emit("stage_close_requested", condition=condition)
            report["close_stage_async_calls"] = 1
            close_start = time.perf_counter()
            await asyncio.wait_for(context.close_stage_async(), timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
            report["close_elapsed_seconds"] = float(time.perf_counter() - close_start)
            emit("stage_close_completed", condition=condition, elapsed_seconds=report["close_elapsed_seconds"])
            if context.get_stage() is not None:
                report["first_failure_boundary"] = "context_empty"
                raise RuntimeError("usd_context_not_empty_after_close")
            report["context_empty"] = True
            report["references_released"] = True
            emit("context_empty_confirmed", condition=condition)
            report["operation_complete"] = True
            report["status"] = "stage_open_close_qualified"
            persist()
            emit("shutdown_requested", condition=condition)
            report["shutdown_complete"] = True
            emit("shutdown_complete", condition=condition)
            persist()
            exit_code = 0
        except Exception as error:
            if report is None:
                report = {
                    "schema": composition.SCHEMA, "phase": "phase6ii",
                    "attempt_id": attempt_id, "condition": condition,
                    "status": "safe_stop_stage_open_harness_failure",
                    "operation_complete": False, "shutdown_complete": False,
                    "first_failure_boundary": "pre_open_harness",
                }
            else:
                report["status"] = "safe_stop_stage_open_attempt_failure"
                if report.get("first_failure_boundary") is None:
                    report["first_failure_boundary"] = "python_operation"
            report["error"] = f"{type(error).__name__}: {error}"
            report["traceback"] = traceback.format_exc()
            try:
                timeline.stop()
                if context.get_stage() is not None:
                    if report.get("close_stage_async_calls", 0) == 0:
                        emit("stage_close_requested", condition=condition)
                        report["close_stage_async_calls"] = 1
                    close_start = time.perf_counter()
                    await asyncio.wait_for(context.close_stage_async(), timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
                    report["close_elapsed_seconds"] = float(time.perf_counter() - close_start)
                    emit("stage_close_completed", condition=condition, elapsed_seconds=report["close_elapsed_seconds"])
                if context.get_stage() is None:
                    report["context_empty"] = True
                    report["references_released"] = True
                    emit("context_empty_confirmed", condition=condition)
                emit("shutdown_requested", condition=condition)
                report["shutdown_complete"] = True
                emit("shutdown_complete", condition=condition)
            except Exception as shutdown_error:
                report["shutdown_error"] = f"{type(shutdown_error).__name__}: {shutdown_error}"
                report["shutdown_complete"] = False
            persist()
        app.post_uncancellable_quit(exit_code)

    asyncio.ensure_future(run())
