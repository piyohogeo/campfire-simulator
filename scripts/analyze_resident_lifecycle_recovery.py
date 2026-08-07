"""Validate and visualize the Phase 6BX lifecycle recovery report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _svg(report):
    passed = sum(bool(value) for value in report["gates"].values())
    total = len(report["gates"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6BX Resident lifecycle recovery</title>
<desc id="desc">Native rollback, downstream USD replay, shutdown export, and same-stage revision-continuous restart all pass.</desc>
<style>.bg{{fill:#08121f}} .panel{{fill:#111f31;stroke:#29415f;stroke-width:1.5}} .title{{fill:#f7fafc;font:700 30px system-ui,sans-serif}} .subtitle{{fill:#9fb3c8;font:15px system-ui,sans-serif}} .head{{fill:#7dd3fc;font:700 16px system-ui,sans-serif}} .body{{fill:#cbd5e1;font:14px system-ui,sans-serif}} .ok{{fill:#86efac;font:700 19px system-ui,sans-serif}} .arrow{{fill:#38bdf8;font:700 24px system-ui,sans-serif}} .warn{{fill:#fbbf24;font:700 14px system-ui,sans-serif}}</style>
<rect width="1200" height="680" class="bg"/>
<text x="62" y="58" class="title">Phase 6BX · Resident lifecycle recovery</text>
<text x="62" y="87" class="subtitle">Real MSVC native backend · in-memory Kit USD · production defaults unchanged</text>
<rect x="50" y="120" width="1100" height="214" rx="16" class="panel"/>
<text x="72" y="158" class="head">One continuous recovery sequence</text>
<text x="88" y="220" class="body">rev 1 commit</text><text x="208" y="220" class="arrow">→</text>
<text x="248" y="201" class="body">native failure</text><text x="248" y="226" class="body">exact rollback</text><text x="374" y="220" class="arrow">→</text>
<text x="414" y="220" class="body">rev 2 retry</text><text x="526" y="220" class="arrow">→</text>
<text x="566" y="201" class="body">USD revision-last failure</text><text x="566" y="226" class="body">rev 2 snapshot replay</text><text x="752" y="220" class="arrow">→</text>
<text x="792" y="201" class="body">rev 3 retry</text><text x="792" y="226" class="body">shutdown export</text><text x="902" y="220" class="arrow">→</text>
<text x="942" y="201" class="body">resume 3</text><text x="942" y="226" class="body">commit rev 4</text>
<text x="72" y="296" class="ok">{passed} / {total} lifecycle gates passed</text>
<rect x="50" y="362" width="530" height="220" rx="16" class="panel"/>
<text x="72" y="402" class="head">Rollback and retry</text>
<text x="72" y="446" class="body">✓ native arrays, counters, revision, and tick restored</text>
<text x="72" y="480" class="body">✓ immutable snapshot replay restores all 19 USD values</text>
<text x="72" y="514" class="body">✓ backend may stay ahead until the same snapshot retries</text>
<text x="72" y="548" class="body">✓ adapter revision advances only after complete commit</text>
<rect x="608" y="362" width="542" height="220" rx="16" class="panel"/>
<text x="630" y="402" class="head">Shutdown and same-stage resume</text>
<text x="630" y="446" class="body">✓ one export; backend and adapter close are idempotent</text>
<text x="630" y="480" class="body">✓ explicit revision/tick seed continues 3 → 4</text>
<text x="630" y="514" class="body">✓ all three consumer revisions must match before resume</text>
<text x="630" y="548" class="warn">Resume is explicit; default fresh-run revision remains zero.</text>
<text x="62" y="630" class="body">Scope: lifecycle contract only · no Flow performance claim · physics, JSON schema, snapshots, and default settings unchanged</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.raw.read_text(encoding="utf-8"))
    if report.get("status") != "ok":
        raise ValueError(f"Phase 6BX raw report failed: {report}")
    if not all(report["gates"].values()):
        raise ValueError("Phase 6BX lifecycle gate failed")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")


if __name__ == "__main__":
    main()
