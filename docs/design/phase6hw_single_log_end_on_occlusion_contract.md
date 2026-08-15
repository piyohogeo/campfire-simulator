# Phase 6HW — single-log end-on Flow occlusion contract

Phase 6HV remains frozen at `91f6b06` as `safe_stop_visual_gate`. Its
thresholds, images, artifacts, and classification are not reused or relaxed.
Phase 6HW is a separate diagnostic scene intended to expose a simpler causal
visual signature before any return to the production hierarchy.

The stage contains one X-axis log proxy, one Sphere source centered directly
below its cross-section, an end-on camera whose image-up is world Z, and the
Phase 6DS/6EO/6HU Flow values. Stones, other logs, floor reflection geometry,
Point Emitters, readback, and opaque wood rendering are absent. Raw captures
are Flow-only; postprocessing adds a deterministic cross-section outline and
the frozen ROIs equally to OFF and ON.

The cross-section is exactly the Phase 6HS 12-segment, radius-0.16 m closed
outward Mesh topology (26 vertices, 36 faces, 120 indices). Only its X length
is doubled from 1.8 m to 3.6 m for this diagnostic. With log center Z=0.90 m,
source center Z=0.48 m, and source radius 0.20 m, source support remains 0.06 m
below the proxy surface: 1.2 expected 0.05 m velocity voxels. Source support is
1.60 m, or 32 velocity voxels, from the nearest longitudinal end. Therefore a
visible bypass is less plausibly an end escape, but this longitudinally
extended scene is explicitly not production-shape qualification.

OFF and ON are fresh independent processes in fixed OFF→ON order. Their stages
are authored and hashed before Kit launch and may differ only in
`FlowSimulate.physicsCollisionEnabled`. Stable captures are frames 120 through
240 at stride 10. Per-pixel Flow-color occupancy, occupancy-frequency maps,
time means, and the fixed source/direct/left/right/upper/background ROIs are
the primary evidence; final-frame differences are not a gate. Active blocks
at frames 60/120/180/240 must each be at least 128, but are liveness evidence
only.

The machine-readable contract fixes all geometry, camera, capture, mask, ROI,
and numeric thresholds. Qualification requires the full numeric gate and human
confirmation of a persistent OFF central column, ON central suppression,
lateral bypass, and upper re-merge without whole-field extinction. Ambiguous
evidence fails closed. Success stops before production placement, arbitrary or
dynamic pose, PhysX sharing, Point coexistence, performance, P3/P4, defaults,
V3, or production integration.

## Result: pre-Kit harness safe stop

The no-Kit preflight qualified the atomic producer path (15/15) and the
generated-stage contract (12/12), including exact OFF/ON stage hashes and a
two-line USD diff limited to `physicsCollisionEnabled`. The formal fresh root
was then created, but the parent runner stopped before target construction or
Kit launch while hashing production invariants: it referred to the nonexistent
`source/extensions/campfire.app/campfire/app/point_emitter.py` path.

This is a deterministic pre-Kit harness-path failure, not Flow, collision,
rendering, resource, or lifecycle evidence. OFF and ON both have launch count
zero; no active-block samples, captures, occupancy metrics, human visual gate,
or comparison video exist. The root is frozen and will not be reused. Phase
6HV remains `safe_stop_visual_gate` without reclassification or image reuse.
A later separately approved Phase must first bind the Point-policy invariant
to an existing canonical source set and add that existence check to the
no-Kit producer-to-runner fixture, then use another empty root.

Post-stop verification passed Python compilation, the five focused Phase 6HW
tests, Release build, the standard eight-process / 78-test suite, and static
devlog validation. Phase 0 RTX and Phase 3 were not repeated because no
production source, USD generation path, renderer/app dependency, wood
authority, or Flow input changed. A final exact-name process inventory found
zero Kit/CDB/NGX/telemetry residuals.
