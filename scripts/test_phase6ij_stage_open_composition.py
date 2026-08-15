from pathlib import Path

from phase6ij_stage_open_composition_fixture import run_fixture


def test_phase6ij_stage_open_composition(tmp_path: Path):
    report = run_fixture(tmp_path / "phase6ij")
    assert report["status"] == "qualified", report
