"""Pairwise OFF versus Collision ON scalar/velocity gate for Phase 6ER."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _spatial(case: Path, channel: str, band: str, metric: str, scenario: str) -> float:
    result = 0.0
    folders = [case / "spatial" / "collider_1"] if scenario == "lower_upper" else sorted((case / "spatial").glob("collider_*"))
    for path in (path for folder in folders for path in folder.glob(f"*_{channel}.npz")):
        with np.load(path) as data:
            values = data["magnitude"].astype(np.float64)
            depth = data["mesh_distance_voxels"].astype(np.float64)
            mask = depth < -1.0
            if band == "center":
                mask &= data["axis_radial_distance_m"].astype(np.float64) <= 0.5 * float(np.max(data["voxel_size_xyz"]))
            if mask.any():
                value = float(values[mask].sum()) if metric == "sum" else float(values[mask].max())
                result = max(result, value)
    return result


def _roi(case: Path, channel: str, roi: str) -> float:
    raw = json.loads((case / "raw.json").read_text(encoding="utf-8"))
    return max((float(sample.get("channels", {}).get(channel, {}).get("rois", {}).get(roi, {}).get("sum", 0.0)) for sample in raw.get("samples", [])), default=0.0)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--off",required=True,type=Path);parser.add_argument("--candidate",required=True,type=Path)
    parser.add_argument("--contract",required=True,type=Path);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();contract=json.loads(args.contract.read_text(encoding="utf-8"));t=contract["thresholds"]
    raw=json.loads((args.candidate/"raw.json").read_text(encoding="utf-8"));scenario=raw["arguments"]["scenario"]
    failures=[]; metrics={}
    off_v=_spatial(args.off,"velocity","deep","maximum",scenario);on_v=_spatial(args.candidate,"velocity","deep","maximum",scenario)
    ratio_v=on_v/max(off_v,1e-30)
    metrics["velocity"]={"off_deep_maximum":off_v,"on_deep_maximum":on_v,"ratio":ratio_v}
    if off_v<t["collision_off_deep_velocity_minimum_m_s"]:failures.append("off_velocity_positive")
    if ratio_v>t["collision_on_to_off_deep_velocity_ratio"]:failures.append("velocity_ratio")
    scalar_gate_applied=scenario=="lower_upper"
    for channel in ("temperature","smoke"):
        values={}
        for band in ("deep","center"):
            off=_spatial(args.off,channel,band,"sum",scenario);on=_spatial(args.candidate,channel,band,"sum",scenario)
            values[band]={"off_sum":off,"on_sum":on,"ratio":on/max(off,1e-30)}
        for roi in ("opposite_side","far_above"):
            off=_roi(args.off,channel,roi);on=_roi(args.candidate,channel,roi)
            values[roi]={"off_sum":off,"on_sum":on,"ratio":on/max(off,1e-30)}
        metrics[channel]=values
        if scalar_gate_applied:
            if values["deep"]["off_sum"]<t[f"collision_off_{channel}_deep_sum_minimum"]:failures.append(f"off_{channel}_positive")
            if values["deep"]["ratio"]>t[f"collision_on_to_off_{channel}_deep_sum_ratio"]:failures.append(f"{channel}_deep_ratio")
            if values["center"]["ratio"]>t[f"collision_on_to_off_{channel}_center_sum_ratio"]:failures.append(f"{channel}_center_ratio")
            if values["opposite_side"]["ratio"]>t[f"collision_on_to_off_{channel}_opposite_sum_ratio"]:failures.append(f"{channel}_opposite_ratio")
            if values["far_above"]["ratio"]>t[f"collision_on_to_off_{channel}_far_sum_ratio"]:failures.append(f"{channel}_far_ratio")
    report={"schema":"campfire.phase6er.pair-gate.v1","phase":"phase6er","scenario":scenario,
        "policy":raw["arguments"]["policy"],"passed":not failures,"failed_gates":failures,
        "scalar_gate_applied":scalar_gate_applied,"scalar_gate_reason":"upper blocker is emitterless" if scalar_gate_applied else "all four logs emit; ownership and leakage are inseparable",
        "metrics":metrics}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"Phase 6ER pair {scenario}/{report['policy']} passed={not failures}")
    return 0 if not failures else 1


if __name__=="__main__":raise SystemExit(main())
