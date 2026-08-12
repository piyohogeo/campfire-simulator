"""Write the Phase 6ER legacy-versus-corrected four-log audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from phase6ep_point_collision_geometry import SCENARIOS
from phase6er_point_collision_geometry import write_audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = write_audit(args.output, SCENARIOS["production_four"])
    print(f"Phase 6ER geometry qualified={report['qualified_for_scalar_calibration']}")
    return 0 if report["qualified_for_scalar_calibration"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
