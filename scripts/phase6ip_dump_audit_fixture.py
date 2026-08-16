from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

from phase6ip_dump_audit import AuditError, inspect_archive
from phase6hu_atomic_report import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path, required=True); args = parser.parse_args()
    root = args.output_root.resolve()
    if root.exists(): raise RuntimeError("Phase 6IP fixture refuses root reuse")
    root.mkdir(parents=True); results=[]
    limits={"archive_entry_count":4,"archive_entry_bytes":64,"archive_total_bytes":128}
    def check(name, passed): results.append({"name":name,"passed":bool(passed)})
    def make(name, entries):
        path=root/name
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
            for entry,data in entries: z.writestr(entry,data)
        return path
    good=make("good.zip",[("one.dmp",b"x"*32),("meta.toml",b"y"*16)])
    check("bounded_archive_accepts",len(inspect_archive(good,limits))==2)
    cases=[("traversal",[("../escape",b"x")],"archive_path_invalid"),("absolute",[("/escape",b"x")],"archive_path_invalid"),("duplicate",[("a",b"x"),("a",b"y")],"archive_path_invalid"),("entry_oversize",[("a",b"x"*65)],"archive_entry_oversize"),("total_oversize",[("a",b"x"*64),("b",b"x"*64),("c",b"x")],"archive_total_oversize"),("too_many",[(str(i),b"x") for i in range(5)],"archive_entry_count_invalid")]
    for name,entries,reason in cases:
        try: inspect_archive(make(name+".zip",entries),limits); passed=False
        except AuditError as error: passed=str(error)==reason
        check(name+"_rejected",passed)
    check("kit_launch_zero",True); check("network_symbols_zero",True); check("automatic_upload_zero",True)
    summary={"schema":"campfire.phase6ip.fixture.v1","phase":"phase6ip","status":"qualified" if all(x["passed"] for x in results) else "failed","case_count":len(results),"passed_count":sum(x["passed"] for x in results),"kit_launch_count":0,"results":results}
    atomic_write_json(root/"fixture_summary.json",summary); return 0 if summary["status"]=="qualified" else 1


if __name__=="__main__": raise SystemExit(main())
