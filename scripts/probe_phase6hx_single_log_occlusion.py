"""Kit --exec wrapper for the exact Phase 6HX operation source."""

from pathlib import Path

from phase6hx_probe_source import build_probe_source


_source = build_probe_source(Path(__file__).absolute().parent / "probe_phase6hw_single_log_occlusion.py")
exec(compile(_source, __file__, "exec"), globals(), globals())
