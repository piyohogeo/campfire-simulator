# Phase 6DY calibrated Box-to-Cylinder stage-open ablation

## Purpose and boundary

Phase 6DY resumes the stage-open classification that Phase 6DX stopped before stage construction. It does not reuse the Phase 6DX readiness loop. The matrix calls the unchanged, qualified Phase 6DW runner (`run_phase6dw_gpu_renderer_case.ps1`) and probe (`probe_phase6dw_gpu_renderer_lifecycle.py`) directly for every stage. No lifecycle helper was extracted because the existing runner already accepts an arbitrary source stage.

The static contract test checks the actual Phase 6DW source and the Phase 6DY matrix. It requires pure OpenUSD open before USD-context connection, context connection before the first renderer update, the only `next_viewport_frame_async()` call after context connection, stage close before renderer drain, A-to-E order, fail-fast, and no automatic retry. The historical cylindrical `convexHull` condition was not run.

Production code, the production app, Flow 110.0.0, V3, Resident state, wood authority, emitters, colliders, and defaults were not changed. Each runtime condition used a separate process, crash-upload opt-out, dump preservation, fatal-token rejection, a 420-second ceiling, and production SHA-256 gates. Existing artifacts were not overwritten.

## Offline stage isolation

The Phase 6DT known-good Mesh stage (`2ED926A1...61862`) was reopened and exported through Kit/OpenUSD before any Hydra connection. A, C, and E are byte-identical controls (`C3860B27...D908`).

| Condition | Approximation | Vertices / faces / indices | Isolated change |
|---|---|---:|---|
| A Box | `convexDecomposition` | 8 / 6 / 24 | control |
| B Box | `convexHull` | 8 / 6 / 24 | approximation only |
| C Box | `convexDecomposition` | 8 / 6 / 24 | control |
| D Cylinder | `convexDecomposition` | 26 / 36 / 120 | topology and matching extent only |
| E Box | `convexDecomposition` | 8 / 6 / 24 | exit control |

All meshes are closed, outward-wound, non-degenerate, and have matching authored/computed extents. They use `/World/ColliderReferenceMesh` with `PhysicsCollisionAPI` and `PhysicsMeshCollisionAPI`, no transform ops, default purpose, invisible visibility, no RenderSurface, no analytic sibling, and no RigidBody API. D is a static, axis-aligned, Flow-only 12-segment cylinder, radius 0.16 m and length 1.8 m.

## Stage-open matrix

| Condition | Runtime | Last durable boundary | Exit / timeout / fatal / dump / upload |
|---|---:|---|---|
| A Box decomposition | 14.443 s | `shutdown_requested` | 0 / 0 / 0 / 0 / 0 |
| B Box hull | 14.640 s | `shutdown_requested` | 0 / 0 / 0 / 0 / 0 |
| C Box decomposition | 14.375 s | `shutdown_requested` | 0 / 0 / 0 / 0 / 0 |
| D Cylinder decomposition | 15.735 s | `shutdown_requested` | 0 / 0 / 0 / 0 / 0 |
| E Box decomposition | 14.304 s | `shutdown_requested` | 0 / 0 / 0 / 0 / 0 |

Every process reached pure OpenUSD open, USD-context connection, Hydra observation, first renderer update, first viewport frame, stage close, renderer drain, plugin shutdown, and normal OS exit. RTX selected the GeForce RTX 3090, CUDA index 0, Hydra mask 1, and viewport device 0 in each run.

This denies the Phase 6DX pre-stage wait as a necessary lifecycle step. It also shows that Box `convexHull` is not sufficient to reproduce the historical cylindrical Hull crash. It does not qualify Cylinder `convexHull`.

## Public Flow readback

After A-E qualified, A, D, and E were run as separate processes through the existing Phase 6DT public NanoVDB readback. The graph used density cell size 0.025 m, measured velocity voxel size 0.0500000007 m, `physicsCollisionEnabled=true`, `physicsConvexCollision=true`, and the same emitter/settings/frames for all three conditions. Box before/after produced identical time series and active-block counts (24 / 24); the Cylinder finished at 26 active blocks.

The original Box-oriented `inside_core` ROI is wider than the cylinder. It therefore reported Cylinder frame-200 temperature mean 0.02024925 and is not a valid solid-volume penetration measure. A common supplemental cuboid, analytically contained within the 0.16 m cylinder, was sampled in every Box and Cylinder process:

| Cylinder, frame 200 | Mean | p95 | Maximum | Nonzero voxels |
|---|---:|---:|---:|---:|
| core temperature | 0 | 0 | 0 | 0 |
| core fuel | 0 | 0 | 0 | 0 |
| core burn | 0 | 0 | 0 | 0 |
| core smoke | 0 | 0 | 0 | 0 |
| core velocity magnitude | 0 | 0 | 0 | 0 |
| cylinder-above temperature | 1.0891e-5 | 4.6492e-6 | 0.0066414 | 171 |
| cylinder-above velocity magnitude | 0.0046399 | 0.0116008 | 0.0382939 | 207 |

The core was zero at frames 60, 120, 180, and 200 for all four scalar channels and velocity. The nonzero values in the wide Box ROI occupy space outside the cylindrical solid and are consistent with lateral bypass, not passage through the cylinder core. A small residual remains above the cylinder, so the result is not described as perfect global occlusion.

## Classification and next boundary

### Observed

- All five stage-open processes and all three Flow-readback processes exited normally with fatal, crash dump, and automatic-upload counts of zero.
- Box controls were byte-identical offline and numerically identical before/after Flow readback.
- Box `convexHull` and Cylinder `convexDecomposition` both pass the calibrated stage-open and teardown boundary.
- Cylinder-contained Flow scalar and velocity samples remained zero at all sampled frames.

### Strong inference

- Phase 6DX failed in its pre-stage viewport-frame wait, not in the tested stage content.
- The low-detail cylindrical topology is safe for the static, axis-aligned, Flow-only `convexDecomposition` configuration on this fixed Kit 110.2 / Flow 110.0.0 / RTX 3090 environment.
- The wider-ROI signal is lateral flow around the narrower obstacle rather than cylinder-core penetration.

### Unconfirmed

- The historical `omni.fabric.plugin.dll` crash root cause and Cylinder `convexHull` remain unresolved.
- Rotation, PhysX sharing, an analytic sibling, dynamic transforms, Phase 6DR integration, and 20-log cost remain untested.
- No internal Flow collision representation is inferred beyond the public stage and readback observations.

Phase 6DU may resume in a new independent Phase from the qualified static Cylinder `convexDecomposition` configuration. Cylinder `convexHull` must stay excluded until a separately approved, guarded experiment. No production integration is performed here.

No new demo video is created because this Phase changes no production-visible behavior; the existing latest-demo pointer remains unchanged.

## Regression

- Release build: passed in 6.80 seconds.
- Lifecycle marker contract: 6 / 6 passed.
- Focused Flow-scene collider contract: 1 / 1 passed in 0.073 seconds.
- Public readback runtime target: 3 / 3 processes and 12 / 12 samples passed.
- Standard suite: 8 processes, 78 / 78 tests passed in 305.9 seconds; collapse coverage completed in 179.5 seconds.
- Devlog static validation: 330 unique local references, missing 0, JSON/SVG failures 0, UTF-8 replacement characters 0.
- Phase 0 RTX was not required because production code/app composition did not change and all renderer lifecycles remained normal.
