"""No-Kit fixtures and static scope checks for Phase 6GT."""

from __future__ import annotations

import ast
import json
import os
import tempfile
from pathlib import Path

from phase6gs_harness_contract import ACCESSORS
from phase6gt_temporary_nvdb_contract import (
    MAXIMUM_FILE_BYTES,
    TEMPORARY_FILENAME,
    delete_exact_temporary,
    exact_temporary_path,
    poll_nonempty_file,
    require_absent,
    require_save_return,
)


def rejected(callable_) -> bool:
    try:
        callable_()
    except (FileExistsError, RuntimeError, TypeError, ValueError, TimeoutError):
        return True
    return False


def main() -> int:
    results = []

    def check(name: str, passed: bool, observed=None) -> None:
        results.append({"name": name, "passed": bool(passed), "observed": observed})

    with tempfile.TemporaryDirectory(prefix="phase6gt-fixture-") as raw_root:
        root = Path(raw_root).resolve()
        path = exact_temporary_path(root)
        check("fixed_path_inside_artifact", path.parent == root and path.name == TEMPORARY_FILENAME)
        require_absent(path)
        check("absent_before_save", True)
        check("save_true_accepted", require_save_return(True) is True)
        check("save_false_rejected", rejected(lambda: require_save_return(False)))
        check("save_nonboolean_rejected", rejected(lambda: require_save_return(1)))

        path.touch()
        os.truncate(path, 4096)
        poll = poll_nonempty_file(path, timeout_seconds=0.2, interval_seconds=0.01)
        check("nonempty_within_limit", poll["file_size_bytes"] == 4096 and poll["within_limit"], poll)
        neighbor = root / "must_not_delete.txt"
        neighbor.touch()
        os.truncate(neighbor, 1)
        deletion = delete_exact_temporary(path, root)
        check("exact_file_deleted", deletion["deleted"] and not path.exists(), deletion)
        check("neighbor_preserved", neighbor.exists())
        neighbor.unlink()

        path.touch()
        os.truncate(path, 0)
        check("empty_file_times_out", rejected(lambda: poll_nonempty_file(path, timeout_seconds=0.03, interval_seconds=0.01)))
        path.unlink()
        path.touch()
        os.truncate(path, MAXIMUM_FILE_BYTES + 1)
        check("oversize_rejected", rejected(lambda: poll_nonempty_file(path, timeout_seconds=0.1, interval_seconds=0.01)))
        path.unlink()
        path.touch()
        os.truncate(path, 1)
        check("preexisting_file_rejected", rejected(lambda: require_absent(path)))
        path.unlink()
        outside = root.parent / "not-phase6gt.nvdb"
        check("delete_path_escape_rejected", rejected(lambda: delete_exact_temporary(outside, root)))

    probe_path = Path(__file__).with_name("probe_phase6gt_temporary_nvdb.py")
    runner_path = Path(__file__).with_name("run_phase6gt_temporary_nvdb.ps1")
    if probe_path.exists() and runner_path.exists():
        source = probe_path.read_text(encoding="utf-8")
        runner = runner_path.read_text(encoding="utf-8")
        contract = json.loads(Path(__file__).with_name("phase6gt_temporary_nvdb_contract.json").read_text(encoding="utf-8"))
        tree = ast.parse(source, filename=str(probe_path))
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
        check("one_readback", calls.count("get_latest_nanovdb_readback") == 1)
        check("one_conversion", calls.count("buffer_to_volume") == 1)
        check("one_save_volume", calls.count("save_volume") == 1)
        check("qualified_accessor_counts", all(source.count(f".{name}(") == 1 for name in ACCESSORS))
        check("codec_none", "kNanoVDBCodecNone" in source)
        check("no_content_read_api", all(token not in source for token in ("read_bytes", "ReadAllBytes", "mmap", "hashlib")))
        check("no_reload_or_typed_metadata", "load_volume" not in calls and "typed" not in source.lower())
        check("no_numpy_asarray", "asarray" not in calls)
        check("no_sampling_collector_flux", all(token not in calls for token in ("sample", "save_and_sample", "flux")))
        cleanup_helper = Path(__file__).with_name("phase6gt_temporary_file_cleanup.ps1").read_text(encoding="utf-8")
        check("parent_exact_cleanup", contract["temporary_file"]["filename"] == TEMPORARY_FILENAME and "Join-Path $caseRoot $contract.temporary_file.filename" in runner and "Invoke-Phase6gtExactTemporaryCleanup" in runner and "Remove-Item -LiteralPath $exactPath" in cleanup_helper)
        check("runner_no_nvdb_content_read", all(token not in runner for token in ("Get-Content $temporaryPath", "ReadAllBytes", "Get-FileHash -LiteralPath $temporaryPath")))

    passed = all(item["passed"] for item in results)
    report = {
        "schema": "campfire.phase6gt.temporary-nvdb-fixture.v1",
        "passed": passed,
        "case_count": len(results),
        "kit_started": False,
        "cases": results,
    }
    output = Path(os.environ["PHASE6GT_FIXTURE_REPORT"]) if "PHASE6GT_FIXTURE_REPORT" in os.environ else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit(f"Phase 6GT fixtures failed: {[row['name'] for row in results if not row['passed']]}")
    print(f"Phase 6GT no-Kit fixtures passed: {len(results)}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
