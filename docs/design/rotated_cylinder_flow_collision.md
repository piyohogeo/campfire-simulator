# Phase 6DZ rotated Cylinder Flow-collision qualification

## Scope

Phase 6DZ is the first requested step from the Phase 6DY qualified static Cylinder toward the real log arrangement. It is production-neutral. The only intended stage difference is a rigid transform on `/World/ColliderReferenceMesh`; local Mesh geometry, collision schemas, `physics:approximation=convexDecomposition`, Flow 110.0.0, and every production default remain unchanged. The previously crashed cylindrical `convexHull` condition is neither generated nor executable.

The planned conditions are an axis-aligned entry control, X 17°, Y 12°, Z 90° (the four-log orientation), Z 37° (the Phase 6DR `Log_00` diagnostic orientation), XYZ 17°/12°/37°, and a byte-identical exit control. Every rotation uses a single `xformOp:transform`, right-handed unit scale, and the qualified local Cylinder center as pivot. Each new condition is bracketed by controls.

The stage-open boundary directly invokes the existing Phase 6DW runner and probe. Phase 6DZ does not implement its own renderer readiness or viewport wait. Public Flow sampling extends the existing Phase 6DT path only with an inverse-world-transform local Cylinder ROI. The predeclared maximum-noise limits are `1e-6` for scalar channels and `1e-5 m/s` for velocity. Flow readback is allowed only after every stage-open process exits normally.

## Offline result

All seven prepared stages passed the offline isolation gates:

- local geometry SHA-256: `662163A79B8E77EFBDACF34775ADF3F8BB9967232B5F8534124DD30E2E676FF0` in every condition;
- topology: 26 vertices, 36 faces, 120 indices, unchanged local extent;
- `PhysicsCollisionAPI` and `PhysicsMeshCollisionAPI` unchanged;
- `physics:approximation=convexDecomposition` in every condition;
- start/end controls byte-identical;
- all transforms right-handed, unit-scale, and center-preserving;
- no cylindrical `convexHull` stage generated.

This qualifies preparation only. It does not qualify any rotated stage against Hydra or Flow.

## Runtime safe stop

The first, unchanged axis-aligned control was run through `run_phase6dw_gpu_renderer_case.ps1` with the normal cache and a 420-second ceiling. It reached pure OpenUSD open, USD-context connection, observed Hydra delegate, the first renderer update after cold RTX compilation, first viewport frame, timeline stop, stage close, renderer drain, and `shutdown_requested` plus Hydra extension shutdown log entries.

The Kit process nevertheless remained alive at 420.092 seconds and did not produce a normal OS exit. The runner classified the result as timeout. The exact isolated `kit.exe` path was verified and the remaining process was terminated. Fatal-token, dump, automatic-upload-attempt, device-lost, TDR, and stage-ID-error counts were zero. RTX selected the GeForce RTX 3090 / CUDA index 0. The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A` before and after.

This is an unchanged-axis-control lifecycle failure, not evidence that rotation or Flow occlusion failed. It differs from Phase 6DX: Phase 6DX stopped before stage construction, while Phase 6DZ reached complete renderer/stage teardown markers but not OS process exit.

## Decision

Phase 6DZ is a safe stop. No rotated runtime condition and no public Flow readback condition was started. Phases B through G are held. No production code, app composition, collider, wood authority, V3 path, emitter, checkpoint, rollback, serialization, or latest-demo pointer changed.

Restart requires the byte-identical axis-aligned Phase 6DY control to reach a normal OS exit through the calibrated Phase 6DW lifecycle. The same failed run must not be automatically repeated. The next investigation should classify why the control process remains alive after `shutdown_requested` despite completed stage close and renderer drain, before any rotation is attempted.

Machine-readable evidence is in `docs/devlog/assets/phase6/rotated_cylinder_safe_stop_report.json`; sensitive logs and run-local data remain under the Git-ignored `artifacts/phase6dz-rotated-cylinder-1/` directory.

## Regression

- Release build: passed in 6.86 seconds.
- Phase 6DY calibrated lifecycle contract: 6 / 6 passed.
- Phase 6DZ rotation/isolation contract: 5 / 5 passed.
- Focused Flow-scene collider test: 1 / 1 passed; seven filtered processes contained zero tests.
- Standard suite: eight processes, 78 / 78 tests passed in 293.4 seconds; collapse coverage completed in 171.6 seconds.
- Devlog static validation: 332 unique local references, missing 0, JSON errors 0, SVG errors 0, UTF-8 replacement characters 0.
- Phase 0 RTX was not run because production code/app composition did not change; the renderer diagnostic itself stopped safely on its unchanged control.
