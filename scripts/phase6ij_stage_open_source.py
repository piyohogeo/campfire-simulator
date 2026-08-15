"""One stopped-timeline Stage open/close attempt for Phase 6IJ."""
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


def _layer_path(layer) -> str:
    return str(Path(layer.realPath or layer.identifier).resolve())


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
            if _sha(protected_path) != policy["composition_contract"]["protected_file_sha256"]:
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
            started = time.perf_counter()
            opened, error = await context.open_stage_async(expected["open_path"])
            report["open_elapsed_seconds"] = float(time.perf_counter() - started)
            if not opened or error:
                report["first_failure_boundary"] = "open_stage_async"
                raise RuntimeError("usd_context_stage_open_failed:" + str(error))
            emit("stage_open_completed", condition=condition, elapsed_seconds=report["open_elapsed_seconds"])

            stage = context.get_stage()
            if stage is None:
                raise RuntimeError("opened_stage_missing")
            root = stage.GetRootLayer()
            session = stage.GetSessionLayer()
            protected_layer = Sdf.Layer.FindOrOpen(str(protected_path))
            runtime_layer = Sdf.Layer.FindOrOpen(str(files["runtime"])) if condition == "C" else None
            sublayers = [str(Path(Sdf.ComputeAssetPathRelativeToLayer(root, value)).resolve()) for value in root.subLayerPaths]
            runtime_empty = runtime_layer is not None and len(runtime_layer.rootPrims) == 0 if condition == "C" else False
            initial_identifier = str(session.identifier) if session is not None else None
            session_at_close_request = stage.GetSessionLayer()
            close_identifier = str(session_at_close_request.identifier) if session_at_close_request is not None else None
            layer_stack = list(stage.GetLayerStack(includeSessionLayers=True))
            session_evidence = composition.produce_session_evidence(
                session_layer=session,
                session_layer_at_close_request=session_at_close_request,
                root_layer=root,
                runtime_layer=runtime_layer,
                protected_layer=protected_layer,
                layer_stack=layer_stack,
                raw_identifier=initial_identifier,
                close_request_identifier=close_identifier,
                real_path=str(session.realPath or "") if session is not None else "",
                resolved_path=str(Path(session.realPath).resolve()) if session is not None and session.realPath else "",
            )
            observed = {
                "condition": condition,
                "open_path": str(Path(expected["open_path"]).resolve()),
                "open_sha256": _sha(Path(expected["open_path"])),
                "root_identifier": _layer_path(root),
                "sublayer_identifiers": sublayers,
                "edit_target_identifier": _layer_path(stage.GetEditTarget().GetLayer()),
                "protected_sha256": _sha(protected_path),
                "runtime_empty": runtime_empty,
                **session_evidence,
            }
            identity_result = composition.validate_identity(observed, expected)
            write(identity_path, {"schema": composition.IDENTITY_SCHEMA, "expected": expected, "observed": observed, "validation": identity_result})
            report["observed_identity"] = observed
            persist()
            emit("opened_stage_identity_recorded", condition=condition, root_identifier=observed["root_identifier"])
            if not identity_result["accepted"]:
                report["first_failure_boundary"] = "opened_stage_identity"
                raise RuntimeError(identity_result["reasons"][0])

            emit("stage_close_requested", condition=condition)
            report["close_stage_async_calls"] = 1
            started = time.perf_counter()
            await asyncio.wait_for(context.close_stage_async(), timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
            report["close_elapsed_seconds"] = float(time.perf_counter() - started)
            emit("stage_close_completed", condition=condition, elapsed_seconds=report["close_elapsed_seconds"])
            if context.get_stage() is not None:
                report["first_failure_boundary"] = "context_empty"
                raise RuntimeError("usd_context_not_empty_after_close")
            session_at_close_request = None
            session = None
            runtime_layer = None
            protected_layer = None
            root = None
            stage = None
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
                    "schema": composition.SCHEMA, "phase": "phase6ij",
                    "attempt_id": attempt_id, "condition": condition,
                    "status": "safe_stop_stage_open_contract_failure",
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
                    started = time.perf_counter()
                    await asyncio.wait_for(context.close_stage_async(), timeout=float(policy["safety"]["stage_close_timeout_seconds"]))
                    report["close_elapsed_seconds"] = float(time.perf_counter() - started)
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
