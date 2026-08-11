# Phase 6EG: representative static Mesh CollisionProxy poses

## Purpose and frozen contract

Phase 6EG was intended to extend the Phase 6EF judgment method from static Y40° to six predeclared representative poses while changing only pose. The exact authored 26-vertex, 36-face, 120-index closed Mesh remains the distance reference; the ideal Cylinder is secondary, and no public Flow 110.0.0 API exposes Flow's internal collision occupancy mask. The inherited velocity gates are deep/center ON maximum `<=1e-5 m/s`, paired OFF maximum `>=0.1 m/s`, and ON/OFF deep-maximum ratio `<=0.01`.

Before formal results were observed, `scripts/phase6eg_static_pose_set_contract.json` fixed P0 identity, P1 Y40°, P2 long-axis X17° roll, P3 Z33°, P4 local Y24° then world Z31°, and P5 axis `(1,1,1)` at 53°. It also fixed all final row-vector 4×4 matrices, three counterbalanced orders, four sample frames, and 36 independent processes. Matrix inversion in the sampler uses the authored final matrix rather than reconstructing Euler angles.

Offline OpenUSD preflight passed every pose. All rotations were orthonormal with determinant `+1`, preserved center `(0,0,1.035) m`, retained identical topology and local-geometry hash, stayed inside the qualified scene envelope, and predicted deep/center velocity-grid samples. Exact authored-Mesh clearance from the emitter sphere was 0.225000, 0.111532, 0.230156, 0.225000, 0.183070, and 0.201088 m for P0–P5 respectively; every pose exceeded two 0.05 m velocity voxels.

## Formal safe stop

The formal matrix stopped after six of 36 processes. P0, P1, and P2 ON/OFF each reached functional pass, normal OS exit, active Flow blocks, fuel 0.8, and zero fatal/dump/upload/residual evidence. Their single-run worst deep ON values were `0`, `8.352523e-6`, and `7.300535e-6 m/s`; paired OFF minima were all `7.767152 m/s`, so the completed diagnostic pairs satisfy the inherited numeric checks. One run cannot satisfy the predeclared three-run qualification.

P3 Z33° collision ON did not reach Flow sampling. Its last durable marker was `opening_prebuilt_stage`, `active_blocks_final` was absent, and no runner evidence was completed. The existing Phase 6EA guarded PowerShell helper crossed its 512 MiB Private Bytes ceiling at 552,259,584 bytes. The guard terminated only that process tree, left no Kit/CDB process, and the matrix did not retry P3 or start later conditions. No crash dump or automatic upload was observed. This is a `resource_guard_abort` with incomplete functional evidence and unknown lifecycle—not evidence that Z33° collision failed.

The original root-level `safe_stop.json` recorded the last completed condition (`P2_roll_x17_off`) instead of the failing condition. The read-only evidence unambiguously identifies the only incomplete case as `P3_z33_on`; the checked-in summary preserves both facts, and the runner now records the active failing condition for future roots. This bookkeeping correction does not retry or reinterpret the failed run.

