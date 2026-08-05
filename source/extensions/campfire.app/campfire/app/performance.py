"""Small, deterministic helpers for performance evidence."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence


def summarize_timing_ms(
    values_ms: Sequence[float], warmup_samples: int = 0
) -> dict[str, int | float]:
    """Summarize non-negative millisecond samples after a fixed warmup prefix."""

    if warmup_samples < 0 or warmup_samples >= len(values_ms):
        raise ValueError("warmup_samples must leave at least one measured sample")
    measured = [float(value) for value in values_ms[warmup_samples:]]
    if any(not math.isfinite(value) or value < 0.0 for value in measured):
        raise ValueError("timing samples must be finite and non-negative")
    ordered = sorted(measured)
    p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return {
        "sample_count": len(measured),
        "warmup_samples_excluded": warmup_samples,
        "total_ms": round(sum(measured), 4),
        "mean_ms": round(statistics.fmean(measured), 4),
        "p95_ms": round(ordered[p95_index], 4),
        "max_ms": round(ordered[-1], 4),
    }
