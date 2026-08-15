"""Run the frozen one-proxy operation under the Phase 6HS identity."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).absolute().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phase6hp_junction_module_path import collect_module_path_evidence, validate_module_path_evidence
from phase6hs_probe_source import build_probe_source

SOURCE = Path(__file__).with_name("probe_phase6hk_flow_proxy_boundary.py")
source = build_probe_source(SOURCE)
exec(compile(source, str(Path(__file__).absolute()), "exec"), globals(), globals())
