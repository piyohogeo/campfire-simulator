# Phase 6ET four-log Flow memory calibration safe stop

## Scope and frozen history

Phase 6ET is a production-neutral calibration of the corrected four-log diagnostic scene. Phase 6ES remains an immutable resource safe stop: its two 14 GiB guard failures, artifacts, classification, and unfinished 93.33%/100% comparison are not overwritten or reclassified. Production code and defaults, Point schema/order/length/revision, wood authority, Flow settings, CollisionProxy geometry, and log placement are unchanged.

The new contract is `campfire.phase6et.four-log-memory-calibration-contract.v1`, SHA-256 `4B14168B37442050FCA9D23B1ECAAC6DA9F57C666FB3D44FBCEE5F39C26830F6`. It predeclares seven conditions and three counterbalanced orders (21 independent processes). The Kit/runner/diagnostic/tree limits remain 14 GiB / 512 MiB / 512 MiB / 16 GiB, with 8 GiB physical-memory and commit-headroom floors. Formal conditions are never retried automatically.

## Read-only baseline

Bytes and GiB use different bases and are reported together:

- Phase 6ES root 1 `filtered_933_on`: `15,100,735,488 bytes` = `14.063656 GiB`.
- Phase 6ES root 2 with scalar spatial collection limited to one representative blocker: `15,722,414,080 bytes` = `14.642639 GiB`.
- Phase 6ER did not reach a four-log runtime population. Its four-log evidence is offline geometry, so it does not provide a comparable Kit peak. Its completed lower/upper controls remain read-only context.

At Phase 6ES frame 90, the available public readback buffers represented `294,940,224 bytes` (`0.274685 GiB`): temperature, fuel, burn, and smoke were each `65,716,224 bytes`, and velocity was `32,075,328 bytes`. The JSON report was only tens of KiB. This is too small to explain a multi-GiB Kit change by JSON or NumPy retention alone.

## Frozen A–G isolation matrix

All conditions use the corrected four-log placement, `allow_self_center`, offset `-0.0125 m`, 1,344/1,440 active Points, the same timeline and frames 30/60/90/120/150/180/200.

- A: no readback and no spatial/transport collector.
- B: public readback, process only fuel, no spatial/transport collector.
- C: velocity and one representative Collider spatial collector.
- D: temperature and one representative Collider.
- E: smoke and one representative Collider.
- F: velocity + temperature + smoke, no directional postprocessing.
- G: F plus the existing directional transport analysis after Kit exits.

`get_latest_nanovdb_readback()` returns the public channel tuple as one acquisition. Therefore B is the smallest existing public readback path but is not a true per-channel device readback: the selected fuel array size is a lower bound on the resources acquired by the call.

The resource trace samples every 0.25 seconds. It records de-duplicated PID + creation-time identities, Kit/runner/diagnostic/child/tree Private Bytes and working set, physical and commit headroom, CPU, lifecycle/resource markers, and isolated `nvidia-smi` dedicated-memory/utilization/power/temperature CSV. The bounded public telemetry path does not expose GPU shared memory; it is recorded unavailable and is not estimated.

## Observed result

The first artifact root was rejected before Kit launch because an empty PowerShell collector-index argument was bound as a missing value. It is an invalid harness preflight, not a Flow sample. The fix is isolated in commit `4a495a7`; root 2 starts from a fresh warm-up and formal process 1.

Warm-up completed with normal OS exit and Kit peak `12,291,465,216 bytes` (`11.447319 GiB`).

### A — Flow only

A completed with normal OS exit, no readback, no spatial NPZ, fatal/dump/upload/device-lost/TDR/residual zero. Kit peak was `14,536,630,272 bytes` (`13.538292 GiB`), tree peak `14,700,179,456 bytes` (`13.690609 GiB`). Active blocks at the sample frames were `505, 688, 894, 1118, 1314, 1329, 1251`.

