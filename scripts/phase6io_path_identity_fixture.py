from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

from phase6ho_process_tree_topology import KIT
from phase6io_executable_identity import (
    MAX_JSON_BYTES, PathIdentityError, normalize_path_text,
    produce_path_identity_report, read_report, resolve_file_identity,
    validate_path_identity_report, write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_root.resolve()
    if root.exists():
        raise RuntimeError("Phase 6IO fixture refuses root reuse")
    root.mkdir(parents=True)
    results: list[dict] = []

    def check(name: str, passed: bool, details=None) -> None:
        results.append({"name": name, "passed": bool(passed), "details": details})

    lexical = KIT.resolve(strict=False)
    # Preserve the junction spelling; Path.resolve would erase the boundary.
    lexical = KIT.absolute()
    direct = Path(resolve_file_identity(lexical)["canonical_path"])
    pid = os.getpid()
    ticks = 134313180179568390
    helper_identity = {"pid": pid, "creation_time_filetime_ticks": ticks, "executable_path": str(direct)}
    actual = produce_path_identity_report(
        attempt_id="phase6io-fixture", lexical_launch_path=lexical,
        expected_lexical_launch_path=lexical, process_identity=helper_identity,
        launch_pid=pid, launch_creation_ticks=ticks,
    )
    raw = root / "actual_producer.json"
    write_report(raw, actual)
    consumed = read_report(raw)
    validation = validate_path_identity_report(consumed, attempt_id="phase6io-fixture")
    check("actual_producer_atomic_writer_bounded_reader_validator", validation["accepted"], validation)
    check("lexical_build_and_resolved_packman_match", actual["checks"]["canonical_file_match"], {"lexical": str(lexical), "resolved": str(direct)})
    check("junction_and_direct_path_same_file", resolve_file_identity(lexical)["file_index"] == resolve_file_identity(direct)["file_index"])

    variants = [
        str(lexical).upper(), str(lexical).replace("\\", "/"), "\\\\?\\" + str(lexical),
    ]
    for label, variant in zip(("case", "separator", "extended_prefix"), variants):
        evidence = resolve_file_identity(variant)
        check(label + "_normalization", evidence["canonical_path"] == actual["lexical_launch_file"]["canonical_path"], evidence["lexical_path"])

    for name, candidate in (
        ("nonexistent_path", root / "missing" / "kit.exe"),
        ("broken_junction_target", root / "broken-junction" / "kit.exe"),
    ):
        try:
            resolve_file_identity(candidate); rejected = False
        except PathIdentityError as error:
            rejected = error.reason == "path_open_failed"
        check(name, rejected)

    other = root / "kit.exe"
    other.write_bytes(b"not the Packman Kit binary")
    other_evidence = resolve_file_identity(other)
    check("same_name_different_file_rejected", not actual["lexical_launch_file"]["file_index"] == other_evidence["file_index"])
    fake_version = root / "packman-repo" / "kit-kernel" / "999.0.0" / "kit.exe"
    fake_version.parent.mkdir(parents=True)
    fake_version.write_bytes(b"different Packman version")
    fake_identity = copy.deepcopy(helper_identity); fake_identity["executable_path"] = str(fake_version)
    mismatch = produce_path_identity_report(
        attempt_id="phase6io-fixture", lexical_launch_path=lexical,
        expected_lexical_launch_path=lexical, process_identity=fake_identity,
        launch_pid=pid, launch_creation_ticks=ticks,
    )
    check("different_packman_version_rejected", not mismatch["accepted"] and mismatch["reasons"] == ["canonical_file_identity_mismatch"])

    def invalid(name: str, mutate, needle: str) -> None:
        value = copy.deepcopy(actual); mutate(value)
        outcome = validate_path_identity_report(value, attempt_id="phase6io-fixture")
        check(name, not outcome["accepted"] and any(needle in reason for reason in outcome["reasons"]), outcome)

    invalid("canonical_path_missing", lambda value: value["lexical_launch_file"].pop("canonical_path"), "launch_file_keys_invalid")
    invalid("canonical_path_duplicate_transport_key", lambda value: value.update(canonical_path="duplicate"), "unknown_key:canonical_path")
    invalid("canonical_path_conflict", lambda value: value["process_executable_file"].update(canonical_path=str(other)), "canonical_file_identity_mismatch")
    invalid("pid_match_creation_mismatch", lambda value: value["process_identity"].update(creation_time_filetime_ticks=ticks + 1), "creation_time_mismatch")
    invalid("creation_match_path_mismatch", lambda value: value["process_executable_file"].update(file_index=value["process_executable_file"]["file_index"] + 1), "canonical_file_identity_mismatch")
    invalid("pid_reuse_rejected", lambda value: value["process_identity"].update(pid=pid + 1, creation_time_filetime_ticks=ticks + 1), "pid_mismatch")
    invalid("producer_consumer_attempt_conflict", lambda value: value.update(attempt_id="other"), "attempt_identity_invalid")
    invalid("handle_balance_conflict", lambda value: value["handle_tracker"].update(open_handle_residual_count=1), "file_handle_balance_invalid")
    invalid("file_hash_conflict", lambda value: value["process_executable_file"].update(sha256="0" * 64), "canonical_file_identity_mismatch")
    invalid("unknown_field_rejected", lambda value: value.update(unknown=True), "unknown_key:unknown")

    try:
        produce_path_identity_report(
            attempt_id="phase6io-fixture", lexical_launch_path=other,
            expected_lexical_launch_path=lexical, process_identity=helper_identity,
            launch_pid=pid, launch_creation_ticks=ticks,
        ); rejected = False
    except PathIdentityError as error:
        rejected = error.reason == "launch_lexical_boundary_mismatch"
    check("arbitrary_junction_or_path_not_authorized", rejected)

    corrupt = root / "corrupt.json"; corrupt.write_text("{", encoding="utf-8")
    try: read_report(corrupt); rejected = False
    except (PathIdentityError, json.JSONDecodeError): rejected = True
    check("corrupt_json_rejected", rejected)
    oversize = root / "oversize.json"
    with oversize.open("wb") as stream: stream.truncate(MAX_JSON_BYTES + 1)
    try: read_report(oversize); rejected = False
    except PathIdentityError: rejected = True
    check("oversize_json_rejected", rejected)
    check("actual_handle_balance_zero", actual["handle_tracker"]["open_count"] == 2 and actual["handle_tracker"]["close_count"] == 2 and actual["handle_tracker"]["open_handle_residual_count"] == 0)
    check("x64_pointer_and_handle", actual["handle_tracker"]["pointer_size_bytes"] == 8 and actual["handle_tracker"]["handle_size_bytes"] == 8)
    check("normalized_text_equivalence", normalize_path_text(str(lexical).upper()) == normalize_path_text("\\\\?\\" + str(lexical)))
    summary = {
        "schema": "campfire.phase6io.path-fixture.v1", "phase": "phase6io",
        "status": "qualified" if all(item["passed"] for item in results) else "failed",
        "case_count": len(results), "passed_count": sum(item["passed"] for item in results),
        "kit_launch_count": 0, "results": results,
        "actual_lexical_path": str(lexical), "actual_resolved_path": str(direct),
    }
    write_report(root / "fixture_summary.json", summary)
    return 0 if summary["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
