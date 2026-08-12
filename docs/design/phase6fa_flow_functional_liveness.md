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

## Runtime result and safe stop

The first new root established a healthy D0 control: 49 stationarity samples covered 1,121–1,567 active blocks with mean 1,360.143, its dynamic-memory gate passed, stage close took 2.498 seconds, and the process exited normally. D1 then reproduced the small field independently: all 60 per-frame observations from frame 1 through frame 60 were fresh values of 24 while timeline time advanced from 0.0167 to 1.0 seconds. The readback boundary follows the frame-60 observation. Therefore public readback, alias release, and `numpy.asarray` cannot be the direct cause of the initial 24-block field. A diagnostic helper name error prevented the public fuel semantic decode; D1 closed in 2.634 seconds and left no process residual. D2 was not started.

After correcting only that helper, the formal population restarted from D0 in a second empty root; no root-1 evidence was reused. D0 again formed the representative dynamic field (1,121–1,558 active blocks, mean 1,361.551) and passed the memory-stationarity checks. It then exceeded the frozen 180-second `close_stage_async()` limit. Bounded CDB collection reached an `omni_usd` context-destruction / extension-shutdown stack boundary but timed out before a complete detach marker; the accepted NGX five-token signature did not match and the lock owner is unknown. Exact-identity cleanup removed the observed Kit and children, with zero residual afterward. D1 and D2 were not started.

### Confirmed facts

- Phase 6EZ C1 and the independent Phase 6FA D1 both had 24 blocks before their readback boundary.
- Timeline and telemetry samples advanced, and the frozen C1 returned much smaller public buffers than C0. The value is not consistent with a single stale integer being replayed.
- Stage, Point payload, 1,344 active / 1,440 total points, revision 1, transforms, source sums, and Flow settings match between the audited C0/C1 inputs.
- Phase 6EZ's same-object, shared-memory, zero-copy `numpy.asarray(fuel)` observation remains valid as an observation, but is not qualified under the Phase 6FA liveness contract.
- The 14 GiB Kit and 16 GiB tree ceilings were unchanged.

### Strong inference and unknowns

The narrowest supported causal boundary is per-process Flow/Point-emitter startup or source ingestion before readback. The exact trigger— including whether immediate cross-process sequencing contributes—remains unconfirmed. The D1 helper failed before semantic field decoding, so the complete functional-liveness gate was not satisfied even though authored input, timeline, and fresh occupancy telemetry existed. The second-root unknown stage-close wait is a separate lifecycle blocker. Repeated readback cannot proceed until both boundaries are resolved.

The machine-readable result is `docs/devlog/assets/phase6/flow_functional_liveness_safe_stop.json`; the comparison figure is `flow_functional_liveness_safe_stop.svg`. Phase 6EY/6EZ history remains unchanged, Phase 6FA does not qualify one fuel alias lifetime, and production is unchanged.

Final regression passed 22/22 focused Phase 6FA/6EY/6EZ contracts, the Release build in 7.75 seconds, Phase 0 RTX, Phase 3, and the standard eight-process suite with 78/78 tests in 349.5 seconds. Phase 3 retained zero dry/wet mass-balance error, the established dry/wet authority hashes, active blocks final/peak 256/353, and peak fuel 1.0. The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`; final Kit/CDB/GPU-helper residual count was zero. Devlog validation passed 419 references, 257 IDs, 209 JSON files, 175 SVG files, and two ZIP files.
