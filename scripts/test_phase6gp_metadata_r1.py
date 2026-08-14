"""No-Kit fixtures for the Phase 6GP metadata-only boundary."""

from __future__ import annotations

import json
from pathlib import Path

from phase6gp_metadata_r1_contract import bounded_slot_metadata, classify


class MetadataOnlyArray:
    def __init__(self, shape=(4, 3), dtype="float32", nbytes=48):
        self.ndim = len(shape)
        self.shape = shape
        self.dtype = dtype
        self.size = 12 if shape else 1
        self.nbytes = nbytes

    def __iter__(self):
        raise AssertionError("element iteration is forbidden")

    def __getitem__(self, key):
        raise AssertionError("element access is forbidden")


def main() -> int:
    contract_path = Path(__file__).with_name("phase6gp_metadata_r1_contract.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    checks = []
    row = bounded_slot_metadata(2, MetadataOnlyArray())
    checks.extend([
        row["slot"] == 2,
        row["shape"] == [4, 3],
        row["dtype"] == "float32",
        row["size"] == 12,
        row["nbytes"] == 48,
        row["empty"] is False,
    ])
    empty = MetadataOnlyArray(shape=(0,), nbytes=0)
    empty.size = 0
    checks.append(bounded_slot_metadata(6, empty)["empty"] is True)
    checks.append(classify(True, True)["classification"] == "qualified")
    partial = classify(True, False)
    checks.extend([
        partial["operation_result"] == "partial_operation_evidence",
        partial["lifecycle_result"] == "failure",
        classify(False, True)["operation_result"] == "failure",
    ])
    checks.extend([
        contract["population"]["maximum_launches"] == 1,
        contract["scope"]["r2_or_formal_population_authorized"] is False,
        contract["artifact_bounds"]["field_body_allowed"] is False,
        contract["lifecycle"]["low_level_diagnostic_allowed"] is False,
    ])
    case_runner = Path(__file__).with_name("run_phase6fo_supply_case.ps1").read_text(encoding="utf-8")
    shutdown_policy = Path(__file__).with_name("kit_shutdown_policy.ps1").read_text(encoding="utf-8")
    phase_runner = Path(__file__).with_name("run_phase6gp_metadata_r1.ps1").read_text(encoding="utf-8")
    checks.extend([
        "[switch]$SkipLowLevelShutdownDiagnostic" in case_runner,
        "[switch]$SkipLowLevelDiagnostic" in shutdown_policy,
        "if ($SkipLowLevelDiagnostic.IsPresent)" in shutdown_policy,
        '"-SkipLowLevelShutdownDiagnostic"' in phase_runner,
    ])
    if not all(checks):
        raise SystemExit("Phase 6GP offline fixture failed")
    print(f"Phase 6GP offline fixtures passed: {len(checks)}/{len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
