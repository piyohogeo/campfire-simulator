# Phase 6FA Flow functional-liveness diagnosis

## Scope and frozen history

Phase 6EY's R0 3/3 and R1 1/1 qualifications are immutable. Phase 6EZ through commit `0066ab3` is also immutable: corrected C0 passed, while C1 completed one same-object zero-copy `numpy.asarray(fuel)` boundary and normal OS exit but failed the unchanged Phase 6EY dynamic-stationarity contract because all 49 observation samples were 24 active blocks. This Phase neither reclassifies C1 nor reuses either result as a formal sample.

Production code, Flow settings, Point ordering/payload/revision, CollisionProxy geometry, wood authority, V3, and all resource ceilings are unchanged.

## Read-only evidence before runtime

C0 and C1 used the same stage SHA-256 `073D985D9DFE56C1C45745B85328D37F7B0E6CE268C180BEBF218402C3E13EA2`, Point payload SHA-256, four-log transforms, 1,440 total / 1,344 active points, collision settings, fuel/temperature/smoke sums, revision, renderer settings, sample frames, and lifecycle sequence. The intended readback mode and output paths were the only material argument differences.

C1 was already at 24 active blocks at frame 30. Public readback and `numpy.asarray` occurred at frame 60, so neither operation can be the direct cause of the initial small field. C1 remained at 24 for the complete 24-second observation while timeline time and update indices changed. Its public channel buffers were also much smaller than C0's. These facts make stale active-block telemetry unlikely and support a real smaller Flow allocation. They do not establish why the Point field was smaller.

The pre-runtime hypothesis order is:

1. Runtime Point-emitter ingestion or a fixture/lifecycle boundary failed nondeterministically, so the Flow field did not grow.
2. Independent-process initialization order changed ingestion despite an identical offline stage.
3. Observation began too early; weakened because the field stayed small throughout the long observation.
4. Readback or release affected later field lifetime; unable to explain frame 30.
5. `numpy.asarray` caused the initial collapse; excluded by marker order.
6. Telemetry was stale; unlikely given fresh timing and independently smaller buffers.
7. 24 blocks were a meaningful physical steady state; not accepted without functional-liveness evidence.

## Frozen diagnostic sequence

The contract `campfire.phase6fa.flow-liveness-occupancy-contract.v1` is hashed before runtime. Each condition is a fresh independent Kit process with the same stage, deterministic payload, warmup, sample frames, 24-second post-frame-320 observation, safety guard, and lifecycle.

- D0: same probe with no public readback.
- D1: one public readback at frame 60, no `numpy.asarray`, C1's explicit alias-release order.
- D2: D1 plus exactly one `numpy.asarray(fuel)`.

D0 must first form the representative four-log field; otherwise D1/D2 are not started. D1 must pass before D2. There is no automatic retry.

The liveness audit records each frame's monotonic timestamp, timeline time and play state, active blocks, USD root identity, and Flow interface identity. D1/D2 decode the public fuel buffer using `flow.buffer_to_volume`, `omni.volume.save_volume`, and the bundled NanoVDB reader; only active Point positions are sampled and the temporary file is deleted. This is public-field evidence, not access to Flow's internal collider or occupancy mask.

## Dynamic and constant occupancy

Dynamic occupancy retains the Phase 6EY finite non-divergence checks, including occupancy trends and block-drop memory response. Constant occupancy does not require artificial increase/decrease fractions or a block-drop response. It instead requires all of the following:

- fresh timestamps and advancing, playing timeline;
- positive source input, 1,344 active of 1,440 points, and revision 1;
- unchanged stage and Flow identities;
- a meaningful public fuel field for readback conditions;
- at least 128 active blocks for this fixed four-log fixture, so 24 is not accepted merely because it is constant;
- Kit Private Bytes slope at most 8 MiB/s, projected drift at most 5%, normalized drift at most 25%, and high-water recovery or plateau;
- unchanged 14 GiB Kit, 16 GiB tree, 512 MiB runner/diagnostic and 8 GiB headroom limits;
- complete stage close, extension shutdown, normal OS exit, and zero fatal/dump/TDR/upload/residual evidence.

Synthetic fixtures accept constant/flat, constant/bounded-noise, dynamic/bounded-response, and block-drop/memory-recovery series. They reject linear or accelerating memory growth, stale block telemetry, stopped timeline, missing Emitter input, empty field, a constant 24-block trace, and memory growth after block reduction.

## Claim boundary

Even if D0/D1/D2 pass, the result qualifies only one fixed-condition fuel alias lifetime. It does not qualify repeated readback, repeated conversion, other channels, field persistence, production integration, or any resource-ceiling increase.