The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`. Phase 6EG changes no production module, app setting, Flow default, V3, Resident state, authority, emitter schema, collider geometry, or resolution.

Post-stop regression passed: Release build 6.69 seconds, Phase 0 RTX exit 0, and Phase 3 dry/wet mass-balance error 0 with unchanged authority hashes `0dec57f3...e84be10` / `148585f8...d2b20c9`, Flow active blocks final/peak 265/316, and peak fuel 1.0. The focused Phase 6DY–6EG and Phase 6EA/6EB/6ED safety contracts passed 88/88. The standard suite passed all 8 processes and 78/78 tests in 311.9 seconds (313.4 seconds wall time; collapse coverage 183.2 seconds).

## Result and restart boundary

Phase 6EG is not qualified. P0–P2 remain diagnostic-only one-run observations; P3–P5 are unevaluated. No formal qualification SVG or NPZ archive is produced because the numeric/lifecycle population is incomplete. The latest demo remains unchanged because this is an internal diagnostic with no qualified screen-visible change.

Before resuming, classify why the existing guarded helper exceeded 512 MiB during P3 stage-open. Do not automatically repeat the same P3 condition or raise the Phase 6EA memory ceiling merely to obtain a result. A future restart must use a new artifact root and preserve the frozen pose/threshold contract. Even a later pass would cover only Flow 110.0.0, the current fixed resolution, this exact Mesh, and P0–P5 static poses—not all SO(3), dynamic transform, RenderSurface, PhysX sharing, production layout, or 20-log performance.

## Phase 6EH resource diagnosis and second safe stop

The historical 512 MiB guard was not a Kit or process-tree budget. It sampled only the direct runner PowerShell PID. The original P3 artifact contains no per-PID history, but its timestamps show that the 552,259,584-byte stop occurred after the 330-second Kit hang entered lightweight shutdown diagnosis; the spatial collector had never started. The completed P0–P2 manifests instead reported Kit RSS around 6.62–6.74 GB and collector RSS deltas around 579–678 MB, which are different metrics.

A new low-volume JSONL guard now keys each process by PID plus creation time and records path, parent PID, role, Private Bytes, working set, peak working set, commit, unique-tree total, available physical memory, and estimated commit headroom. It never buffers Kit output or process histories in PowerShell. The runner ceiling remains 512 MiB. Calibration used separate 12 GiB Kit and 14 GiB tree observation ceilings; P0 and P3 stage-open-only runs reached `shutdown_complete` with runner peaks 95.5/96.0 MB, Kit Private peaks 11.27/11.42 GB, and tree peaks 11.41/11.72 GB. P3 therefore did not show pose-specific unbounded memory or a repeatable stage-open failure.

The fresh frozen-contract root then completed all P0–P5 ON/OFF conditions in run 1. Run-2 P2 OFF completed Flow sampling and timeline stop, but hung before stage close. At the 330-second boundary, its lightweight diagnostic created the capture lock and invoked GPU inventory. The trace observed `nvidia-smi.exe` first; about one second later the runner rose from about 100 MB through 139, 318, 469, and 558 MB over 18 seconds while Kit remained bounded. CDB was not launched. This is confirmed as the trigger boundary; the internal Windows PowerShell/native-command allocation mechanism remains unconfirmed.

GPU inventory is therefore isolated in a short-lived helper with 15-second timeout, 128 MiB ceiling, direct stdout/stderr files, and `File.ReadLines` parsing. Its small fixture completed in 1.64 seconds with a 74.6 MB runner, 16.1 MB `nvidia-smi`, and 100.4 MB unique tree. Formal Kit and tree ceilings are separated at 14 and 16 GiB, derived from calibration plus the known collector increment and safety margin; the runner ceiling is unchanged.

The second formal root is still a safe stop: 12/36 normal-exit processes are diagnostic only, run-2 P2 OFF is rejected, and no condition is retried automatically. Phase 6EG remains unqualified. A future restart requires explicit approval, a new artifact root, and process 1 of the unchanged frozen order.

After all 36 Phase 6EG processes eventually qualify, the next pending integration-preparation Phase is PointEmitter–CollisionProxy coexistence. It will evaluate emitter center and influence radius against the actual Mesh, exclude emitters inside their own or another log's collider, sweep offsets of 0, 0.25, 0.5, 1.0, and 1.5 Flow cells, and compare fuel/temperature supply, active blocks, deep intrusion, overhead penetration, and visible flame lift. No part of that Phase is implemented here.

Post-diagnosis regression passed: Release build 6.95 seconds, Phase 0 RTX in 19.9 seconds, and Phase 3 in 25.9 seconds with dry/wet mass-balance error 0, unchanged authority hashes, active Flow blocks final/peak 299/328, and peak fuel 1.0. The focused Phase 6EC–6EH plus Phase 6EA/6EB/6ED safety contracts passed 81/81 in 20.160 seconds. The standard suite passed all eight processes and 78/78 tests in 311.9 seconds. The calibration/formal/isolation roots contain no fatal token, dump, or automatic-upload attempt; no Kit/CDB process remained, and the production app hash stayed unchanged.
