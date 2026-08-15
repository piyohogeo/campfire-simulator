"""Run the frozen Phase 6HK boundary implementation under Phase 6HM identity."""

from __future__ import annotations

import hashlib
from pathlib import Path


SOURCE = Path(__file__).with_name("probe_phase6hk_flow_proxy_boundary.py")
EXPECTED_SHA256 = "7CDBFD7DBC5076095BA0BF352EFD96FFDD56CB1678AF6F5E2B7AD8835D640EC1"
source_bytes = SOURCE.read_bytes()
if hashlib.sha256(source_bytes).hexdigest().upper() != EXPECTED_SHA256:
    raise RuntimeError("Frozen Phase 6HK boundary probe hash mismatch")
source = source_bytes.decode("utf-8")
source = source.replace("phase6hk", "phase6hm").replace("Phase 6HK", "Phase 6HM")
exec(compile(source, str(Path(__file__).resolve()), "exec"), globals(), globals())
