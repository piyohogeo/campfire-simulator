"""Validate and visualize the Phase 6BZ checkpoint-session report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _svg(report):
    session = report["session"]
    passed = sum(bool(value) for value in report["gates"].values())
    total = len(report["gates"])
    export_values = " / ".join(
        f"{value:.4f}" for value in session["save_export_ms"]
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6BZ explicit Resident save barrier</title>
<desc id="desc">An owner-thread session pauses publication, clones the stage, saves atomically, resumes, and produces the same next revision as a restored session.</desc>
<style>.bg{{fill:#08121f}} .panel{{fill:#111f31;stroke:#29415f;stroke-width:1.5}} .title{{fill:#f7fafc;font:700 30px system-ui,sans-serif}} .subtitle{{fill:#9fb3c8;font:15px system-ui,sans-serif}} .head{{fill:#7dd3fc;font:700 16px system-ui,sans-serif}} .body{{fill:#cbd5e1;font:14px system-ui,sans-serif}} .ok{{fill:#86efac;font:700 19px system-ui,sans-serif}} .arrow{{fill:#38bdf8;font:700 22px system-ui,sans-serif}} .warn{{fill:#fbbf24;font:700 14px system-ui,sans-serif}}</style>
<rect width="1200" height="680" class="bg"/>
<text x="62" y="58" class="title">Phase 6BZ · Explicit Resident save barrier</text>
<text x="62" y="87" class="subtitle">Isolated Kit controller · same live session continues · production integration remains off</text>
<rect x="50" y="120" width="1100" height="214" rx="16" class="panel"/>
<text x="72" y="158" class="head">One owner-thread barrier; live USD stage stays untouched</text>
<text x="76" y="213" class="body">running rev 2</text><text x="190" y="213" class="arrow">→</text>
<text x="226" y="194" class="body">pause adapter</text><text x="226" y="219" class="body">export SoA</text><text x="342" y="213" class="arrow">→</text>
<text x="378" y="194" class="body">clone stage</text><text x="378" y="219" class="body">write model JSON</text><text x="510" y="213" class="arrow">→</text>
<text x="546" y="194" class="body">atomic package</text><text x="546" y="219" class="body">replace or reject</text><text x="682" y="213" class="arrow">→</text>
<text x="718" y="194" class="body">resume adapter</text><text x="718" y="219" class="body">revision unchanged</text><text x="858" y="213" class="arrow">→</text>
<text x="894" y="194" class="body">next step</text><text x="894" y="219" class="body">rev 3 exact</text>
<text x="72" y="296" class="ok">{passed} / {total} session gates passed</text>
<rect x="50" y="362" width="530" height="220" rx="16" class="panel"/>
<text x="72" y="402" class="head">Failure and ownership</text>
<text x="72" y="446" class="body">✓ non-owner-thread save is rejected before pausing</text>
<text x="72" y="480" class="body">✓ interrupted replace preserves the previous package</text>
<text x="72" y="514" class="body">✓ failed save resumes revision 2 in the same session</text>
<text x="72" y="548" class="body">✓ save after close is rejected; close remains idempotent</text>
<rect x="608" y="362" width="542" height="220" rx="16" class="panel"/>
<text x="630" y="402" class="head">Continuity evidence</text>
<text x="630" y="446" class="body">2 successful saves + 1 injected failure</text>
<text x="630" y="480" class="body">SoA export: {export_values} ms</text>
<text x="630" y="514" class="body">continuous rev 3 = restored rev 3, exact result/snapshot</text>
<text x="630" y="548" class="warn">No UI or automatic save: persistent app owner is not implemented.</text>
<text x="62" y="630" class="body">Decision: session-owner boundary qualified as an isolated prototype · production defaults, physics, schemas, rollback, and USD publication unchanged</text>
</svg>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.raw.read_text(encoding="utf-8"))
    if report.get("status") != "ok":
        raise ValueError(f"Phase 6BZ raw report failed: {report}")
    if not all(report["gates"].values()):
        raise ValueError("Phase 6BZ checkpoint-session gate failed")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.svg.write_text(_svg(report), encoding="utf-8")


if __name__ == "__main__":
    main()
