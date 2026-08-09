"""Aggregate Phase V3T-G process outcomes and render its comparison SVG."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",type=Path,required=True); args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    groups=defaultdict(list)
    for row in manifest["entries"]: groups[(row["mode"],row["sequence"])].append(row)
    summary=[]
    for (mode,sequence),rows in sorted(groups.items()):
        counts=defaultdict(int)
        for row in rows: counts[row["classification"]]+=1
        summary.append({"mode":mode,"sequence":sequence,"runs":len(rows),"normal":counts["normal"],"access_violations":counts["access_violation_0xC0000005"],"timeouts":counts["timeout"],"other_nonzero":counts["nonzero_exit"],"last_markers":sorted({str(r.get("last_marker")) for r in rows})})
    access=sum(r["access_violations"] for r in summary)
    total=sum(r["runs"] for r in summary)
    gpu_a=next((r for r in summary if r["mode"]=="gpu_ring3_normal" and r["sequence"]=="A"),None)
    cpu=next((r for r in summary if r["mode"]=="cpu_reference" and r["sequence"]=="A"),None)
    reproduced=access>0
    classification=("reproduced; compare condition-specific rates without asserting an internal root cause" if reproduced else "not reproduced in this matrix; root cause and GPU lifetime safety remain unconfirmed")
    report={"schema":"campfire.phasev3tg.shutdown-report.v1","status":"ok","observed":{"processes":total,"access_violations":access,"groups":summary},"classification":classification,"inference_strength":"observed exit codes only; internal cause unconfirmed","re_adoption_qualified":False,"reason":"This isolation phase never integrates production; final 20-run lifecycle qualification was not claimed.","production_changed":False,"controls":{"cpu_A":cpu,"gpu_ring3_A":gpu_a}}
    output=args.manifest.parent/"shutdown_report.json"; output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    raw=[]
    for row in manifest["entries"]:
        marker_path=Path(row["markers"])
        markers=[]
        if marker_path.exists():
            markers=[json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines() if line]
        raw.append({"process":row,"markers":markers})
    (args.manifest.parent/"shutdown_samples.json").write_text(
        json.dumps({"schema":"campfire.phasev3tg.shutdown-samples.v1","processes":raw},ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8",
    )
    rows=[]
    for i,item in enumerate(summary):
        y=205+i*34; normal_w=520*item["normal"]/max(1,item["runs"]); crash_w=520*item["access_violations"]/max(1,item["runs"])
        rows.append(f'<text x="70" y="{y+20}" class="label">{item["mode"]} / {item["sequence"]}</text><rect x="430" y="{y}" width="520" height="24" rx="6" fill="#263447"/><rect x="430" y="{y}" width="{normal_w:.1f}" height="24" rx="6" fill="#22c55e"/><rect x="{430+normal_w:.1f}" y="{y}" width="{crash_w:.1f}" height="24" fill="#ef4444"/><text x="972" y="{y+19}" class="value">{item["normal"]}/{item["runs"]} normal · {item["access_violations"]} AV</text>')
    height=280+len(summary)*34
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img"><style>.title{{font:700 36px Segoe UI,sans-serif;fill:#f8fafc}}.sub{{font:17px Segoe UI,sans-serif;fill:#a7b2c2}}.label{{font:15px Segoe UI,sans-serif;fill:#f8fafc}}.value{{font:14px Segoe UI,sans-serif;fill:#cbd5e1}}.decision{{font:700 20px Segoe UI,sans-serif;fill:#fbbf24}}</style><rect width="1200" height="{height}" rx="28" fill="#0b1625"/><text x="70" y="62" class="sub">PHASE V3T-G · ISOLATED SHUTDOWN MATRIX</text><text x="70" y="112" class="title">Native exit codes, not Python exceptions</text><text x="70" y="148" class="sub">20 logs · 120×60 RGBA8 base + emission · Flow 110.0.0 · Kit 110.2</text>{''.join(rows)}<text x="70" y="{height-48}" class="decision">{total} processes · {access} access violation(s) · production unchanged</text><text x="70" y="{height-20}" class="sub">Green = normal exit; red = 0xC0000005. Absence of reproduction is not proof of safety.</text></svg>'''
    (args.manifest.parent/"shutdown_report.svg").write_text(svg,encoding="utf-8")
    index={"schema":"campfire.phasev3tg.crash-index.v1","entries":[{"name":r["name"],"classification":r["classification"],"exit_hex":r.get("exit_hex"),"last_marker":r.get("last_marker"),"kit_log":r.get("kit_log"),"excerpt":r.get("crash_excerpt",[])} for r in manifest["entries"] if r["classification"]!="normal"]}
    (args.manifest.parent/"crash_log_index.json").write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"processes":total,"access_violations":access,"report":str(output)}))

if __name__=="__main__": main()
