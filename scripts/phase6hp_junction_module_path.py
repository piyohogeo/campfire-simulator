"""Read-only, fail-closed Phase 6HP module/junction identity contract."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).absolute().parents[1]
BUILD_EXTENSION_ROOT = Path(os.path.abspath(str(ROOT / "_build/windows-x86_64/release/exts/campfire.app")))
JUNCTION_RELATIVE_PATH = "campfire"
JUNCTION_PATH = BUILD_EXTENSION_ROOT / JUNCTION_RELATIVE_PATH
EXPECTED_TARGET = Path(os.path.abspath(str(ROOT / "source/extensions/campfire.app/campfire")))
EXPECTED_MODULE_FILE = EXPECTED_TARGET / "app/__init__.py"
EXPECTED_EXTENSION_ID = "campfire.app-0.1.0"
EXPECTED_EXTENSION_NAME = "campfire.app"
EXPECTED_EXTENSION_VERSION = "0.1.0"
EXPECTED_MODULE_NAME = "campfire.app"
EXPECTED_PACKAGE_NAME = "campfire"

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
SCHEMA = "campfire.phase6hp.junction-module-path-evidence.v1"

REQUIRED_KEYS = {
    "schema",
    "extension_id",
    "extension_name",
    "extension_version",
    "extension_root_lexical",
    "extension_root_resolved",
    "extension_root_is_reparse_point",
    "junction_relative_path",
    "junction_lexical_path",
    "junction_exists",
    "junction_is_reparse_point",
    "junction_reparse_tag",
    "junction_target_resolved",
    "junction_chain_depth",
    "target_reparse_point_count",
    "module_name",
    "package_name",
    "module_file_lexical",
    "module_file_resolved",
    "module_file_under_lexical_junction",
    "module_file_under_resolved_target",
}


def lexical(value: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(value)))


def resolved(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve(strict=True)))


def _is_within(candidate: str | Path, parent: str | Path) -> bool:
    try:
        return os.path.commonpath((lexical(candidate), lexical(parent))) == lexical(parent)
    except ValueError:
        return False


def _is_reparse_point(path: Path) -> tuple[bool, int]:
    stat_result = os.lstat(str(path))
    attributes = int(getattr(stat_result, "st_file_attributes", 0))
    tag = int(getattr(stat_result, "st_reparse_tag", 0))
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT), tag


def _target_reparse_count(target: Path) -> int:
    """Count reparse points from repository root through the declared target."""
    if not _is_within(target, ROOT):
        return -1
    relative = Path(lexical(target)).relative_to(Path(lexical(ROOT)))
    current = Path(lexical(ROOT))
    count = 0
    for part in relative.parts:
        current = current / part
        if current.exists() and _is_reparse_point(current)[0]:
            count += 1
    return count


def collect_module_path_evidence(
    *,
    extension_id: str,
    extension_root: str | Path,
    module_name: str,
    package_name: str,
    module_file: str | Path,
) -> dict[str, Any]:
    """Collect bounded evidence without changing the existing build junction."""
    root = Path(extension_root)
    junction = root / JUNCTION_RELATIVE_PATH
    root_reparse, _root_tag = _is_reparse_point(root)
    junction_reparse, junction_tag = _is_reparse_point(junction)
    module_lexical = lexical(module_file)
    module_resolved = resolved(module_file)
    extension_version = extension_id[len(EXPECTED_EXTENSION_NAME) + 1 :] if extension_id.startswith(EXPECTED_EXTENSION_NAME + "-") else ""
    return {
        "schema": SCHEMA,
        "extension_id": extension_id,
        "extension_name": EXPECTED_EXTENSION_NAME,
        "extension_version": extension_version,
        "extension_root_lexical": lexical(root),
        "extension_root_resolved": resolved(root),
        "extension_root_is_reparse_point": root_reparse,
        "junction_relative_path": JUNCTION_RELATIVE_PATH,
        "junction_lexical_path": lexical(junction),
        "junction_exists": junction.exists(),
        "junction_is_reparse_point": junction_reparse,
        "junction_reparse_tag": junction_tag,
        "junction_target_resolved": resolved(junction),
        "junction_chain_depth": 1,
        "target_reparse_point_count": _target_reparse_count(Path(resolved(junction))),
        "module_name": module_name,
        "package_name": package_name,
        "module_file_lexical": module_lexical,
        "module_file_resolved": module_resolved,
        "module_file_under_lexical_junction": _is_within(module_lexical, junction),
        "module_file_under_resolved_target": _is_within(module_resolved, EXPECTED_TARGET),
    }


def validate_module_path_evidence(value: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, dict):
        return False, "evidence_type_invalid"
    keys = set(value)
    missing = REQUIRED_KEYS - keys
    unknown = keys - REQUIRED_KEYS
    if missing:
        return False, "evidence_missing:" + sorted(missing)[0]
    if unknown:
        return False, "evidence_unknown:" + sorted(unknown)[0]
    if value["schema"] != SCHEMA:
        return False, "schema_mismatch"
    string_fields = REQUIRED_KEYS - {
        "extension_root_is_reparse_point",
        "junction_exists",
        "junction_is_reparse_point",
        "junction_reparse_tag",
        "junction_chain_depth",
        "target_reparse_point_count",
        "module_file_under_lexical_junction",
        "module_file_under_resolved_target",
    }
    for key in string_fields:
        if not isinstance(value[key], str) or not value[key]:
            return False, "evidence_string_invalid:" + key
    bool_fields = {
        "extension_root_is_reparse_point",
        "junction_exists",
        "junction_is_reparse_point",
        "module_file_under_lexical_junction",
        "module_file_under_resolved_target",
    }
    for key in bool_fields:
        if type(value[key]) is not bool:
            return False, "evidence_bool_invalid:" + key
    for key in ("junction_reparse_tag", "junction_chain_depth", "target_reparse_point_count"):
        if type(value[key]) is not int:
            return False, "evidence_int_invalid:" + key

    exact = {
        "extension_id": EXPECTED_EXTENSION_ID,
        "extension_name": EXPECTED_EXTENSION_NAME,
        "extension_version": EXPECTED_EXTENSION_VERSION,
        "extension_root_lexical": lexical(BUILD_EXTENSION_ROOT),
        "extension_root_resolved": resolved(BUILD_EXTENSION_ROOT),
        "junction_relative_path": JUNCTION_RELATIVE_PATH,
        "junction_lexical_path": lexical(JUNCTION_PATH),
        "junction_target_resolved": resolved(EXPECTED_TARGET),
        "module_name": EXPECTED_MODULE_NAME,
        "package_name": EXPECTED_PACKAGE_NAME,
    }
    for key, expected in exact.items():
        if value[key] != expected:
            return False, key + "_mismatch"
    if value["extension_root_is_reparse_point"]:
        return False, "extension_root_unexpected_reparse_point"
    if not value["junction_exists"]:
        return False, "junction_missing_or_broken"
    if not value["junction_is_reparse_point"]:
        return False, "junction_not_reparse_point"
    if value["junction_reparse_tag"] != IO_REPARSE_TAG_MOUNT_POINT:
        return False, "junction_reparse_tag_mismatch"
    if value["junction_chain_depth"] != 1 or value["target_reparse_point_count"] != 0:
        return False, "junction_chain_not_allowed"
    if not _is_within(value["junction_target_resolved"], ROOT):
        return False, "junction_target_outside_repository"
    if not _is_within(value["module_file_resolved"], EXPECTED_TARGET):
        return False, "module_resolved_outside_expected_target"
    if not value["module_file_under_resolved_target"]:
        return False, "module_resolved_target_membership_false"
    if not (
        value["module_file_under_lexical_junction"]
        or _is_within(value["module_file_lexical"], EXPECTED_TARGET)
    ):
        return False, "module_lexical_identity_mismatch"
    if Path(value["module_file_resolved"]).name != "__init__.py":
        return False, "module_file_name_mismatch"
    return True, "pass"


def validate_evidence_population(values: Iterable[dict[str, Any]]) -> tuple[bool, str]:
    rows = list(values)
    if len(rows) == 0:
        return False, "evidence_population_missing"
    if len(rows) != 1:
        return False, "evidence_population_duplicate"
    return validate_module_path_evidence(rows[0])


def actual_no_kit_evidence() -> dict[str, Any]:
    return collect_module_path_evidence(
        extension_id=EXPECTED_EXTENSION_ID,
        extension_root=BUILD_EXTENSION_ROOT,
        module_name=EXPECTED_MODULE_NAME,
        package_name=EXPECTED_PACKAGE_NAME,
        module_file=EXPECTED_MODULE_FILE,
    )
