# Phase 6HE velocity sub-boundary lifecycle safe stop

Phase 6HD remains frozen at commit `cefa061`; no Phase 6HD artifact,
classification, document, or sample was changed or reused. Phase 6HE used the
new root `artifacts/phase6he-velocity-lifecycle-20260815` under contract
SHA-256 `C611A4805D91C544006BAB6E1232EC973444142659CCA6A270DCE37D07D051B1`.

## Audited path and ladder result

The actual Phase 6HD D helper order is `buffer_to_volume`,
`SaveVolumeParameters`, `save_volume`, durability confirmation,
`nanovdb.io.readGrid`, `vec3fGrid`, `voxelSize` and `activeVoxelCount`, five
existing ROI `_sample_grid()` calls in `scene`, `inter_log_gap`, `flame_rise`,
`opposite_above`, `side_control` order, the scene `_profile_grid()` call,
allowlisted temporary deletion, and caller-owned ordered release. Condition C
had already performed schema conversion, metadata, temporary save, and typed
read once for velocity, so this ladder isolates the second spatial-analysis
pass.

| Mode | Sole cumulative addition | Result | Stage close (s) | Kit/tree peak (bytes) |
|---|---|---|---:|---:|
| V0 | fresh Phase 6HD C prefix | normal exit | 2.7351259 | 15,088,603,136 / 15,252,156,416 |
| V1 | velocity alias and bounded metadata | normal exit | 2.2127584 | 15,145,943,040 / 15,309,406,208 |
| V2 | second conversion and immediate release | normal exit | 2.0327255 | 14,997,135,360 / 15,149,527,040 |
| V3 | parameters, save, durability, deletion | normal exit | 3.2925337 | 15,206,297,600 / 15,369,940,992 |
| V4 | `readGrid` and handle release | normal exit | 2.1345378 | 15,169,912,832 / 15,324,827,648 |
| V5 | vector grid, voxel size, active count | normal exit | 8.2008969 | 15,173,799,936 / 15,325,982,720 |
| V6 | five ROI samples, no profile | lifecycle safe stop | 4.5438597 | 15,223,119,872 / 15,386,820,608 |

V6's canonical operation report passed. Its five ROI calls and temporary-file
deletion completed, references were released, weak-reference residual was zero,
stage close completed, and `shutdown_complete` was durable. The natural OS exit
alone timed out. Exact cleanup succeeded with process and NanoVDB residuals
both zero. Operation success is therefore not mixed with lifecycle failure.
V7 was not launched after the first non-normal condition; V8 was not scheduled
because V7 would already reach the actual helper's final applicable profile
branch.

## Counters and safety

The ten velocity counters progressed exactly as frozen: V0 all zero; V1 alias
1; V2 conversion 1; V3 save/durability/deletion 1; V4 file-read 1; V5 vector
access/basic metadata 1; V6 ROI sampling 5. `velocity_profile`,
`velocity_collector`, and every temperature counter remained zero. The 25-key
producer-to-consumer fixture passed 63/63 and the frozen Phase 6HD, 6HC, and
6HB fixtures passed 54/54, 20/20, and 28/28 before runtime.

Maximum Kit/tree peaks were 15,223,119,872 / 15,386,820,608 bytes, leaving
1,956,749,312 / 2,866,790,400 bytes below the 16/17 GiB ceilings. Minimum
available physical memory and commit headroom were 79,682,027,520 and
99,321,352,192 bytes. Runner and diagnostic peaks stayed below their 512 MiB
limits. No unknown temporary file, resource failure, fatal, retry, replacement,
collector use, temperature native operation, or formal comparison occurred.

## Decision and verification

V5 is the last fully qualified condition. V6 is the first non-normal condition,
and the exact added element is the five-call existing ROI sampling stage. This
single observation makes ROI sampling the next minimum candidate boundary; it
does not prove a root cause or justify a fix or automatic repetition.
Temperature and collectors were not exercised and are not implicated.

Post-stop verification passed the Release build in 7.62 seconds, Phase 6HE
fixture 63/63, frozen Phase 6HD/6HC/6HB fixtures 54/54, 20/20, and 28/28,
Python compilation, and static devlog validation with 530 references and 311
IDs. Production
app SHA-256 remains
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A` and
latest-demo manifest SHA-256 remains
`1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285`.
No new video was required for this internal lifecycle diagnosis.
