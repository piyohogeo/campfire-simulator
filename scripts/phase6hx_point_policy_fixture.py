"""No-Kit producer-to-parent fixture for the canonical Phase 6HX Point source set."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from phase6hx_point_policy_invariant import (
    InvariantError,
    _ordered_digest,
    consume_report,
    produce_report,
    sha256_bytes,
    validate_manifest,
    write_report,
)


def _record(cases: list[dict], name: str, passed: bool, **evidence) -> None:
    cases.append({"name": name, "passed": bool(passed), **evidence})


def _write_manifest(root: Path, value: dict, name: str = "manifest") -> tuple[Path, Path]:
    path = root / f"{name}.json"
    sidecar = root / f"{name}.sha256"
    data = json.dumps(value, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(data)
    sidecar.write_text(f"{sha256_bytes(data)}  {path.name}\n", encoding="ascii")
    return path, sidecar


def _mutated_manifest(base: dict, mutate) -> dict:
    value = copy.deepcopy(base)
    mutate(value)
    value["ordered_entries_sha256"] = _ordered_digest(value["entries"])
    return value


def _mirror_repository(root: Path, source_repo: Path, manifest: dict) -> Path:
    mirror = root / "mirror"
    for entry in manifest["entries"]:
        source = source_repo / Path(*entry["path"].split("/"))
        target = mirror / Path(*entry["path"].split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return mirror


def _expect_failure(cases: list[dict], name: str, expected: str, operation) -> None:
    try:
        operation()
    except InvariantError as error:
        _record(cases, name, str(error).startswith(expected), reason=str(error), expected=expected)
    else:
        _record(cases, name, False, reason="unexpected_pass", expected=expected)


def run_fixture(output_root: Path, manifest_path: Path, sidecar_path: Path, repo_root: Path) -> dict:
    if output_root.exists():
        raise RuntimeError("Phase 6HX point-policy fixture refuses root reuse")
    output_root.mkdir(parents=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[dict] = []
    attempt_id = "phase6hx-point-policy-fixture-positive"
    report = produce_report(manifest_path, sidecar_path, repo_root, attempt_id)
    report_path = output_root / "actual_producer_report.json"
    write_report(report_path, report)
    consumed = consume_report(report_path, manifest_path, sidecar_path, repo_root, attempt_id)
    _record(cases, "actual_repository_source_set", consumed == report and report["entry_count"] == 13, entry_count=report["entry_count"], manifest_sha256=report["manifest_sha256"])
    _record(cases, "producer_to_file_to_parent_round_trip", consumed == report, report_bytes=report_path.stat().st_size)
    _record(cases, "bounded_projection", report_path.stat().st_size < 128 * 1024, report_bytes=report_path.stat().st_size)

    mirror = _mirror_repository(output_root, repo_root, manifest)
    mirror_manifest = output_root / "mirror_manifest.json"
    mirror_sidecar = output_root / "mirror_manifest.sha256"
    shutil.copy2(manifest_path, mirror_manifest)
    shutil.copy2(sidecar_path, mirror_sidecar)
    missing_target = mirror / Path(*manifest["entries"][7]["path"].split("/"))
    missing_target.unlink()
    _expect_failure(cases, "one_file_missing", "manifest_entry_missing:7", lambda: validate_manifest(mirror_manifest, mirror_sidecar, mirror))

    legacy = _mutated_manifest(manifest, lambda value: value.__setitem__("entries", [{"order": 0, "path": "source/extensions/campfire.app/campfire/app/point_emitter.py", "role": "legacy", "sha256": "0" * 64}]))
    legacy_path, legacy_sidecar = _write_manifest(output_root, legacy, "legacy_only")
    _expect_failure(cases, "legacy_point_emitter_only", "legacy_point_emitter_path_forbidden", lambda: validate_manifest(legacy_path, legacy_sidecar, repo_root))

    def duplicate(value):
        value["entries"].append(copy.deepcopy(value["entries"][-1]))
        for index, entry in enumerate(value["entries"]):
            entry["order"] = index
    duplicate_value = _mutated_manifest(manifest, duplicate)
    duplicate_path, duplicate_sidecar = _write_manifest(output_root, duplicate_value, "duplicate")
    _expect_failure(cases, "duplicate_entry", "manifest_entry_duplicate:13", lambda: validate_manifest(duplicate_path, duplicate_sidecar, repo_root))

    reordered = _mutated_manifest(manifest, lambda value: value["entries"].__setitem__(slice(0, 2), [value["entries"][1], value["entries"][0]]))
    reordered_path, reordered_sidecar = _write_manifest(output_root, reordered, "reordered")
    _expect_failure(cases, "entry_order_changed", "manifest_entry_order_invalid:0", lambda: validate_manifest(reordered_path, reordered_sidecar, repo_root))

    bad_sha = _mutated_manifest(manifest, lambda value: value["entries"][8].__setitem__("sha256", "A" * 64))
    bad_sha_path, bad_sha_sidecar = _write_manifest(output_root, bad_sha, "bad_sha")
    _expect_failure(cases, "entry_sha_mismatch", "manifest_entry_sha_mismatch:8", lambda: validate_manifest(bad_sha_path, bad_sha_sidecar, repo_root))

    escaped = _mutated_manifest(manifest, lambda value: value["entries"][0].__setitem__("path", "outside.py"))
    escape_path, escape_sidecar = _write_manifest(output_root, escaped, "escape")
    _expect_failure(cases, "source_root_escape", "manifest_entry_path_invalid:0", lambda: validate_manifest(escape_path, escape_sidecar, repo_root))

    _expect_failure(cases, "manifest_missing", "bounded_json_missing", lambda: validate_manifest(output_root / "missing.json", sidecar_path, repo_root))
    wrong_schema = copy.deepcopy(manifest)
    wrong_schema["schema"] = "campfire.unknown"
    wrong_schema_path, wrong_schema_sidecar = _write_manifest(output_root, wrong_schema, "wrong_schema")
    _expect_failure(cases, "manifest_schema_mismatch", "manifest_schema_mismatch", lambda: validate_manifest(wrong_schema_path, wrong_schema_sidecar, repo_root))

    alternate = _mutated_manifest(manifest, lambda value: value["entries"][0].__setitem__("role", value["entries"][0]["role"] + " altered"))
    alternate_path, alternate_sidecar = _write_manifest(output_root, alternate, "alternate_valid")
    producer_report = produce_report(manifest_path, sidecar_path, repo_root, "producer-runner-mismatch")
    mismatch_report = output_root / "producer_runner_mismatch_report.json"
    write_report(mismatch_report, producer_report)
    _expect_failure(cases, "producer_and_runner_different_set", "producer_runner_source_set_mismatch", lambda: consume_report(mismatch_report, alternate_path, alternate_sidecar, repo_root, "producer-runner-mismatch"))

    tampered = copy.deepcopy(report)
    tampered["entries"] = tampered["entries"][:-1]
    tampered_path = output_root / "tampered_report.json"
    write_report(tampered_path, tampered)
    _expect_failure(cases, "consumer_rejects_missing_report_entry", "producer_runner_source_set_mismatch", lambda: consume_report(tampered_path, manifest_path, sidecar_path, repo_root, attempt_id))

    report_summary = {
        "schema": "campfire.phase6hx.point-policy-fixture.v1",
        "phase": "phase6hx",
        "status": "qualified" if all(case["passed"] for case in cases) else "failed",
        "kit_launch_count": 0,
        "case_count": len(cases),
        "canonical_entry_count": report["entry_count"],
        "canonical_manifest_sha256": report["manifest_sha256"],
        "cases": cases,
    }
    (output_root / "fixture_report.json").write_text(json.dumps(report_summary, indent=2) + "\n", encoding="utf-8")
    return report_summary
