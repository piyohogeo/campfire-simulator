"""Validate the minimal structure and full-memory stream of a Windows minidump."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.dump.read_bytes()
    if len(data) < 32 or data[:4] != b"MDMP":
        raise RuntimeError("invalid minidump signature")
    stream_count, directory_rva = struct.unpack_from("<II", data, 8)
    streams = []
    for index in range(stream_count):
        offset = directory_rva + index * 12
        if offset + 12 > len(data):
            raise RuntimeError("truncated stream directory")
        stream_type, size, rva = struct.unpack_from("<III", data, offset)
        streams.append({"type": stream_type, "size": size, "rva": rva})
    collector = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
    report = {
        "schema": "campfire.phasev3tj.minidump-validation.v1",
        "status": "ok",
        "path": str(args.dump.resolve()),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "signature": "MDMP",
        "stream_count": stream_count,
        "stream_types": [row["type"] for row in streams],
        "memory64_list_stream_present": 9 in {row["type"] for row in streams},
        "collector": collector,
        "git_managed": False,
    }
    if not report["memory64_list_stream_present"]:
        raise RuntimeError("full-memory Memory64ListStream is absent")
    if collector.get("exception_hex") != "0xC0000005" or not collector.get("dump_written"):
        raise RuntimeError("collector did not record the expected access violation")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("size_bytes", "sha256", "memory64_list_stream_present")}))


if __name__ == "__main__":
    main()
