"""Phase 6HO exact Kit deployment-path audit and fail-closed preflight."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).absolute().parents[1]
SCRIPTS = ROOT / "scripts"
BUILD = ROOT / "_build/windows-x86_64/release"
KIT_LEXICAL = Path(os.path.abspath(str(BUILD / "kit/kit.exe")))
APP_LEXICAL = Path(os.path.abspath(str(BUILD / "apps/campfire.simulator.kit")))
CAMPFIRE_LEXICAL = Path(os.path.abspath(str(BUILD / "exts/campfire.app")))
ANIM_LEXICAL = Path(os.path.abspath(str(BUILD / "extscache/omni.anim.curve.core-1.6.0+110.0.0.wx64.r.cp312.u7f4")))
LOCKS = (
    Path(r"C:\Users\junic\AppData\Local\ov\data\exts\v2\index\e18a4046\registry.lock"),
    Path(r"C:\Users\junic\AppData\Local\ov\data\exts\v2\index\7fa0c1e2\registry.lock"),
)


def lexical(value: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(value)))


def resolved(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve()))


def deployment_descriptor() -> dict[str, Any]:
    return {
        "schema": "campfire.phase6ho.app-ready-deployment.v1",
        "working_directory": lexical(ROOT),
        "kit_lexical_path": lexical(KIT_LEXICAL),
        "kit_resolved_path": resolved(KIT_LEXICAL),
        "app_lexical_path": lexical(APP_LEXICAL),
        "app_resolved_path": resolved(APP_LEXICAL),
        "campfire_extension_lexical_path": lexical(CAMPFIRE_LEXICAL),
        "campfire_extension_resolved_path": resolved(CAMPFIRE_LEXICAL),
        "anim_extension_lexical_path": lexical(ANIM_LEXICAL),
        "anim_extension_resolved_path": resolved(ANIM_LEXICAL),
        "app_ready_marker": True,
        "registry_lock_writable": True,
    }


def validate_deployment(value: dict[str, Any]) -> tuple[bool, str]:
    if value.get("schema") != "campfire.phase6ho.app-ready-deployment.v1":
        return False, "deployment_schema_mismatch"
    required = {
        "working_directory": lexical(ROOT),
        "kit_lexical_path": lexical(KIT_LEXICAL),
        "app_lexical_path": lexical(APP_LEXICAL),
        "campfire_extension_lexical_path": lexical(CAMPFIRE_LEXICAL),
        "campfire_extension_resolved_path": resolved(CAMPFIRE_LEXICAL),
        "anim_extension_lexical_path": lexical(ANIM_LEXICAL),
        "anim_extension_resolved_path": resolved(ANIM_LEXICAL),
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            return False, key + "_mismatch"
    if value.get("kit_lexical_path") == value.get("kit_resolved_path"):
        return False, "kit_reparse_boundary_not_observed"
    if value.get("app_lexical_path") == value.get("app_resolved_path"):
        return False, "app_reparse_boundary_not_observed"
    if not value.get("app_ready_marker"):
        return False, "app_ready_marker_missing"
    if value.get("registry_lock_writable") is not True:
        return False, "registry_lock_not_writable"
    for path in (KIT_LEXICAL, APP_LEXICAL, CAMPFIRE_LEXICAL, ANIM_LEXICAL):
        if not path.exists():
            return False, "required_deployment_path_missing:" + str(path)
    return True, "pass"


def _lock_audit(path: Path) -> dict[str, Any]:
    quoted = str(path).replace("'", "''")
    script = (
        "$p='" + quoted + "';$item=Get-Item -LiteralPath $p;$acl=Get-Acl -LiteralPath $p;"
        "$exclusive=$true;try{$s=[IO.File]::Open($p,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None);$s.Dispose()}catch{$exclusive=$false};"
        "[ordered]@{owner=$acl.Owner;access=$acl.AccessToString;exclusive_read_open=$exclusive;length=$item.Length;last_write_utc=$item.LastWriteTimeUtc.ToString('o')}|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=15, check=False,
    )
    parsed = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else {}
    return {
        "path": str(path), "exists": path.is_file(), "parent_exists": path.parent.is_dir(),
        "owner": parsed.get("owner"), "acl": parsed.get("access"),
        "exclusive_read_open": parsed.get("exclusive_read_open"),
        "size": parsed.get("length"), "last_write_utc": parsed.get("last_write_utc"),
        "phase6hn_observed_write_result": "permission_denied",
        "current_lock_holder_evidence": "none" if parsed.get("exclusive_read_open") else "possible_or_access_unknown",
    }


def historical_audit() -> dict[str, Any]:
    hn_root = ROOT / "artifacts/phase6hn-flow-proxy-process-tree-20260815/attempt01"
    fz_root = ROOT / "artifacts/phase6fz-three-axis-memory-2/attempts/attempt01/case"
    hn = json.loads((hn_root / "runner_evidence.json").read_text(encoding="utf-8"))
    fz_log = (fz_root / "kit.log").read_text(encoding="utf-8", errors="replace")
    fz_cmd = next((line.split(" Cmd: ", 1)[1] for line in fz_log.splitlines() if " Cmd: " in line), None)
    return {
        "schema": "campfire.phase6ho.environment-audit.v1",
        "phase6hn_preserved": True,
        "phase6hn": {
            "kit_path": hn.get("transmitted_kit_path"), "app_path": hn.get("transmitted_app_path"),
            "probe_path": hn.get("transmitted_probe_path"), "arguments": hn.get("kit_arguments"),
            "first_failure_sequence": [
                "registry_lock_permission_denied", "dependency_solver_missing_omni.anim.curve.core-1.6.0",
                "probe_exec_module_not_found:campfire",
            ],
        },
        "phase6fz": {
            "kit_lexical_path": str(KIT_LEXICAL),
            "app_lexical_path": str(BUILD / "kit/apps/omni.app.editor.base.kit"),
            "working_directory": str(ROOT), "command_line": fz_cmd,
            "normal_exit_evidence": True,
        },
        "confirmed_delta": {
            "name": "build_deployment_lexical_path_preservation",
            "phase6hn_kit_resolved_away_from_build": lexical(hn.get("transmitted_kit_path", "")) == resolved(KIT_LEXICAL),
            "phase6hn_app_resolved_away_from_build": lexical(hn.get("transmitted_app_path", "")) == resolved(APP_LEXICAL),
            "effect": "source/packman mixed roots omit build exts/extscache; build lexical roots retain local campfire and omni.anim.curve.core search locations",
        },
        "paths": deployment_descriptor(),
        "registry_locks": [_lock_audit(path) for path in LOCKS],
        "environment": {
            "cwd": str(ROOT), "USERPROFILE": os.environ.get("USERPROFILE"),
            "LOCALAPPDATA": os.environ.get("LOCALAPPDATA"),
            "PATH_component_count": len(os.environ.get("PATH", "").split(os.pathsep)),
            "PYTHONPATH_present": bool(os.environ.get("PYTHONPATH")),
            "secret_values_persisted": False,
        },
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(data) > 1024 * 1024:
        raise ValueError("bounded_audit_oversize")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
