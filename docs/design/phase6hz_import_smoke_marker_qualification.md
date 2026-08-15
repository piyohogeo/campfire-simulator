# Phase 6HZ reserved-key-safe Kit import smoke qualification

## Frozen history and scope

Phase 6HY remains frozen at `40ff0e0` as
`safe_stop_kit_import_smoke_marker_harness_failure`. Its root, runtime
attempt, artifacts, classification, and failed marker call were not modified,
reclassified, or reused. Phase 6HZ used a new contract and new artifact root
only to qualify the marker boundary and one exact app-ready import smoke.
Collision OFF/ON, stage construction, Flow, CollisionProxy, Emitter, capture,
occupancy, NanoVDB readback, P3, and P4 were out of scope.

## Marker contract

The marker helper names its destination argument `marker_file` and takes a
canonical payload mapping rather than mixing helper arguments with arbitrary
`**kwargs`. Reserved keys are derived from the actual helper signature and
augmented with helper-owned `marker`, `timestamp_utc`, and legacy `path`.
Payload paths use explicit names such as `resolved_path`, `module_path`, and
`expected_wrapper_path`. Unknown events or payload keys, missing keys, invalid
types, reserved-key intersections, and duplicate or conflicting values fail
closed before Kit launch.

The real producer-to-helper fixture emitted all 12 runtime marker payloads to
JSONL and passed 11/11 positive and negative cases. The frozen Phase 6HY exact
loader fixture independently remained 12/12. Kit launch count during this
preflight was zero. The new contract SHA-256 is
`5D05CE4D7DA82EF538D406DF79CDFDFDF9AE73D2C3B9DC92C7EA8A8F4BA6D457`;
the implementation commit is `b46c140`.

## Exact app-ready smoke

One fresh Kit process was launched with no retry or replacement. The wrapper,
scripts directory, and probe source resolved under
`C:\Users\junic\src\campfire-simulator`. The wrapper SHA-256 was
`D0FAF3880C01424211765394C527C0944B39C71B93B6ED9602621BD55862B730`.
The exact probe was `scripts/phase6hy_probe_source.py`, SHA-256
`4F373882C6BC8AAB14247E2B5A9916550444DC283947D5B3321FAA0F7A622B35`.
Its loaded `__file__` matched the expected absolute path and
`build_probe_source` was callable.

All required markers completed in order from `kit_launch` through
`shutdown_complete`. The operation report proves zero stage creation, zero
Flow-interface/readback/capture calls, and no CollisionProxy. Kit exited with
code 0. The canonical lifecycle class was
`cleanup_assisted_telemetry_exit`, accepted by the existing Phase 6HR policy;
exact cleanup ended with residual process count zero.

Kit/tree peaks were 7,253,692,416 and 7,739,625,472 bytes, leaving
9,926,176,768 and 10,513,985,536 bytes below the 16/17 GiB limits. Runner and
diagnostic peaks were 97,820,672 and 16,199,680 bytes. Available physical and
commit headroom minima were 85,150,494,720 and 105,112,694,784 bytes.

## Qualification and next boundary

Phase 6HZ qualifies only the reserved-key-safe durable marker contract and
the exact Kit app-ready wrapper-to-probe import boundary. It does not qualify
the frozen single-log visual occlusion signature. A separately approved Phase
may start a fresh OFF-then-ON comparison using the unchanged Phase 6HW/HX
geometry, source, camera, ROI, temporal window, and gates.

Python compilation, focused tests 4/4, Release build, the standard
eight-process 78/78 suite, and static devlog validation passed. Phase 0 RTX and
Phase 3 were omitted because production code, USD generation, rendering,
wood authority, and Flow inputs are unchanged. Production source, defaults,
canonical Point-policy set, Point payload/revision/ordering, wood authority,
V3, public scenes, and latest demo remain unchanged. No video was generated.

