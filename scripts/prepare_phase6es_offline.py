"""Freeze Phase 6ES Point classification before runtime."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from phase6er_point_collision_geometry import corrected_plan_payload

CASES=(
 ("A_filtered_933","allow_self_center",-.0125,True),
 ("B_full_100","allow_other_support",-.0125,True),
 ("C_offset_zero_filtered","allow_self_center",0.0,True),
 ("E_collision_off","strict_all",0.0,False),
)

def main():
 p=argparse.ArgumentParser();p.add_argument("--output",required=True,type=Path);p.add_argument("--records-output",type=Path);a=p.parse_args()
 records_output=a.records_output or a.output.with_name("point_records.jsonl")
 records_output.parent.mkdir(parents=True,exist_ok=True)
 rows=[];point_record_count=0
 with records_output.open("w",encoding="utf-8",newline="\n") as stream:
  for name,policy,offset,filtering in CASES:
   plan=corrected_plan_payload("production_four",offset,.05,filtering,policy)
   for record in plan["records"]:
    stream.write(json.dumps({"condition":name,"policy":policy,"offset_from_point_cell_center_m":offset,"filtering":filtering,**record},separators=(",",":"),allow_nan=False,default=lambda value:value.item())+"\n")
    point_record_count+=1
   rows.append({"name":name,"policy":policy,"offset_from_point_cell_center_m":offset,"filtering":filtering,**{k:plan[k] for k in ("original_point_count","active_point_count","self_center_inside_count","other_center_inside_count","self_support_intersection_count","other_support_intersection_count","active_other_support_intersection_count","disable_reason_counts","weighted_supply")},"self_signed_distance":{"minimum_m":min(x["self_signed_distance_m"] for x in plan["records"]),"maximum_m":max(x["self_signed_distance_m"] for x in plan["records"])},"other_signed_distance":{"minimum_m":min(x["other_min_signed_distance_m"] for x in plan["records"]),"maximum_m":max(x["other_min_signed_distance_m"] for x in plan["records"])}})
 digest=hashlib.sha256()
 with records_output.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
 report={"schema":"campfire.phase6es.offline-point-classification.v1","phase":"phase6es","support_radius_m":.05,"support_radius_status":"engineering assumption equal to one velocity voxel; not a public Flow support radius","offset_zero_meaning":"surface-cell centers remain approximately 13.125 mm inside the authored CollisionProxy; offset is relative to Point cell center, not the mathematical Mesh surface","point_records":{"path":records_output.name,"format":"JSONL; one bounded record per condition and immutable payload index","count":point_record_count,"sha256":digest.hexdigest().upper()},"rows":rows,"gates":{"A_1344":rows[0]["active_point_count"]==1344,"B_1440":rows[1]["active_point_count"]==1440,"B_other_center_inside_zero":rows[1]["other_center_inside_count"]==0,"B_active_other_support_96":rows[1]["active_other_support_intersection_count"]==96,"C_1280":rows[2]["active_point_count"]==1280}}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
 if not all(report["gates"].values()):raise SystemExit("Phase 6ES offline gate failed")
 print("Phase 6ES offline classification frozen")
if __name__=="__main__":main()
