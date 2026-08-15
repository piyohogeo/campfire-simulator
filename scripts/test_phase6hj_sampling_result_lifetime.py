"""Phase 6HJ no-Kit wrapper: isolate the frozen Phase 6HH fixture temp root."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

import test_phase6hh_sampling_result_lifetime as frozen_fixture


def main() -> int:
    original = frozen_fixture.tempfile.gettempdir
    capture = io.StringIO()
    with tempfile.TemporaryDirectory(prefix="phase6hj-fixture-root-") as root:
        frozen_fixture.tempfile.gettempdir = lambda: str(Path(root).resolve())
        try:
            with contextlib.redirect_stdout(capture):
                code = frozen_fixture.main()
        finally:
            frozen_fixture.tempfile.gettempdir = original
    nested = json.loads(capture.getvalue())
    output = {
        "schema": "campfire.phase6hj.producer-consumer-fixture.v1",
        "pass": code == 0 and nested.get("pass") is True,
        "count": nested.get("count"),
        "phase6hh_fixture": nested,
        "fix": "fixture command path allocated under a unique TemporaryDirectory",
        "kit_launched": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
