"""Run the frozen one-proxy boundary under the Phase 6HP identity."""

from __future__ import annotations

import hashlib
from pathlib import Path


SOURCE = Path(__file__).with_name("probe_phase6hk_flow_proxy_boundary.py")
EXPECTED_SHA256 = "7CDBFD7DBC5076095BA0BF352EFD96FFDD56CB1678AF6F5E2B7AD8835D640EC1"
source_bytes = SOURCE.read_bytes()
if hashlib.sha256(source_bytes).hexdigest().upper() != EXPECTED_SHA256:
    raise RuntimeError("Frozen Phase 6HK boundary probe hash mismatch")
source = source_bytes.decode("utf-8").replace("phase6hk", "phase6hp").replace("Phase 6HK", "Phase 6HP")
exec(compile(source, str(Path(__file__).absolute()), "exec"), globals(), globals())
