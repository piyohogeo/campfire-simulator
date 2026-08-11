"""Validate local devlog references and machine-readable assets."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "docs" / "devlog"
    html = (root / "index.html").read_text(encoding="utf-8")
    if "\ufffd" in html:
        raise ValueError("replacement character in devlog HTML")
    ids = re.findall(r'\bid="([^"]+)"', html)
    duplicates = sorted(value for value in set(ids) if ids.count(value) > 1)
    if duplicates:
        raise ValueError(f"duplicate HTML ids: {duplicates}")
    refs = sorted(set(re.findall(r'\b(?:href|src)="([^"]+)"', html)))
    missing = []
    for reference in refs:
        if not reference or re.match(r"^(?:#|https?:|data:|mailto:|javascript:)", reference):
            continue
        relative = reference.split("#", 1)[0].split("?", 1)[0]
        if not (root / relative).resolve().exists():
            missing.append(reference)
    if missing:
        raise FileNotFoundError(f"missing devlog references: {missing}")
    json_files = list((root / "assets").rglob("*.json"))
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8-sig"))
    svg_files = list((root / "assets").rglob("*.svg"))
    for path in svg_files:
        ET.parse(path)
    zip_files = list((root / "assets").rglob("*.zip"))
    for path in zip_files:
        with zipfile.ZipFile(path) as archive:
            corrupt = archive.testzip()
            if corrupt is not None:
                raise ValueError(f"corrupt ZIP member: {path}:{corrupt}")
    print(
        f"DEVLOG_OK refs={len(refs)} ids={len(ids)} "
        f"json={len(json_files)} svg={len(svg_files)} zip={len(zip_files)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
