# Phase 6HU — atomic report and visible Flow baseline contract

Phase 6HT (`89ae109`) remains a frozen safe stop. Its Collision ON sample is
not rerun, reclassified, or reused as a Phase 6HU runtime sample. Phase 6HU
qualifies only two prerequisites: bounded raw-report replacement with cleanup
continuity, and one representative Collision-OFF Flow baseline.

## Confirmed pre-runtime audit

The Phase 6HT Kit probe appended and fsync'd `markers.jsonl`, then wrote the
replaceable `raw_operation.json` snapshot through a fixed `.tmp` followed by
`os.replace()`. At the same time, the PowerShell shutdown monitor and Python
resource guard polled that destination. Their Windows read handles do not
guarantee delete sharing. The frozen Phase 6HT failure is therefore located at
the snapshot replacement after `timeline_stop_complete`; it is not evidence of
a Flow, CollisionProxy, resource, or stage-close failure because those later
boundaries were never attempted.

The no-Kit fixture reproduces the relevant Windows share mode explicitly. A
held destination read handle produces WinError 5, while release of that handle
allows the same replacement to complete. This confirms reader/replace sharing
contention as a sufficient cause in the fixture. It does not identify which
specific Phase 6HT reader held the handle at the exact instant of failure.

## Atomic snapshot contract

- `markers.jsonl`, appended and fsync'd, remains the lifecycle source of truth.
- The JSON snapshot is capped at 1 MiB.
- Each write uses a unique same-directory temporary and an exclusive writer
  lease. A second writer fails closed.
- Only Windows errors 5, 32, and 33 are retryable.
- The frozen limit is five total attempts, 0.25 s maximum elapsed time, and
  10/20/40/80 ms backoff. Other errors are not retried.
- Retry/failure evidence goes to a separate bounded, fsync'd JSONL so no row
  can appear after the canonical `shutdown_complete` marker.
- A raw-snapshot failure makes the operation unqualified, but marker emission,
  timeline stop, renderer drain, stage close, reference release, and Kit quit
  remain on the cleanup path.

The actual Phase 6HS report producer, serializer, reader, validator, and
lifecycle consumer are included in the end-to-end fixture. Existing files,
sequential writes, concurrent reads, transient and persistent sharing
violations, unavailable writes, concurrent writers, missing files, and
truncated JSON are classified before any Kit launch.

## Representative Flow baseline

Phase 6EO's Collision-OFF authoring is the known-good display baseline:
source `(0, 0, 0.55)`, radius 0.1 m, front camera
`(2.65, -4.2, 2.35) -> (0, 0, 1.05)`, and 1280x720 rendering. Its recorded
active blocks were 64/58/64/62. Phase 6HT used source
`(0, -0.42, 0)`, radius 0.1 m, a different camera, and recorded 46/46/40/49
under Collision ON.

The user-frozen Phase 6HT gate requires at least 128 active blocks at frames
60/120/180/240. Before runtime, Phase 6HU therefore fixes a diagnostic source
radius of 0.2 m while retaining Phase 6EO's source center, Flow authoring,
render material, camera, update order, fuel, and temperature. This is a
diagnostic sensitivity condition, not a production/default change. The
production wood hierarchy and Phase 6HS proxy remain present, but Flow
collision is disabled.

Qualification requires all four active-block samples to be at least 128, a
baseline/final image pair, a bounded image-change gate, and human confirmation
of a recognizable flame, smoke plume, or rendered Flow volume. Brightness or
active blocks alone are insufficient. Operation, stage close, shutdown, OS
exit, resource limits, exact cleanup, and invariant hashes must also pass.

Collision ON, ON/OFF occlusion, readback, Point policy, dynamic transforms,
PhysX sharing, 4/20-log performance, V3, production integration, defaults, and
latest-demo changes remain out of scope. Success stops before any next phase.
