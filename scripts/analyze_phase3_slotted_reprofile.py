"""Re-profile the adopted slotted authoritative wood-cell path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import analyze_phase3_adopted_reprofile as phase6aj
import analyze_phase3_inline_reprofile as phase6an


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "devlog" / "assets" / "phase6"
DEFAULT_JSON = ASSETS / "phase3_slotted_reprofile_report.json"
DEFAULT_SVG = DEFAULT_JSON.with_suffix(".svg")
PHASE6AN_JSON = ASSETS / "phase3_inline_reprofile_report.json"
PHASE6AO_JSON = ASSETS / "phase3_slotted_cell_report.json"


def _change(current: float, previous: float) -> float:
    return (current - previous) / previous * 100.0


def build_report(
    internal_paths: list[Path],
    sensible_paths: list[Path],
    phase6an_path: Path,
    phase6ao_path: Path,
) -> dict:
    internal_runs = [phase6aj._load(path) for path in internal_paths]
    sensible_runs = [phase6aj._load(path) for path in sensible_paths]
    for run in internal_runs + sensible_runs:
        if run.get("scenario", {}).get("python_slotted_wood_cell_storage") is not True:
            raise ValueError("Every profile must use slotted wood-cell storage")

    report = phase6an.build_report(
        internal_paths,
        sensible_paths,
        phase6an.PHASE6AL_JSON,
        phase6an.PHASE6AM_JSON,
    )
    previous = phase6aj._load(phase6an_path)
    adoption = phase6aj._load(phase6ao_path)
    if previous.get("phase") != "phase6an" or previous.get("status") != "ok":
        raise ValueError("Phase 6AN profile baseline is invalid")
    if adoption.get("phase") != "phase6ao" or adoption.get("status") != "ok":
        raise ValueError("Phase 6AO adoption report is invalid")
    if adoption.get("decision", {}).get("adopt_slotted_storage") is not True:
        raise ValueError("Phase 6AO did not adopt slotted storage")

    internal = report["internal_profile"]
    sensible = report["sensible_detail"]
    previous_internal = previous["internal_profile"]
    previous_sensible = previous["sensible_detail"]
    internal["phase6an_median_total_ms"] = previous_internal["median_total_ms"]
    internal["change_since_phase6an_percent"] = _change(
        internal["median_total_ms"], previous_internal["median_total_ms"]
    )
    sensible["sensible_change_since_phase6an_percent"] = _change(
        internal["segments"]["sensible_heat"]["median_mean_ms"],
        previous_internal["segments"]["sensible_heat"]["median_mean_ms"],
    )
    sensible["heat_capacity_change_since_phase6an_percent"] = _change(
        sensible["segments"]["heat_capacity_evaluation"]["median_mean_ms"],
        previous_sensible["segments"]["heat_capacity_evaluation"]["median_mean_ms"],
    )
    internal.pop("phase6al_median_total_ms", None)
    internal.pop("change_since_phase6al_percent", None)
    sensible.pop("sensible_change_since_phase6al_percent", None)
    sensible.pop("heat_capacity_change_since_phase6al_percent", None)

    report["phase"] = "phase6ap"
    report["environment"]["slotted_wood_cell_storage"] = True
    report["comparison_note"] = (
        "Phase 6AN and Phase 6AP are separate-launch profiles used only as "
        "context; Phase 6AO is the causal alternating adoption gate."
    )
    report["baselines"] = {
        "phase6an": str(phase6an_path.resolve().relative_to(ROOT)),
        "phase6ao": str(phase6ao_path.resolve().relative_to(ROOT)),
    }
    return report


def render_svg(report: dict) -> str:
    svg = phase6an.render_svg(report)
    return (
        svg.replace("Phase 6AN adopted inline-path reprofile", "Phase 6AP adopted slotted-path reprofile")
        .replace("PHASE 6AN - ADOPTED INLINE PATH REPROFILE", "PHASE 6AP - ADOPTED SLOTTED PATH REPROFILE")
        .replace("Re-rank costs after removing the closure", "Re-rank costs after slotted cell adoption")
        .replace("inline path active", "slotted cells active")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--sensible-summary", type=Path, nargs="+", required=True)
    parser.add_argument("--phase6an-report", type=Path, default=PHASE6AN_JSON)
    parser.add_argument("--phase6ao-report", type=Path, default=PHASE6AO_JSON)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-svg", type=Path, default=DEFAULT_SVG)
    arguments = parser.parse_args()
    report = build_report(
        arguments.internal_summary,
        arguments.sensible_summary,
        arguments.phase6an_report,
        arguments.phase6ao_report,
    )
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    arguments.report_svg.write_text(render_svg(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