The memory series did not grow monotonically at every frame: sampled Kit values rose and fell, with a maximum around the frame-120 `sample_persisted` interval. However, the predeclared 20-second tail window covered the still-growing active simulation interval and had a positive slope of about `370.6 MB/s`, so it did not satisfy the frozen plateau classifier. This is a bounded high-water observation, not evidence of an unbounded Python leak.

### B — first public readback

B reached samples 30/60/90, then the unchanged Kit guard stopped it. Kit peak was `15,323,729,920 bytes` (`14.271336 GiB`), tree peak `15,487,098,880 bytes` (`14.423485 GiB`). Cleanup left no Kit, CDB, or `nvidia-smi` process. The active marker was frame-90 `sample_persisted` while the timeline was still playing.

The selected fuel arrays were `19,277,312`, `25,553,152`, and `32,858,112 bytes`; raw JSON at the last completed marker was `9,511 bytes`, and spatial collection was disabled, so NPZ bytes were zero. At frame 30 the nearest resource samples show about `140,185,600 bytes` added between `readback_started` and `readback_complete`. At frame 90, about `931,454,976 bytes` appeared between the nearest `channel_started` and `channel_complete` resource samples, followed by the final guard peak. Sampling resolution and continued Flow execution prevent attributing those deltas to a single internal allocator.

## Classification

Observed facts:

- Four-log Flow without readback already reaches `13.538 GiB`, close to the unchanged 14 GiB limit.
- The first public readback path is sufficient to cross the limit by frame 90.
- B has no spatial collector, no NPZ output, no directional transport postprocessing, and no temperature/smoke processing.
- The small selected array and JSON sizes do not match the approximately 0.79 GiB A/B peak difference or the larger within-frame resource movement.
- A is not strictly monotonic, but its formal measurement window did not establish the frozen plateau gate.

Strong inference:

- Directional aggregation, temperature/smoke readback processing, Collider multiplicity in the spatial collector, and JSON expansion are not the trigger for this safe stop because they were not reached.
- The dominant boundary is a high four-log Flow/active-block baseline plus the first public NanoVDB readback acquisition/processing boundary.

Unconfirmed:

- The public call returns all channel handles, so B cannot separate device/Flow readback-resource lifetime from fuel conversion/sampling.
- No public evidence identifies an internal Flow allocator, staging allocation, or resource cache as the precise owner of the unexplained bytes.
- GPU shared memory and a per-Kit GPU allocation are unavailable from the bounded telemetry path.

## Decision and next restart condition

Phase 6ET is a safe stop: one of 21 formal processes completed, the second exceeded the unchanged guard, and C–G were not started. The 14 GiB limit is not raised. The 93.33% vs 100% comparison, offset-zero runtime, threshold freezing, and video are not started. The latest-demo pointer remains unchanged because this is an internal diagnostic with no qualified visual change.

The next independently approved calibration should split `get_latest_nanovdb_readback()` acquisition from `_save_and_sample()` conversion/persistence using acquire-and-discard and explicitly bounded lifetime fixtures. It must use a new schema/root and keep Phase 6ET immutable. A higher Kit limit is not justified until at least three normal runs demonstrate a stable plateau and sufficient system headroom.

Post-stop regression passed the Release build in 8.25 seconds, Phase 0 RTX, and Phase 3. Phase 3 retained dry/wet mass-balance error 0, authority hashes `0dec57f3...e84be10` / `148585f8...d2b20c9`, active blocks final/peak `304/332`, and peak fuel 1.0. Phase 6EA–6ET focused contracts passed `169/169`; the standard suite passed all eight processes and `78/78` tests in 348.5 seconds. Production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.

No in-app Browser instance was available for rendered-page inspection. The fallback static verification passed 396 local references, 200 JSON files, 166 SVG files, two ZIP files, UTF-8 decoding, and duplicate-ID checks; the existing latest-demo reference was left unchanged.
