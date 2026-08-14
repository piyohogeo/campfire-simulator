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

## Runtime result

The frozen contract and all pre-Kit gates passed: source cases 16/16, geometry
binding 4/4, app-ready import 3/3, CDB progress 7/7, and offline geometry. The
fresh S93 preflight formed representative Flow (269/688 active blocks at frames
1/60 and 1,329 at frame 180). Expected and live canonical payload SHA-256 were
both `DF5AF9FA764B4B2D74FCD67DEF30ADE4C24DC267E351FA017746E89907B2E920`;
fuel, temperature and smoke differences were exactly zero.

The one public readback returned seven handles while the frozen public-channel
order contains six entries. Marker `p3_readback_call_after` durably recorded
the count, then the probe failed closed before handle indexing, conversion,
NPZ, spatial metrics or directional flux. This is a new public-readback schema
boundary, not a source-sum failure, and is not fixed or retried in Phase 6GC.

Formal S93/S100/OFF, replacement and video remained zero. Stage close completed
in 15.6564391 seconds and `shutdown_complete` was durable; the deliberate probe
error yielded OS exit 1. Kit/tree peaks were 14,817,234,944/14,980,284,416 bytes.
CDB/fatal/dump/upload/residual were zero and exact cleanup completed. S100 is
still unevaluated and is not an adoption candidate.

Regression passed Release build, Phase 0 RTX, Phase 3 with zero mass-balance
error and wood-owned Flow input (active blocks final/peak 277/381), focused
Phase 6F 212/212, focused Phase 6G 16/16, the standard eight-process 78/78
suite, and static devlog validation. Production and latest-demo hashes remained
unchanged; final Kit/CDB/nvidia-smi/nvngx-update residuals were zero.
