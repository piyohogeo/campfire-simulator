# Phase 6GC payload-native source contract

Status before runtime: frozen contract. Phase 6GB remains a pre-readback safe
stop and is not reclassified. Phase 6GC changes only the source-array evidence
boundary; geometry, Point policy, readback frames, Flow/RTX settings, physical
thresholds, lifecycle order, and resource ceilings are byte-for-byte equal to
the Phase 6GB contract sections covered by the focused regression.

## Primary semantics

The expected source is constructed from the exact contiguous `float32` arrays
immediately before USD authoring. The live Point Emitter is read back as
contiguous `float32`. Both expected and observed sums use:

`sum(float64(float32(source_i)))`, in payload order, with a float64 accumulator.

The decimal expression `0.8 * point_count` is telemetry only. Qualification
requires exact point count, revision, payload identity, per-array shape, dtype,
stride, finite state and SHA-256, plus a canonical hash covering ordered Point
positions and all three source arrays. With the same accumulator order, the sum
budget is zero because the payload hashes must already match.

If an integration boundary explicitly reports a different addition order, it
may use a precomputed bound of `element_count * maximum float32 ULP`. This path
is permitted only when every array and the canonical payload hash match. The
bound is computed before runtime and never fitted to the Phase 6GB difference.

For S93 fuel, the payload-native expectation is
`1075.2000160217285`; `1075.2` remains the decimal reference. Their difference
is the accumulated representation of `float32(0.8)`, not missing supply.

## Pre-Kit fixtures

Sixteen cases exercise the same corrected geometry planner, float32 payload,
compressed NPZ round trip and contract validator. Valid S93, valid S100, and a
correct quantized value differing from the decimal reference must pass. Missing,
duplicate, changed, reordered, wrong-dtype, wrong-shape, NaN, positive/negative
infinity, stale-revision and wrong-identity payloads must fail. An identical
payload with an alternate accumulator order passes inside the precomputed ULP
budget and fails above it. The report is bounded machine-readable JSON; Kit is
not launched.

Only after this suite, the Phase 6GB geometry-binding fixture, app-ready import,
progress-aware CDB and offline geometry gates pass may a fresh channel preflight
and nine-process population begin. Any later failure remains fail-closed under
the frozen Phase 6FZ safety contract.
