# Phase 6HH sampling-result lifetime contract

Phase 6HF remains frozen at commit `c27267f`. Its artifacts, contract,
classification, thresholds, and samples are neither changed nor reused as a
new measurement. The Phase 6HH identifier avoids reusing the historical Phase
6GH identifier. A fresh artifact root and a frozen machine contract are
required before runtime.
The frozen contract SHA-256 is
`9BDA7BCCC7049DBAC873DD0C31C307E488648820EB228B7E04D3787AD4020504`.

## Read-only audit

The existing `_sample_grid()` returns a `builtins.dict`. Its leaves are only
`bool`, `int`, `float`, or a bounded reason string; it contains no NumPy view,
NanoVDB/native wrapper, grid, volume, or readback handle. A built-in dict does
not support weak references. Phase 6HF stored that exact dict at
`velocity_result["rois"]["scene"]`, then assigned the same velocity-result
object to the global bounded operation report. Clearing the caller's local
`velocity_result` did not remove the report-owned reference. Handle weak
residual zero therefore did not test the sample-result dict's lifetime.

The runtime preflight writes this audit to bounded JSON after checking the
actual Phase 6HF source and frozen R1 operation report. It records only type,
keys, scalar types and values, ownership path, release order, and the already
frozen functional/lifecycle axes. No field body, dense voxel data, or copy is
created.

## One-variable ladder

Every condition rebuilds the Phase 6HE V5 prefix with a fresh process, stage,
and attempt directory.

| Mode | Sampling | Original sample-result lifetime |
|---|---|---|
| L0 | none | no result |
| L1 | one `scene` call | scalar copy is written to the report; original dict is immediately cleared and not put in `result["rois"]` |
| L2 | one identical `scene` call | original dict remains in `result["rois"]` and the operation report through the Phase 6HF release boundary |

L1 and L2 use the same `_sample_grid()`, grid, ROI, thresholds, native call
order, sampling calculations, and scalar report shape. The helper's default
retention remains the frozen legacy behavior; only Phase 6HH passes the
explicit diagnostic retention mode. Neither condition invokes `gc.collect()`.
The original result type, identity, container structure, scalar leaf types,
weak-reference support, store count, and local-clear boundary are persisted as
bounded markers. Both reports contain the same bounded scalar copy, preventing
artifact-size differences from becoming the comparison variable.

Each condition runs once without retry or replacement. Canonical operation,
reference release, weak residual zero, stage close, durable
`shutdown_complete`, natural exit code 0, resource gates, exact cleanup, and
residual zero are all required before continuing. L0 non-normal invalidates the
comparison. L1 non-normal shows that result retention alone is insufficient.
L1 normal followed by L2 non-normal strengthens a retention-lifetime
association without proving root cause. If L1 and L2 are normal, the timeout is
classified as not reproduced and parked without large repetition. The first
non-normal condition stops the ladder.

Kit/tree limits remain 16/17 GiB; runner/diagnostic limits remain 512 MiB;
physical and commit floors remain 8 GiB; stage close remains 180 seconds. The
release-after-close lifecycle, progress-aware stack-first CDB, Phase 6FU exact
cleanup, Phase 6FW PID-reuse policy, and attempt-local temporary allowlist are
unchanged.

Temperature, collectors, profile, formal S93/S100/OFF comparison, long
repetition, production/default/Point/V3/P4 changes, GPU heat feedback, and
video/latest-demo changes are prohibited.
