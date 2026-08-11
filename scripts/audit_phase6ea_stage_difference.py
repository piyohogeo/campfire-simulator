"""Read-only normalized audit of the qualified 6DY and regenerated 6DZ stages."""

from __future__ import annotations

import difflib
import hashlib
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import carb
import omni.kit.app
from pxr import Usd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        return [_json_safe(item) for item in value]
    except TypeError:
        return str(value)


def _canonical_sha256(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def _stage_payload(path: Path) -> dict:
    stage = Usd.Stage.Open(str(path))
    if stage is None:
        raise RuntimeError(f"Unable to open stage: {path}")
    root = stage.GetRootLayer()
    prims = []
    for prim in stage.TraverseAll():
        attributes = []
        for attribute in prim.GetAttributes():
            attributes.append(
                {
                    "name": attribute.GetName(),
                    "type": str(attribute.GetTypeName()),
                    "variability": str(attribute.GetVariability()),
                    "custom": bool(attribute.IsCustom()),
                    "value": _json_safe(attribute.Get()),
                    "connections": [str(item) for item in attribute.GetConnections()],
                }
            )
        relationships = []
        for relationship in prim.GetRelationships():
            relationships.append(
                {
                    "name": relationship.GetName(),
                    "custom": bool(relationship.IsCustom()),
                    "targets": [str(item) for item in relationship.GetTargets()],
                }
            )
        prims.append(
            {
                "path": str(prim.GetPath()),
                "type": prim.GetTypeName(),
                "active": prim.IsActive(),
                "defined": prim.IsDefined(),
                "abstract": prim.IsAbstract(),
                "instanceable": prim.IsInstanceable(),
                "applied_schemas": list(prim.GetAppliedSchemas()),
                "metadata": _json_safe(prim.GetAllMetadata()),
                "children_order": [child.GetName() for child in prim.GetAllChildren()],
                "attributes": attributes,
                "relationships": relationships,
            }
        )
    payload = {
        "stage_metadata": _json_safe(stage.GetPseudoRoot().GetAllMetadata()),
        "root_layer": {
            "documentation": root.documentation,
            "comment": root.comment,
            "custom_layer_data": _json_safe(root.customLayerData),
            "default_prim": root.defaultPrim,
            "start_time_code": root.startTimeCode,
            "end_time_code": root.endTimeCode,
            "time_codes_per_second": root.timeCodesPerSecond,
            "frames_per_second": root.framesPerSecond,
        },
        "prim_order": [item["path"] for item in prims],
        "prims": prims,
    }
    del stage
    return payload


def _diff(left, right, prefix: str = "") -> list[dict]:
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                result.append({"path": path, "left": left.get(key), "right": right.get(key)})
            else:
                result.extend(_diff(left[key], right[key], path))
        return result
    if isinstance(left, list) and isinstance(right, list):
        result = []
        if len(left) != len(right):
            result.append({"path": f"{prefix}.length", "left": len(left), "right": len(right)})
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            result.extend(_diff(left_item, right_item, f"{prefix}[{index}]"))
        return result
    if left != right:
        return [{"path": prefix, "left": left, "right": right}]
    return []


def _text_audit(path: Path) -> dict:
    data = path.read_bytes()
    text = data.decode("utf-8")
    return {
        "sha256": _sha256(path),
        "bytes": len(data),
        "line_count": len(text.splitlines()),
        "crlf_count": data.count(b"\r\n"),
        "lf_count": data.count(b"\n"),
        "trailing_newline": data.endswith(b"\n"),
    }


def _main() -> None:
    settings = carb.settings.get_settings()
    left_path = Path(settings.get_as_string("/phase6ea/left")).resolve()
    right_path = Path(settings.get_as_string("/phase6ea/right")).resolve()
    output = Path(settings.get_as_string("/phase6ea/output")).resolve()
    app = omni.kit.app.get_app()
    report = {
        "schema": "campfire.phase6ea.stage-difference.v1",
        "phase": "phase6ea",
        "status": "running",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "inputs_read_only": True,
        "left": {"path": str(left_path)},
        "right": {"path": str(right_path)},
    }
    exit_code = 1
    try:
        left_text = _text_audit(left_path)
        right_text = _text_audit(right_path)
        left_payload = _stage_payload(left_path)
        right_payload = _stage_payload(right_path)
        differences = _diff(left_payload, right_payload)
        left_lines = left_path.read_text(encoding="utf-8").splitlines()
        right_lines = right_path.read_text(encoding="utf-8").splitlines()
        report.update(
            {
                "left": {**report["left"], **left_text, "normalized_sha256": _canonical_sha256(left_payload)},
                "right": {**report["right"], **right_text, "normalized_sha256": _canonical_sha256(right_payload)},
                "normalized_difference_count": len(differences),
                "normalized_differences": differences,
                "semantic_payload_equal": not differences,
                "semantic_payload_equal_except_documentation": all(
                    item["path"] in {"root_layer.documentation", "stage_metadata.documentation"}
                    for item in differences
                ),
                "prim_order_equal": left_payload["prim_order"] == right_payload["prim_order"],
                "text_unified_diff": list(
                    difflib.unified_diff(left_lines, right_lines, fromfile="phase6dy", tofile="phase6dz", lineterm="")
                ),
                "category_gates": {
                    "geometry_equal": not any("points" in item["path"] or "faceVertex" in item["path"] for item in differences),
                    "schemas_equal": not any("applied_schemas" in item["path"] for item in differences),
                    "transforms_equal": not any("xformOp" in item["path"] for item in differences),
                    "relationships_equal": not any("relationships" in item["path"] for item in differences),
                    "prim_order_equal": left_payload["prim_order"] == right_payload["prim_order"],
                    "stage_metadata_equal_except_documentation": all(
                        item["path"] in {"root_layer.documentation", "stage_metadata.documentation"}
                        for item in differences
                    ),
                },
            }
        )
        report["status"] = "ok"
        exit_code = 0
    except Exception as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        app.post_uncancellable_quit(exit_code)


_main()
