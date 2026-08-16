"""Bounded CLI around the qualified Phase 6HU atomic JSON writer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase6ik_parent_lifecycle_boundary import read_bounded_json, write_runner_evidence
from phase6hu_atomic_report import atomic_write_json


def write_from_source(source: Path, destination: Path) -> dict:
    payload = read_bounded_json(source)
    return write_runner_evidence(destination, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    result = write_from_source(args.source, args.destination)
    atomic_write_json(args.result, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
