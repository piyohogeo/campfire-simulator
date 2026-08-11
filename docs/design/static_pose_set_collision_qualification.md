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
