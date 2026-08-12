"""Aggregate a complete Phase 6ER formal population."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


POLICIES = ("collision_off", "strict_all", "allow_self_support", "allow_self_center")


def _summary(values) -> dict:
    data=np.asarray(list(values),dtype=np.float64)
    if not data.size:return {"count":0,"minimum":0.0,"mean":0.0,"p50":0.0,"p95":0.0,"maximum":0.0}
    return {"count":int(data.size),"minimum":float(data.min()),"mean":float(data.mean()),"p50":float(np.quantile(data,.5)),"p95":float(np.quantile(data,.95)),"maximum":float(data.max())}


def _load(root: Path, directory: Path) -> dict:
    raw=json.loads((directory/"raw.json").read_text(encoding="utf-8"))
    inc=json.loads((directory/"incremental_gate.json").read_text(encoding="utf-8"))
    pair_path=directory/"pair_gate.json"
    pair=json.loads(pair_path.read_text(encoding="utf-8")) if pair_path.is_file() else None
    relative=directory.relative_to(root)
    guard_path=root/"runner-logs"/("_".join(relative.parts)+".guard.json")
    guard=json.loads(guard_path.read_text(encoding="utf-8"))
    return {"raw":raw,"incremental":inc,"pair":pair,"guard":guard}


def _svg(report: dict,path: Path)->None:
    rows=report["condition_summary"];height=170+58*len(rows);body=[]
    colors={"collision_off":"#ef4444","strict_all":"#3b82f6","allow_self_support":"#f59e0b","allow_self_center":"#22c55e"}
    for index,row in enumerate(rows):
        y=140+index*58;ret=row["weighted_fuel_retention"]["mean"]
        body.append(f'<text x="35" y="{y}" class="l">{row["scenario"]} / {row["policy"]}</text><rect x="510" y="{y-20}" width="{480*ret:.1f}" height="21" rx="4" fill="{colors[row["policy"]]}"/><text x="1010" y="{y}" class="v">supply {100*ret:.2f}% · deep v {row["deep_velocity_maximum_m_s"]:.2e}</text>')
    text=f'''<svg xmlns="http://www.w3.org/2000/svg" width="1480" height="{height}" viewBox="0 0 1480 {height}"><style>.t{{font:700 30px system-ui;fill:#f8fafc}}.s{{font:17px system-ui;fill:#94a3b8}}.l,.v{{font:15px ui-monospace;fill:#dbeafe}}</style><rect width="100%" height="100%" fill="#08111f"/><text x="35" y="48" class="t">Phase 6ER corrected geometry + scalar occlusion</text><text x="35" y="80" class="s">bars = weighted supply · scalar gates use lower/upper baseline-adjusted integral ratios</text>{''.join(body)}</svg>'''
    path.write_text(text,encoding="utf-8")


def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--root",required=True,type=Path);p.add_argument("--contract",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--svg",required=True,type=Path);a=p.parse_args()
    contract=json.loads(a.contract.read_text(encoding="utf-8"));entries=[];failures=[]
    for directory in sorted((a.root/"formal").glob("run_*/*/*")):
        if not (directory/"raw.json").is_file():continue
        x=_load(a.root,directory);raw=x["raw"];scenario=raw["arguments"]["scenario"];policy=raw["arguments"]["policy"] if raw["arguments"]["collision"] else "collision_off"
        if not x["incremental"]["passed"]:failures.append(f"incremental:{directory.relative_to(a.root)}")
        if policy!="collision_off" and (x["pair"] is None or not x["pair"]["passed"]):failures.append(f"pair:{directory.relative_to(a.root)}")
        entries.append({"run":directory.parents[1].name,"scenario":scenario,"policy":policy,
            "point_retention":float(raw["point_payload"]["supply_efficiency"]),"weighted_supply":raw["point_payload"]["weighted_supply"],
            "active_points":raw["point_payload"]["active_point_count"],"total_points":raw["point_payload"]["original_point_count"],
            "active_other_support_intersections":raw["point_payload"]["active_other_support_intersection_count"],
            "active_blocks":raw["active_blocks_final"],"source_sums":raw["source_sums"],
            "deep_velocity_maximum_m_s":x["incremental"]["deep_velocity_maximum_m_s"],
            "center_velocity_maximum_m_s":x["incremental"]["center_velocity_maximum_m_s"],
            "external_ignition_frame":x["incremental"]["external_ignition_frame"],
            "pair_gate":x["pair"],"resource_peaks":x["guard"]["peaks"],"process_absent":x["guard"]["process_absent"]})
    if len(entries)!=contract["formal_process_count"]:failures.append(f"process_count:{len(entries)}")
    summaries=[]
    for scenario in contract["formal_scenarios"]:
        for policy in POLICIES:
            selected=[e for e in entries if e["scenario"]==scenario and e["policy"]==policy]
            variation=[e["active_blocks"] for e in selected]
            relative=(max(variation)-min(variation))/max(float(np.mean(variation)),1e-30) if variation else math.inf
            if len(selected)==3 and relative>contract["thresholds"]["maximum_run_relative_variation"]:failures.append(f"variation:{scenario}:{policy}")
            summaries.append({"scenario":scenario,"policy":policy,"run_count":len(selected),
                "weighted_fuel_retention":_summary(e["weighted_supply"]["fuel"]["retention"] for e in selected),
                "deep_velocity_maximum_m_s":max((e["deep_velocity_maximum_m_s"] for e in selected),default=0.0),
                "center_velocity_maximum_m_s":max((e["center_velocity_maximum_m_s"] for e in selected),default=0.0),
                "active_blocks":_summary(e["active_blocks"] for e in selected),"active_block_relative_variation":relative})
    report={"schema":"campfire.phase6er.qualification-report.v1","phase":"phase6er","contract_sha256":hashlib.sha256(a.contract.read_bytes()).hexdigest().upper(),
        "qualified":not failures,"formal_process_count":len(entries),"entries":entries,"condition_summary":summaries,"failed_gates":failures,
        "phase6eq_reclassified":False,"production_connected":False,
        "scope":"default-off corrected four-log and lower/upper static coexistence probe; no production integration"}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8");_svg(report,a.svg)
    print(f"Phase 6ER formal qualified={not failures} processes={len(entries)}")
    return 0 if not failures else 1


if __name__=="__main__":raise SystemExit(main())
