# Phase 6HF velocity ROI-sampling lifecycle contract

Phase 6HE remains an immutable safe stop. Its artifacts, classification,
contract, thresholds, and samples are not changed, reclassified, or reused.
Phase 6HF uses fresh stages and processes under contract SHA-256
`DCB70741DAB53BB673CD5CE076C0C295DB359EFCD6E94DDE6C7AB408481FD2F8`, recorded
beside the machine-readable JSON before runtime.

## Read-only boundary audit

Phase 6HE V5 completed the non-temperature schema prefix for slots 1--5 and
the second spatial-analysis velocity path through `buffer_to_volume`,
`SaveVolumeParameters`, `save_volume`, durability confirmation,
`nanovdb.io.readGrid`, `vec3fGrid`, `voxelSize`, `activeVoxelCount`, and exact
temporary deletion. V6 added only `_sample_grid()` in fixed dictionary order:
`scene`, `inter_log_gap`, `flame_rise`, `opposite_above`, and `side_control`.
Each bounded result remained in the returned `rois` dictionary until the
unchanged caller release boundary. After sampling, the exact temporary file
was deleted; the local result, velocity alias, grid row, all list slots, and
the handle list were released in the existing order. V6 operation evidence,
all five samples, deletion, weak residual zero, stage close,
`shutdown_complete`, resource gates, and exact cleanup passed. Natural OS exit
alone timed out.

## Frozen one-shot ladder

Every fresh process rebuilds the complete V5 prefix. It retains sampling
results identically while adding one fixed ROI call at a time.

| Mode | Cumulative ROI calls | Sole addition |
|---|---|---|
| R0 | none | V5 control |
| R1 | scene | scene |
| R2 | scene, inter_log_gap | inter_log_gap |
| R3 | scene, inter_log_gap, flame_rise | flame_rise |
| R4 | scene, inter_log_gap, flame_rise, opposite_above | opposite_above |
| R5 | scene, inter_log_gap, flame_rise, opposite_above, side_control | side_control |

The actual `_save_and_sample()` implementation owns the calls, arguments,
result dictionary, markers, temporary format, and release boundary. Its new
diagnostic ROI limit defaults to `None`, so existing callers and Phase 6HE's
five-call path are unchanged. The offline fixture must prove exact ROI order,
R5 equivalence to Phase 6HE V6, unchanged result retention/release, shared
counter completeness, and forbidden temperature/collector/profile calls.

Each condition runs once. Canonical operation, reference release, weak
residual zero, stage close, durable `shutdown_complete`, natural exit code 0,
resource gates, exact cleanup, and residual zero are all required before the
next condition. There is no retry or replacement. The first non-normal result
stops the ladder. If all six are normal, the only allowed conclusion is that
the Phase 6HE V6 lifecycle timeout did not reproduce in this short population.

## Safety and scope

Kit/tree limits remain 16/17 GiB; runner/diagnostic limits remain 512 MiB;
physical and commit floors remain 8 GiB; stage close remains 180 seconds; only
one Kit process may run. The release-after-close lifecycle, progress-aware
stack-first CDB, Phase 6FU cleanup, Phase 6FW PID-reuse policy, and exact
attempt-local temporary allowlist remain unchanged.

Temperature processing, spatial collectors, velocity profile, other-channel
extensions, formal comparison, Point-policy adoption, production/default/V3/P4
changes, video/latest-demo changes, and long or large repetition are forbidden.
