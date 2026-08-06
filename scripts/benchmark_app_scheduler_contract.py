"""Exercise an app-equivalent contract around the distributed wood scheduler.

The trial keeps the authoritative wood state independent from Flow and USD.
At each logical 0.2 s tick it snapshots heat and oxygen for twenty logs, then
publishes immutable output records over twelve render-frame slots.  Three
consumer views (Flow emitter, visual state, and structural support) must read
the same committed revision.  This remains a headless architecture trial and
does not install the scheduler as the production default.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import benchmark_distributed_wood_updates as distributed
import benchmark_wood_scaling as scaling


TOTAL_LOGS = 20
FRAME_SLOTS = 12
RENDER_FPS = 60
WOOD_BUDGET_MS = 4.0
PATTERNS = ("fixed5", "fixed12", "rotating5")


@dataclass(frozen=True)
class WoodInputSnapshot:
    tick: int
    snapshot_frame: int
    heat_flux_w_m2: float
    oxygen_factor: float


@dataclass(frozen=True)
class PublishedWoodOutput:
    log_index: int
    revision: int
    output_tick: int
    published_frame: int
    elapsed_seconds: float
    input_heat_flux_w_m2: float
    input_oxygen_factor: float
    thermal_step_executed: bool
    surface_temperature_k: float
    remaining_mass_ratio: float
    char_mass_kg: float
    flow_fuel: float
    flow_temperature: float
    flow_smoke: float
    pyrolysis_gas_rate_kg_s: float
    weakest_support_ratio: float


def _templates(combustion) -> dict[str, dict]:
    payloads = {}
    for kind, moisture in (("dry", 0.12), ("wet", 0.60)):
        model = combustion.create_cylindrical_wood_model(
            f"app_contract_{kind}",
            radius_m=0.16,
            length_m=1.80,
            moisture_ratio_dry_basis=moisture,
        )
        model.use_slotted_cell_storage()
        payloads[kind] = model.to_dict()
    return payloads


def _clone_models(combustion, templates: dict[str, dict]):
    models = []
    kinds = []
    for log_index in range(TOTAL_LOGS):
        kind = "dry" if log_index % 2 == 0 else "wet"
        model = combustion.WoodThermalModel.from_dict(templates[kind])
        model.use_slotted_cell_storage()
        models.append(model)
        kinds.append(kind)
    return models, kinds


def _active_indices(pattern: str, tick: int) -> set[int]:
    if pattern == "fixed5":
        return set(range(5))
    if pattern == "fixed12":
        return set(range(12))
    if pattern == "rotating5":
        start = (tick * 5) % TOTAL_LOGS
        return {(start + offset) % TOTAL_LOGS for offset in range(5)}
    raise ValueError(f"Unknown activity pattern: {pattern}")


def _snapshot_inputs(pattern: str, tick: int) -> tuple[WoodInputSnapshot, ...]:
    active = _active_indices(pattern, tick)
    snapshot_frame = tick * FRAME_SLOTS
    oxygen_epoch = tick // 30
    return tuple(
        WoodInputSnapshot(
            tick=tick,
            snapshot_frame=snapshot_frame,
            heat_flux_w_m2=(
                120_000.0 + 7_500.0 * ((tick + log_index) % 5)
                if log_index in active
                else 0.0
            ),
            oxygen_factor=0.45 + 0.10 * ((oxygen_epoch + log_index) % 4),
        )
        for log_index in range(TOTAL_LOGS)
    )


def _apply_oxygen(model, oxygen_factor: float) -> None:
    if not math.isfinite(oxygen_factor) or not 0.0 <= oxygen_factor <= 1.0:
        raise ValueError("oxygen_factor must be finite and within [0, 1]")
    for cell in model.cells:
        cell.oxygen_factor = oxygen_factor * cell.surface_exposure


def _weakest_support_ratio(model, char_strength_factor: float = 0.12) -> float:
    """Return the scalar consumed by the Phase 5 collapse decision."""

    spec = model.spec
    cells_per_section = spec.circumferential_cells * spec.radial_cells
    initial_section_dry_mass = (
        math.pi
        * spec.radius_m**2
        * (spec.length_m / spec.axial_cells)
        * model.parameters.dry_wood_density_kg_m3
    )
    ratios = []
    for axial_index in range(spec.axial_cells):
        start = axial_index * cells_per_section
        section = model.cells[start : start + cells_per_section]
        dry_mass = sum(cell.dry_wood_mass_kg for cell in section)
        char_mass = sum(cell.char_mass_kg for cell in section)
        ratios.append(
            min(
                1.0,
                max(
                    0.0,
                    (dry_mass + char_strength_factor * char_mass)
                    / max(initial_section_dry_mass, 1.0e-12),
                ),
            )
        )
    interior = ratios[1:-1] if len(ratios) > 2 else ratios
    return min(interior)


def _initial_output(model, topology, log_index: int) -> PublishedWoodOutput:
    metrics = model.runtime_metrics(topology)
    remaining_mass = sum(
        metrics[key]
        for key in (
            "moisture_mass_kg",
            "dry_wood_mass_kg",
            "char_mass_kg",
            "ash_mass_kg",
        )
    )
    return PublishedWoodOutput(
        log_index=log_index,
        revision=0,
        output_tick=-1,
        published_frame=-1,
        elapsed_seconds=model.elapsed_seconds,
        input_heat_flux_w_m2=0.0,
        input_oxygen_factor=1.0,
        thermal_step_executed=False,
        surface_temperature_k=metrics["surface_mean_temperature_k"],
        remaining_mass_ratio=remaining_mass / model.initial_mass_kg,
        char_mass_kg=metrics["char_mass_kg"],
        flow_fuel=0.0,
        flow_temperature=0.0,
        flow_smoke=0.0,
        pyrolysis_gas_rate_kg_s=0.0,
        weakest_support_ratio=_weakest_support_ratio(model),
    )


def _publish_output(
    combustion,
    model,
    topology,
    previous: PublishedWoodOutput,
    snapshot: WoodInputSnapshot,
    published_frame: int,
    step_result,
) -> PublishedWoodOutput:
    if step_result is None:
        return PublishedWoodOutput(
            **{
                **asdict(previous),
                "revision": previous.revision + 1,
                "output_tick": snapshot.tick,
                "published_frame": published_frame,
                "elapsed_seconds": model.elapsed_seconds,
                "input_heat_flux_w_m2": snapshot.heat_flux_w_m2,
                "input_oxygen_factor": snapshot.oxygen_factor,
                "thermal_step_executed": False,
            }
        )

    metrics = model.runtime_metrics(topology)
    source = combustion.flow_source_from_model(
        model,
        step_result,
        surface_temperature_k=metrics["surface_mean_temperature_k"],
    )
    remaining_mass = sum(
        metrics[key]
        for key in (
            "moisture_mass_kg",
            "dry_wood_mass_kg",
            "char_mass_kg",
            "ash_mass_kg",
        )
    )
    return PublishedWoodOutput(
        log_index=previous.log_index,
        revision=previous.revision + 1,
        output_tick=snapshot.tick,
        published_frame=published_frame,
        elapsed_seconds=model.elapsed_seconds,
        input_heat_flux_w_m2=snapshot.heat_flux_w_m2,
        input_oxygen_factor=snapshot.oxygen_factor,
        thermal_step_executed=True,
        surface_temperature_k=metrics["surface_mean_temperature_k"],
        remaining_mass_ratio=remaining_mass / model.initial_mass_kg,
        char_mass_kg=metrics["char_mass_kg"],
        flow_fuel=source.fuel,
        flow_temperature=source.temperature,
        flow_smoke=source.smoke,
        pyrolysis_gas_rate_kg_s=source.pyrolysis_gas_rate_kg_s,
        weakest_support_ratio=_weakest_support_ratio(model),
    )


def _advance(model, heat_flux_w_m2: float):
    if distributed.can_skip_exact_equilibrium(model, heat_flux_w_m2):
        model.elapsed_seconds += scaling.DT_SECONDS
        return None, True
    return (
        model.step(
            scaling.DT_SECONDS,
            heat_flux_w_m2,
            **scaling.STEP_ARGUMENTS,
        ),
        False,
    )


def _consume_outputs(
    outputs: list[PublishedWoodOutput], current_tick: int
) -> tuple[int, float]:
    emitter_view = tuple(
        (item.log_index, item.revision, item.output_tick, item.flow_fuel)
        for item in outputs
    )
    visual_view = tuple(
        (item.log_index, item.revision, item.output_tick, item.surface_temperature_k)
        for item in outputs
    )
    support_view = tuple(
        (item.log_index, item.revision, item.output_tick, item.weakest_support_ratio)
        for item in outputs
    )
    emitter_revisions = tuple(item[:3] for item in emitter_view)
    if emitter_revisions != tuple(item[:3] for item in visual_view):
        raise RuntimeError("Emitter and visual consumers observed mixed revisions")
    if emitter_revisions != tuple(item[:3] for item in support_view):
        raise RuntimeError("Emitter and support consumers observed mixed revisions")
    maximum_staleness = max(current_tick - item.output_tick for item in outputs)
    if maximum_staleness > 1 or any(item.output_tick > current_tick for item in outputs):
        raise RuntimeError("A consumer observed a future or over-stale output")
    checksum = (
        sum(item[3] for item in emitter_view)
        + sum(item[3] for item in visual_view)
        + sum(item[3] for item in support_view)
    )
    return maximum_staleness, checksum


def _output_sha256(output: PublishedWoodOutput) -> str:
    return hashlib.sha256(
        json.dumps(
            asdict(output), allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


def _simulate_reference(combustion, templates: dict[str, dict], pattern: str, cycles: int):
    models, _ = _clone_models(combustion, templates)
    topologies = [model.capture_runtime_topology() for model in models]
    outputs = [
        _initial_output(model, topology, index)
        for index, (model, topology) in enumerate(zip(models, topologies))
    ]
    applied_oxygen = [None] * TOTAL_LOGS
    for tick in range(cycles):
        snapshots = _snapshot_inputs(pattern, tick)
        for log_index, snapshot in enumerate(snapshots):
            if applied_oxygen[log_index] != snapshot.oxygen_factor:
                _apply_oxygen(models[log_index], snapshot.oxygen_factor)
                applied_oxygen[log_index] = snapshot.oxygen_factor
            result, _ = _advance(models[log_index], snapshot.heat_flux_w_m2)
            published_frame = snapshot.snapshot_frame + log_index % FRAME_SLOTS
            outputs[log_index] = _publish_output(
                combustion,
                models[log_index],
                topologies[log_index],
                outputs[log_index],
                snapshot,
                published_frame,
                result,
            )
    for model in models:
        model.refresh_cell_phases()
    return (
        [scaling._state_sha256(model) for model in models],
        [_output_sha256(output) for output in outputs],
    )


def _run_once(
    combustion,
    templates: dict[str, dict],
    pattern: str,
    cycles: int,
    warmup_cycles: int,
    reference_state_hashes: list[str],
    reference_output_hashes: list[str],
) -> dict:
    models, _ = _clone_models(combustion, templates)
    topologies = [model.capture_runtime_topology() for model in models]
    outputs = [
        _initial_output(model, topology, index)
        for index, (model, topology) in enumerate(zip(models, topologies))
    ]
    applied_oxygen = [None] * TOTAL_LOGS
    slot_members = [
        [index for index in range(TOTAL_LOGS) if index % FRAME_SLOTS == slot]
        for slot in range(FRAME_SLOTS)
    ]
    frame_times_ms = []
    snapshot_times_ms = []
    scheduled_update_and_output_times_ms = []
    consumer_times_ms = []
    scheduler_active_counts = []
    requested_active_counts = []
    output_latencies_frames = []
    sleeping_gate_hits = 0
    maximum_consumer_tick_staleness = 0
    consumer_checksum = 0.0

    gc.collect()
    for tick in range(cycles):
        first_frame_started = time.perf_counter()
        snapshot_started = time.perf_counter()
        snapshots = _snapshot_inputs(pattern, tick)
        snapshot_times_ms.append((time.perf_counter() - snapshot_started) * 1000.0)
        requested_active_counts.append(
            sum(snapshot.heat_flux_w_m2 > 0.0 for snapshot in snapshots)
        )
        cycle_active_count = 0

        for slot, members in enumerate(slot_members):
            frame_started = first_frame_started if slot == 0 else time.perf_counter()
            published_frame = tick * FRAME_SLOTS + slot
            adapter_started = time.perf_counter()
            for log_index in members:
                snapshot = snapshots[log_index]
                if applied_oxygen[log_index] != snapshot.oxygen_factor:
                    _apply_oxygen(models[log_index], snapshot.oxygen_factor)
                    applied_oxygen[log_index] = snapshot.oxygen_factor
                result, slept = _advance(
                    models[log_index], snapshot.heat_flux_w_m2
                )
                sleeping_gate_hits += int(slept)
                cycle_active_count += int(not slept)
                outputs[log_index] = _publish_output(
                    combustion,
                    models[log_index],
                    topologies[log_index],
                    outputs[log_index],
                    snapshot,
                    published_frame,
                    result,
                )
                latency = published_frame - snapshot.snapshot_frame
                if latency != log_index % FRAME_SLOTS:
                    raise RuntimeError("Output latency no longer matches the fixed slot")
                output_latencies_frames.append(latency)
            scheduled_update_and_output_times_ms.append(
                (time.perf_counter() - adapter_started) * 1000.0
            )

            consumer_started = time.perf_counter()
            staleness, checksum = _consume_outputs(outputs, tick)
            consumer_times_ms.append(
                (time.perf_counter() - consumer_started) * 1000.0
            )
            maximum_consumer_tick_staleness = max(
                maximum_consumer_tick_staleness, staleness
            )
            consumer_checksum += checksum
            frame_times_ms.append((time.perf_counter() - frame_started) * 1000.0)

        if any(output.output_tick != tick for output in outputs):
            raise RuntimeError("Not every log published by the end of its logical tick")
        scheduler_active_counts.append(cycle_active_count)

    for model in models:
        model.refresh_cell_phases()
    state_hashes = [scaling._state_sha256(model) for model in models]
    output_hashes = [_output_sha256(output) for output in outputs]
    exact_states = state_hashes == reference_state_hashes
    exact_outputs = output_hashes == reference_output_hashes
    if not exact_states or not exact_outputs:
        raise RuntimeError(f"{pattern} diverged from its synchronous reference")

    maximum_mass_balance_error_kg = 0.0
    all_values_finite = True
    for model in models:
        metrics = model.metrics()
        maximum_mass_balance_error_kg = max(
            maximum_mass_balance_error_kg,
            abs(float(metrics["mass_balance_error_kg"])),
        )
        all_values_finite = all_values_finite and all(
            math.isfinite(cell.temperature_k)
            and math.isfinite(cell.current_mass_kg)
            for cell in model.cells
        )
    if maximum_mass_balance_error_kg > 1.0e-9 or not all_values_finite:
        raise RuntimeError(f"{pattern} violated numerical invariants")

    warmup_frames = warmup_cycles * FRAME_SLOTS
    measured_frames = frame_times_ms[warmup_frames:]
    measured_snapshots = snapshot_times_ms[warmup_cycles:]
    measured_updates = scheduled_update_and_output_times_ms[warmup_frames:]
    measured_consumers = consumer_times_ms[warmup_frames:]
    measured_active = scheduler_active_counts[warmup_cycles:]
    first_all_awake_tick = next(
        (index for index, count in enumerate(scheduler_active_counts) if count == 20),
        None,
    )
    return {
        "pattern": pattern,
        "sample_count_frames": len(measured_frames),
        "warmup_frames_excluded": warmup_frames,
        "frame_mean_ms": statistics.fmean(measured_frames),
        "frame_p95_ms": scaling._percentile_95(measured_frames),
        "frame_max_ms": max(measured_frames),
        "frames_over_4ms_fraction": sum(
            value > WOOD_BUDGET_MS for value in measured_frames
        )
        / len(measured_frames),
        "input_snapshot_mean_ms": statistics.fmean(measured_snapshots),
        "input_snapshot_p95_ms": scaling._percentile_95(measured_snapshots),
        "scheduled_update_and_output_mean_ms": statistics.fmean(measured_updates),
        "consumer_read_mean_ms": statistics.fmean(measured_consumers),
        "requested_active_count": int(statistics.median(requested_active_counts)),
        "scheduler_active_count_median": statistics.median(measured_active),
        "scheduler_active_count_final": scheduler_active_counts[-1],
        "first_all_awake_tick": first_all_awake_tick,
        "first_all_awake_model_seconds": (
            (first_all_awake_tick + 1) * scaling.DT_SECONDS
            if first_all_awake_tick is not None
            else None
        ),
        "sleeping_gate_hits": sleeping_gate_hits,
        "maximum_output_latency_frames": max(output_latencies_frames),
        "maximum_output_latency_ms_at_60fps": (
            max(output_latencies_frames) / RENDER_FPS * 1000.0
        ),
        "maximum_consumer_tick_staleness": maximum_consumer_tick_staleness,
        "consumer_read_events": cycles * FRAME_SLOTS * TOTAL_LOGS * 3,
        "consumer_checksum": consumer_checksum,
        "exact_reference_states": exact_states,
        "exact_reference_outputs": exact_outputs,
        "maximum_mass_balance_error_kg": maximum_mass_balance_error_kg,
        "all_values_finite": all_values_finite,
        "final_state_sha256": state_hashes,
        "final_output_sha256": output_hashes,
    }


def run_benchmark(patterns: list[str], runs: int, cycles: int, warmup_cycles: int):
    combustion = scaling._load_combustion_module()
    templates = _templates(combustion)
    references = {
        pattern: _simulate_reference(combustion, templates, pattern, cycles)
        for pattern in patterns
    }
    results = []
    for run_index in range(runs):
        if run_index % 3 == 0:
            order = patterns
            order_label = "forward"
        elif run_index % 3 == 1:
            order = list(reversed(patterns))
            order_label = "reverse"
        else:
            order = patterns[1:] + patterns[:1]
            order_label = "rotated"
        for pattern in order:
            state_hashes, output_hashes = references[pattern]
            result = _run_once(
                combustion,
                templates,
                pattern,
                cycles,
                warmup_cycles,
                state_hashes,
                output_hashes,
            )
            result["run"] = run_index + 1
            result["order"] = order_label
            results.append(result)

    maximum_mass_error = max(
        result["maximum_mass_balance_error_kg"] for result in results
    )
    return {
        "schema_version": 1,
        "benchmark": "app_wood_scheduler_contract",
        "status": "ok",
        "measurement_boundary": {
            "kit_python": "_build/windows-x86_64/release/kit/python/python.exe"
            in scaling.sys.executable.replace("\\", "/"),
            "authoritative_cpu_wood_step_included": True,
            "input_snapshot_included_in_first_frame": True,
            "oxygen_application_included": True,
            "runtime_metrics_and_flow_mapping_included": True,
            "support_reduction_included": True,
            "three_consumer_reads_included": True,
            "usd_flow_render_physx_excluded": True,
            "trial_not_production_default": True,
        },
        "scenario": {
            "total_logs": TOTAL_LOGS,
            "patterns": patterns,
            "frame_slots_per_logical_tick": FRAME_SLOTS,
            "render_fps_assumption": RENDER_FPS,
            "wood_update_hz": 1.0 / scaling.DT_SECONDS,
            "cycles_per_run": cycles,
            "warmup_cycles_excluded": warmup_cycles,
            "model_dt_seconds": scaling.DT_SECONDS,
            "cell_count_per_log": len(templates["dry"]["cells"]),
            "input_heat_flux_range_w_m2": [0.0, 150_000.0],
            "input_oxygen_factor_range": [0.45, 0.75],
            "oxygen_change_interval_ticks": 30,
        },
        "contract": {
            "snapshot_once_per_logical_tick": True,
            "fixed_slot_assignment": "log_index % 12",
            "maximum_allowed_output_latency_frames": 11,
            "maximum_allowed_consumer_tick_staleness": 1,
            "immutable_output_revision_shared_by_consumers": True,
            "sleeping_output_reuses_unchanged_payload": True,
            "consumer_views": ["flow_emitter", "visual_state", "support_decision"],
        },
        "equivalence": {
            "exact_reference_states_all_runs": all(
                result["exact_reference_states"] for result in results
            ),
            "exact_reference_outputs_all_runs": all(
                result["exact_reference_outputs"] for result in results
            ),
            "maximum_mass_balance_error_kg": maximum_mass_error,
        },
        "runs": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patterns", nargs="+", default=list(PATTERNS))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cycles", type=int, default=180)
    parser.add_argument("--warmup-cycles", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if tuple(arguments.patterns) != PATTERNS:
        parser.error(f"--patterns must be {' '.join(PATTERNS)}")
    if arguments.runs < 3:
        parser.error("--runs must be at least 3")
    if not 0 <= arguments.warmup_cycles < arguments.cycles:
        parser.error("--warmup-cycles must be in [0, cycles)")

    report = run_benchmark(
        arguments.patterns,
        arguments.runs,
        arguments.cycles,
        arguments.warmup_cycles,
    )
    destination = arguments.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
