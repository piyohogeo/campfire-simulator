"""Shared immutable Flow-export authoring boundary for Phase 6GM diagnostics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DESCRIPTOR_PATH = SCRIPT_DIR / "phase6gm_flow_export_state_descriptor.json"


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load_descriptor(path: Path = DESCRIPTOR_PATH) -> dict:
    descriptor = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = descriptor.get("attributes") or []
    names = [row.get("name") for row in rows]
    if len(rows) != len(set(names)) or any(not isinstance(name, str) for name in names):
        raise ValueError("Flow export descriptor contains missing or duplicate attribute names")
    if any(row.get("usd_type") != "bool" or type(row.get("value")) is not bool for row in rows):
        raise ValueError("Flow export descriptor requires explicit bool attributes")
    return descriptor


def descriptor_digest(descriptor: dict | None = None) -> str:
    return hashlib.sha256(_canonical(descriptor or load_descriptor())).hexdigest().upper()


def author(stage, descriptor: dict | None = None) -> dict:
    from pxr import Sdf

    descriptor = descriptor or load_descriptor()
    prim = stage.GetPrimAtPath(descriptor["prim"]["path"])
    if not prim or not prim.IsValid():
        raise RuntimeError("Flow export Prim is missing at the qualified path")
    if prim.GetTypeName() != descriptor["prim"]["type_name"]:
        raise RuntimeError(f"Flow export Prim type mismatch: {prim.GetTypeName()!r}")
    for row in descriptor["attributes"]:
        attribute = prim.GetAttribute(row["name"])
        if not attribute:
            attribute = prim.CreateAttribute(row["name"], Sdf.ValueTypeNames.Bool, custom=True)
        if attribute.GetTypeName() != Sdf.ValueTypeNames.Bool:
            raise RuntimeError(f"Flow export attribute type mismatch before authoring: {row['name']}")
        if not attribute.Set(row["value"]):
            raise RuntimeError(f"Flow export attribute authoring failed: {row['name']}")
    return validate(stage, descriptor)


def _root_property_names(stage, prim_path: str) -> set[str]:
    from pxr import Sdf

    root = stage.GetRootLayer()
    prim_spec = root.GetPrimAtPath(Sdf.Path(prim_path))
    if prim_spec is None:
        return set()
    return {prop.name for prop in prim_spec.properties}


def validate(stage, descriptor: dict | None = None) -> dict:
    from pxr import Sdf

    descriptor = descriptor or load_descriptor()
    prim_path = descriptor["prim"]["path"]
    prim = stage.GetPrimAtPath(prim_path)
    failures: list[str] = []
    observed = []
    root_properties = _root_property_names(stage, prim_path)
    if not prim or not prim.IsValid():
        failures.append("export_prim_missing")
        prim_type = None
    else:
        prim_type = prim.GetTypeName()
        if prim_type != descriptor["prim"]["type_name"]:
            failures.append("export_prim_type")
        for row in descriptor["attributes"]:
            attribute = prim.GetAttribute(row["name"])
            value = attribute.Get() if attribute else None
            type_name = str(attribute.GetTypeName()) if attribute else None
            root_authored = row["name"] in root_properties
            if not attribute:
                failures.append(f"missing:{row['name']}")
            elif attribute.GetTypeName() != Sdf.ValueTypeNames.Bool:
                failures.append(f"type:{row['name']}")
            elif type(value) is not bool or value != row["value"]:
                failures.append(f"value:{row['name']}")
            if not root_authored:
                failures.append(f"not_root_authored:{row['name']}")
            observed.append({"name": row["name"], "type": type_name, "value": value,
                             "root_authored": root_authored})
    return {
        "schema": "campfire.phase6gm.flow-export-state-validation.v1",
        "pass": not failures,
        "failures": failures,
        "descriptor_digest": descriptor_digest(descriptor),
        "prim_path": prim_path,
        "prim_type": prim_type,
        "attributes": observed,
    }

