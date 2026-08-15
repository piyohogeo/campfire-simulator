# Phase 6HF velocity ROI-sampling lifecycle safe stop

Phase 6HE remains frozen at commit `c410e02`; no Phase 6HE artifact,
classification, contract, threshold, document, or runtime sample was changed,
reclassified, or reused. Phase 6HF used the new root
`artifacts/phase6hf-velocity-roi-lifecycle-20260815` under contract SHA-256
`DCB70741DAB53BB673CD5CE076C0C295DB359EFCD6E94DDE6C7AB408481FD2F8`.

## Read-only audit

Phase 6HE V5 had already completed the non-temperature schema prefix for slots
1--5, the second velocity `buffer_to_volume`, `SaveVolumeParameters`, temporary
save and durability confirmation, `nanovdb.io.readGrid`, `vec3fGrid`, voxel
size and active-voxel count, allowlisted temporary deletion, and caller-owned
ordered release. V6 added five calls to the existing `_sample_grid()` in this
fixed order: `scene`, `inter_log_gap`, `flame_rise`, `opposite_above`, and
`side_control`. Each bounded result remained in `result["rois"]` until the
unchanged operation-report and caller-release boundary. V6 completed all five
calls, temporary deletion, weak-residual-zero release, stage close, cleanup,
and durable `shutdown_complete`; natural OS exit alone timed out.

Phase 6HF therefore reused the V5 implementation as a fresh-process prefix and
selected only a prefix of that exact ROI order. It did not change the ROI
definitions, grid, thresholds, result retention, release order, stage, Flow,
Point payload, timeline, or production code.

## One-shot ladder result

The no-Kit contract and producer-to-consumer fixture passed 62/62. No retry or
replacement was allowed.

| Mode | Sole cumulative addition | Result | Stage close (s) | Kit/tree peak (bytes) |
|---|---|---|---:|---:|
| R0 | fresh Phase 6HE V5; zero ROI calls | normal exit | 3.6565188 | 15,199,580,160 / 15,363,514,368 |
| R1 | `scene` only; one ROI call | post-shutdown OS-exit failure | 3.0257568 | 15,119,458,304 / 15,271,591,936 |

R1's `scene` call completed. The bounded result reported 70,262 voxels, 47,820
nonzero voxels, mean 0.43757287385438787, p95 2.2049771903279027, maximum
13.515141367114726, and sum 30,744.745262757002. The canonical operation report
passed with one velocity ROI-sampling call. References were released, weak
residual was zero, the allowlisted temporary file was absent after cleanup,
stage close completed, and `shutdown_complete` was durable. Kit did not exit
naturally. Exact cleanup passed with process and NanoVDB residuals both zero.
R2--R5 were not launched after the first non-normal condition.

## Safety and interpretation

The maximum Kit/tree peaks across the two launches were 15,199,580,160 and
15,363,514,368 bytes, leaving 1,980,289,024 and 2,890,096,640 bytes below the
16/17 GiB ceilings. Runner and diagnostic peaks were 132,194,304 and
121,896,960 bytes. Minimum available physical memory and estimated commit
headroom were 83,178,196,992 and 102,828,994,560 bytes. There was no fatal,
dump, automatic upload, resource breach, retry, replacement, unknown temporary
file, collector, profile, temperature operation, or formal comparison.

R0 is the last fully qualified condition. R1 is the first non-normal condition,
and its sole added operation is one `scene` `_sample_grid()` call. This is the
smallest candidate association observed by this one-shot ladder, not proof
that sampling is the root cause. The unchanged result-retention lifetime and a
probabilistic or state-dependent native lifecycle event remain unseparated.
Phase 6HE is not retrospectively upgraded.

The next technically useful small experiment, if separately approved, would
hold the sampling API and inputs fixed while isolating the bounded result's
retention/release lifetime. Broad repetition, temperature, collector, profile,
formal comparison, production integration, and demo changes remain blocked.

## Verification

The implementation commit is `53510a9`. Release build passed in 8.12 seconds.
The focused Phase 6HF fixture passed 62/62, the frozen Phase 6HE and Phase 6HD
fixtures passed 63/63 and 54/54, Python compilation passed, and the contract
digest matched. The standard suite passed all 8 processes and 78 tests in 343
seconds. Static devlog validation passed with 531 references and 312 IDs.
Production app SHA-256 remains
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A` and
latest-demo manifest SHA-256 remains
`1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285`.
Phase 0 and Phase 3 were not rerun because this diagnostic-only change did not
alter production, USD generation, rendering startup, Flow physics, Point
payload, or defaults. No new video was required.
