# Phase 6HY exact Kit import boundary and safe stop

## Frozen history and scope

Phase 6HX remains frozen at `4d83948` as
`safe_stop_kit_import_harness_failure`. No Phase 6HX root, runtime attempt,
artifact, image, classification, or threshold was reused or reclassified.
Phase 6HY declared a new exact-import contract before runtime and bound the
frozen Phase 6HX scene contract by SHA-256. The physical scene, OFF/ON order,
ROI definitions, temporal window, visual gates, resource limits, Point-policy
manifest, and production invariants were not changed.

## Deterministic loader

The wrapper derives the repository root from its own absolute path, validates
the non-reparse `scripts` directory under that root, verifies the wrapper,
loader, probe-builder, nested builder, and frozen operation-source SHA-256
values, then loads the probe builder with `spec_from_file_location`. A
repository-local `scripts` path is placed first only in this Kit process and
all observed `phase6h*` nested local modules must resolve inside it. Existing
same-name modules, a different `__file__`, missing callables, root escapes,
reparse redirection, or hash changes fail closed. The contract digest is
`8FB7914FB75C8F9BF8A8E4A34FBF936F6B519B880C8F99149C4CC8A7A290881C`.

The actual resolver/loader no-Kit fixture passed 12/12. The inherited
Point-policy, atomic-report, and generated-stage fixtures passed 13/13,
15/15, and 11/11 respectively. These fixtures launched no Kit process.

## Real Kit smoke result

One fresh app-ready Kit smoke was launched without retry or replacement. Kit
reached `kit_app_ready`, but the wrapper then called its durable marker helper
with both the helper's positional `path` parameter and a payload field named
`path`. Python raised `TypeError: _append() got multiple values for argument
'path'` before `wrapper_resolved`, probe loading, or import completion.

This is a deterministic smoke-marker harness failure. It does not show that
the new resolver accepted or rejected the target probe module. The process did
not quit naturally and the guard reached its 180-second absolute timeout.
Resource gates remained safe: Kit/tree peaks were 11,376,861,184 and
11,501,965,312 bytes, leaving 5,803,008,000 and 6,751,645,696 bytes below the
16/17 GiB ceilings. Available physical and commit headroom minima were
81,503,399,936 and 101,465,600,000 bytes. Exact cleanup ended with residual
zero. No stage, Flow simulation, CollisionProxy, capture, active-block sample,
occupancy calculation, image, or video was created.

## Classification and next boundary

Phase 6HY is `safe_stop_kit_import_smoke_marker_harness_failure`. The formal
OFF/ON launch count is zero. The exact import boundary and the single-log
visual occlusion signature remain unqualified. A separately approved Phase
must first reserve marker-helper argument names and fixture the real wrapper
payloads, then perform one new app-ready smoke from a new root. It must not
reuse this smoke or automatically enter OFF/ON.

Production source, defaults, canonical Point-policy source set, wood
authority, Point payload/revision/ordering, V3, public scenes, and latest demo
are unchanged. Production placement, arbitrary pose, dynamic transform,
PhysX sharing, Point Emitter coexistence, 4/20-log performance, P3, P4,
production integration, and default-ON remain unqualified.

Python compilation, focused tests 2/2, Release build, the standard eight-
process 78/78 suite, and static devlog validation passed. Phase 0 RTX and
Phase 3 were omitted because production sources, USD generation, rendering,
wood authority, and Flow inputs were unchanged.
