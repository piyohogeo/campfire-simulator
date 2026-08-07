"""Probe Sdf.ChangeBlock notice and rollback behavior with the local Kit USD."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "usd_change_block_report.json"
)
DEFAULT_SVG = (
    ROOT / "docs" / "devlog" / "assets" / "phase6" / "usd_change_block_report.svg"
)
_DLL_DIRECTORY_HANDLES = []


def _load_local_usd():
    try:
        from pxr import Gf, Sdf, Tf, Usd

        return Gf, Sdf, Tf, Usd
    except ModuleNotFoundError:
        candidates = sorted(
            (
                ROOT
                / "_build"
                / "windows-x86_64"
                / "release"
                / "extscache"
            ).glob("omni.usd.libs-*")
        )
        if not candidates:
            raise RuntimeError("The built Kit USD Python package was not found")
        package = candidates[-1]
        _DLL_DIRECTORY_HANDLES.append(
            os.add_dll_directory(str(package / "bin"))
        )
        sys.path.insert(0, str(package))
        from pxr import Gf, Sdf, Tf, Usd

        return Gf, Sdf, Tf, Usd


Gf, Sdf, Tf, Usd = _load_local_usd()


def _p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def _summarize(values):
    return {
        "sample_count": len(values),
        "mean_ms": statistics.fmean(values),
        "p95_ms": _p95(values),
        "maximum_ms": max(values),
    }


def _create_stage():
    stage = Usd.Stage.CreateInMemory()
    emitter = stage.DefinePrim("/World/Emitter")
    logs = tuple(stage.DefinePrim(f"/World/Logs/Log{index}") for index in range(2))
    payload = []
    revisions = []
    for name in (
        "fuel",
        "temperature",
        "smoke",
        "coupleRateFuel",
        "coupleRateTemperature",
        "coupleRateSmoke",
    ):
        payload.append(
            (f"Emitter.{name}", emitter.CreateAttribute(name, Sdf.ValueTypeNames.Float))
        )
    emitter_revision = emitter.CreateAttribute(
        "campfire:residentRevision", Sdf.ValueTypeNames.Int64
    )
    for index, prim in enumerate(logs):
        payload.append(
            (
                f"Log{index}.displayColor",
                prim.CreateAttribute(
                    "primvars:displayColor", Sdf.ValueTypeNames.Color3fArray
                ),
            )
        )
        for name in (
            "campfire:surfaceTemperatureK",
            "campfire:charFraction",
            "campfire:remainingMassRatio",
            "campfire:weakestSupportRatio",
        ):
            payload.append(
                (f"Log{index}.{name}", prim.CreateAttribute(name, Sdf.ValueTypeNames.Double))
            )
        revisions.append(
            prim.CreateAttribute(
                "campfire:residentRevision", Sdf.ValueTypeNames.Int64
            )
        )
    revisions.append(emitter_revision)
    return stage, tuple(payload), tuple(revisions)


def _value(name, revision, index):
    if name.endswith("displayColor"):
        scale = 0.0001 * revision
        return [Gf.Vec3f(0.3 + 0.1 * scale, 0.12, 0.045)]
    return float(index + 1) + revision * 0.001


def _values(payload, revision):
    return tuple(_value(name, revision, index) for index, (name, _attr) in enumerate(payload))


def _publish(payload, revisions, revision, *, fail_after_revision=False):
    for index, ((_name, attribute), value) in enumerate(
        zip(payload, _values(payload, revision))
    ):
        if not attribute.Set(value):
            raise RuntimeError(f"Payload Set failed at {index}")
    for attribute in revisions:
        if not attribute.Set(revision):
            raise RuntimeError("Revision Set failed")
    if fail_after_revision:
        raise RuntimeError("Injected failure after revision-last")


def _capture(payload, revisions):
    return {
        "payload": tuple(attribute.Get() for _name, attribute in payload),
        "revisions": tuple(int(attribute.Get()) for attribute in revisions),
    }


def _restore(payload, revisions, snapshot):
    for (_name, attribute), value in zip(payload, snapshot["payload"]):
        if not attribute.Set(value):
            raise RuntimeError("Rollback payload Set failed")
    for attribute, value in zip(revisions, snapshot["revisions"]):
        if not attribute.Set(value):
            raise RuntimeError("Rollback revision Set failed")


def _seed(payload, revisions, revision=1):
    _publish(payload, revisions, revision)
    return _capture(payload, revisions)


def probe_contract():
    stage, payload, revisions = _create_stage()
    _seed(payload, revisions)
    notices = []

    def record_notice(notice, _sender):
        notices.append(
            {
                "changed_paths": tuple(
                    str(path) for path in notice.GetChangedInfoOnlyPaths()
                ),
                "revisions": tuple(int(attribute.Get()) for attribute in revisions),
            }
        )

    listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, record_notice, stage)

    notices.clear()
    _publish(payload, revisions, 2)
    plain = {
        "notice_count": len(notices),
        "final_revisions": list(_capture(payload, revisions)["revisions"]),
        "last_notice_revisions": list(notices[-1]["revisions"]),
        "intermediate_notice_count": sum(
            notice["revisions"] != (2, 2, 2) for notice in notices
        ),
    }

    notices.clear()
    with Sdf.ChangeBlock():
        _publish(payload, revisions, 3)
    grouped = {
        "notice_count": len(notices),
        "changed_path_count": len(notices[0]["changed_paths"]),
        "notice_revisions": list(notices[0]["revisions"]),
        "final_revisions": list(_capture(payload, revisions)["revisions"]),
    }

    before_exception = _capture(payload, revisions)
    notices.clear()
    try:
        with Sdf.ChangeBlock():
            _publish(payload, revisions, 4, fail_after_revision=True)
    except RuntimeError:
        pass
    after_exception = _capture(payload, revisions)
    no_automatic_rollback = {
        "notice_count": len(notices),
        "state_changed": after_exception != before_exception,
        "final_revisions": list(after_exception["revisions"]),
    }

    notices.clear()
    failure = None
    with Sdf.ChangeBlock():
        try:
            _publish(payload, revisions, 5, fail_after_revision=True)
        except RuntimeError as error:
            _restore(payload, revisions, after_exception)
            failure = error
    same_block_rollback = {
        "notice_count": len(notices),
        "changed_path_count": len(notices[0]["changed_paths"]),
        "notice_revisions": list(notices[0]["revisions"]),
        "final_state_exact": _capture(payload, revisions) == after_exception,
        "failure_preserved_for_reraise": isinstance(failure, RuntimeError),
    }
    listener.Revoke()

    gates = {
        "plain_notice_per_set": plain["notice_count"] == 19,
        "plain_exposes_precommit_notices": plain["intermediate_notice_count"] > 0,
        "change_block_one_notice": grouped["notice_count"] == 1,
        "change_block_revision_consistent": grouped["notice_revisions"] == [3, 3, 3],
        "exception_is_not_rollback": (
            no_automatic_rollback["state_changed"]
            and no_automatic_rollback["final_revisions"] == [4, 4, 4]
        ),
        "same_block_rollback_one_notice": same_block_rollback["notice_count"] == 1,
        "same_block_rollback_exact": same_block_rollback["final_state_exact"],
        "same_block_rollback_revision_consistent": (
            same_block_rollback["notice_revisions"] == [4, 4, 4]
        ),
        "failure_can_be_reraised": same_block_rollback[
            "failure_preserved_for_reraise"
        ],
    }
    if not all(gates.values()):
        raise RuntimeError(f"ChangeBlock contract failed: {gates}")
    return {
        "field_count": 19,
        "payload_count": 16,
        "revision_count": 3,
        "plain": plain,
        "change_block": grouped,
        "exception_without_rollback": no_automatic_rollback,
        "same_block_rollback": same_block_rollback,
        "gates": gates,
    }


def benchmark_mode(mode, iterations, run_index):
    stage, payload, revisions = _create_stage()
    _seed(payload, revisions)
    notice_count = 0
    accepted_revisions = 0
    last_accepted_revision = 1

    def revision_gated_consumer(_notice, _sender):
        nonlocal notice_count, accepted_revisions, last_accepted_revision
        notice_count += 1
        current = tuple(int(attribute.Get()) for attribute in revisions)
        if len(set(current)) == 1 and current[0] > last_accepted_revision:
            last_accepted_revision = current[0]
            accepted_revisions += 1

    listener = Tf.Notice.Register(
        Usd.Notice.ObjectsChanged, revision_gated_consumer, stage
    )
    timings = []
    for offset in range(iterations + 20):
        revision = offset + 2
        started = time.perf_counter_ns()
        if mode == "change_block":
            with Sdf.ChangeBlock():
                _publish(payload, revisions, revision)
        else:
            _publish(payload, revisions, revision)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        if offset >= 20:
            timings.append(elapsed_ms)
    listener.Revoke()
    expected_notices = (iterations + 20) * (1 if mode == "change_block" else 19)
    if notice_count != expected_notices:
        raise RuntimeError(
            f"{mode} notice count {notice_count} != {expected_notices}"
        )
    if accepted_revisions != iterations + 20:
        raise RuntimeError(f"{mode} accepted revision count mismatch")
    return {
        "run": run_index,
        "mode": mode,
        "notice_count": notice_count,
        "accepted_revision_count": accepted_revisions,
        "timing": _summarize(timings),
    }


def analyze(iterations, run_count):
    contract = probe_contract()
    runs = []
    for run_index in range(1, run_count + 1):
        order = (
            ("plain", "change_block")
            if run_index % 2
            else ("change_block", "plain")
        )
        pair = {"run": run_index, "order": list(order)}
        for mode in order:
            pair[mode] = benchmark_mode(mode, iterations, run_index)
        runs.append(pair)
    plain_p95 = [run["plain"]["timing"]["p95_ms"] for run in runs]
    grouped_p95 = [run["change_block"]["timing"]["p95_ms"] for run in runs]
    return {
        "schema_version": 1,
        "phase": "phase6bl",
        "status": "prototype_qualified",
        "environment": {
            "usd_package": "omni.usd.libs-1.0.3",
            "stage": "Usd.Stage.CreateInMemory",
            "existing_attributes_only": True,
            "production_adapter_changed": False,
        },
        "contract": contract,
        "measurement": {
            "run_count": run_count,
            "iterations_per_mode_run": iterations,
            "warmup_iterations": 20,
            "balanced_order": True,
            "listener": "revision-gated ObjectsChanged consumer",
            "plain_p95_ms": plain_p95,
            "change_block_p95_ms": grouped_p95,
            "median_plain_p95_ms": statistics.median(plain_p95),
            "median_change_block_p95_ms": statistics.median(grouped_p95),
            "median_p95_reduction_ms": (
                statistics.median(plain_p95) - statistics.median(grouped_p95)
            ),
            "runs": runs,
        },
        "decision": {
            "prototype_contract_qualified": True,
            "production_qualified": False,
            "required_structure": (
                "Catch publication failure inside the ChangeBlock, replay the previous "
                "immutable snapshot inside the same block, exit the block, then reraise."
            ),
            "next_step": (
                "Add a default-off real Phase 3 ChangeBlock candidate and verify notice "
                "counts, failure replay, revision-last consumers, and p95 below 4 ms."
            ),
        },
    }


def render_svg(report):
    measurement = report["measurement"]
    plain = " / ".join(f"{value:.4f}" for value in measurement["plain_p95_ms"])
    grouped = " / ".join(
        f"{value:.4f}" for value in measurement["change_block_p95_ms"]
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
  <title id="title">Phase 6BL Sdf ChangeBlock contract</title>
  <desc id="desc">Local Kit USD prototype verifies notice coalescing, revision-last visibility, and same-block rollback.</desc>
  <rect width="1200" height="680" rx="32" fill="#111820"/>
  <text x="70" y="76" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">PHASE 6BL · USD NOTICE BOUNDARY PROTOTYPE</text>
  <text x="70" y="126" fill="#fff" font-family="Segoe UI, sans-serif" font-size="37" font-weight="700">19 Set notices → one revision-consistent notice</text>
  <rect x="70" y="170" width="1060" height="105" rx="20" fill="#192734" stroke="#315269"/>
  <text x="105" y="214" fill="#8fbcd4" font-family="Consolas, monospace" font-size="18">payload first → log revisions → emitter revision last → notify</text>
  <text x="105" y="250" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="17">existing attributes only · exception is not rollback · replay old snapshot inside the same block</text>
  <rect x="70" y="315" width="510" height="182" rx="20" fill="#182128"/>
  <text x="105" y="360" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Revision-gated consumer p95</text>
  <text x="105" y="405" fill="#a8beca" font-family="Consolas, monospace" font-size="18">plain  {plain} ms</text>
  <text x="105" y="445" fill="#f4b860" font-family="Consolas, monospace" font-size="18">block  {grouped} ms</text>
  <rect x="620" y="315" width="510" height="182" rx="20" fill="#182128"/>
  <text x="655" y="360" fill="#fff" font-family="Segoe UI, sans-serif" font-size="23" font-weight="700">Observed contract</text>
  <text x="655" y="405" fill="#65c18c" font-family="Segoe UI, sans-serif" font-size="18">normal commit  1 notice · revision consistent</text>
  <text x="655" y="441" fill="#65c18c" font-family="Segoe UI, sans-serif" font-size="18">rollback       1 notice · previous revision</text>
  <text x="655" y="477" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="18">exception alone persists partial/new state</text>
  <rect x="70" y="540" width="1060" height="86" rx="20" fill="#3a2d18" stroke="#f4b860"/>
  <text x="105" y="592" fill="#f4b860" font-family="Segoe UI, sans-serif" font-size="22" font-weight="700">PROTOTYPE QUALIFIED · PRODUCTION STILL OFF</text>
  <text x="760" y="580" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">9 / 9 contract gates</text>
  <text x="760" y="607" fill="#d7e1e8" font-family="Segoe UI, sans-serif" font-size="16">real Flow / failure run remains</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=400)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = analyze(arguments.iterations, arguments.runs)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    arguments.svg.write_text(render_svg(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
