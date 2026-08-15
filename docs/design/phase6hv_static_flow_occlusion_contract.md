# Phase 6HV — static production-hierarchy Flow occlusion contract

Phase 6HS, Phase 6HT, and Phase 6HU remain frozen at `fbbac6f`, `89ae109`,
and `a380276`. Their artifacts and classifications are not changed. The Phase
6HU process is used only to freeze the authoring digest and pre-runtime ROI
coordinates; it is not reused as the formal Collision-OFF result. Phase 6HV
starts from a new artifact root and launches one fresh OFF process followed by
one fresh ON process, without retry or replacement.

## One-variable boundary

Both processes retain the production wood hierarchy, Log_00 world matrix,
Phase 6HS 26-vertex/36-face/120-index closed outward proxy, source center
`(0, 0, 0.55)`, diagnostic radius 0.2 m, Flow source/material authoring,
camera `(2.65, -4.2, 2.35) -> (0, 0, 1.05)`, 1280x720 capture, 12 stopped
updates, 240 playing updates, samples at frames 60/120/180/240, and eight
stopped drain updates. Only `FlowSimulate.physicsCollisionEnabled` differs.

Before stage connection and simulation, each generated candidate USD must
match its frozen exact SHA-256 and a common SHA-256 obtained by normalizing the
single collision value. The settings descriptor is independently hashed.
Phase 6HU's qualified OFF stage seeds the no-Kit authoring fixture only; the
formal processes generate fresh stages and verify those digests again.

The fixed order is OFF then ON. OFF must reproduce at least 128 active blocks
at every sample. ON uses a predeclared liveness floor of 25 blocks at every
sample: this is strictly above the known 24-block non-representative plateau,
but cannot prove occlusion by itself. Source-near and diverted image signals
are separate gates. Failure in operation, stage identity, resource, lifecycle,
cleanup, or the OFF sensitivity condition stops before any later condition.

## Frozen image evidence

The direct-path, two side, upper, source-near, and sky background/control ROIs
are normalized coordinates in the immutable contract. Per-condition change is
measured between the fixed baseline and final captures. A bounded yellow-orange
mask supplies a second visible-Flow signal. The ON/OFF comparison requires:

- a sensitive OFF direct path;
- ON source-near Flow and side or upper diversion;
- direct changed-pixel, mean-delta, and color-mask suppression;
- stable baseline and final background controls;
- an ON/OFF final difference not explained by global brightness alone; and
- human confirmation of direct suppression plus lateral diversion or rise.

The numeric thresholds and all ROI bounds are fixed in
`scripts/phase6hv_static_flow_occlusion_contract.json`. These are image-space
transport proxies, not conserved physical flux. Ambiguous imagery, extinction
of the entire field, or direct passage through the log fails closed.

## Safety and scope

Phase 6HU atomic reporting, Phase 6HS canonical operation evidence, the 16 GiB
Kit and 17 GiB unique-tree ceilings, machine floors, accepted lifecycle
classes, and exact identity cleanup remain unchanged. Readback, volume
conversion, NanoVDB files, sampling, directional flux, P3 comparison, dynamic
transforms, PhysX sharing, Point policy, multiple proxies, 4/20-log
performance, production integration, defaults, V3, and latest-demo updates are
forbidden. Success stops after this two-process static boundary.
