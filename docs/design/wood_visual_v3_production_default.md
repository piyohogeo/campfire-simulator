# Phase V3T-P — Wood Visual V3 production default

## Decision

Wood Visual V3 is the production-default wood appearance for the normal app and the production-equivalent benchmark from this phase onward. It is a regenerable display observer: moisture, dry wood, char, ash, and temperature remain authoritative only in the wood model and immutable Resident snapshot. V3 must never be read back as physical truth or used as a Flow, checkpoint, rollback, or serialization commit condition.

The qualified transport is the CPU-source `omni.ui.DynamicTextureProvider.set_raw_bytes_data()` path. GPU-source transport remains experimental and is not enabled or resumed by this phase.

## Configuration contract

The normal `campfire.simulator.kit` and debugger-free `campfire.simulator.benchmark.kit` now start Phase 3 with the following production defaults:

- `woodVisualV3Enabled=true`
- `woodRenderHierarchyEnabled=true`
- `residentSnapshotAdapterEnabled=true`
- `residentSnapshotHandleCacheEnabled=true`
- `residentSnapshotLightweightCommitEnabled=true`
- `residentSnapshotSkipUnchangedEnabled=true`
- `residentNativeBackendEnabled=true`
- `woodVisualV0Enabled=false`
- Resident Point and rigid-layout feature flags remain `false`

The packaged `campfire_wood_native.dll` is resolved only when V3 and the native backend are active and no explicit library path was supplied. An explicit path still wins, and a missing packaged library fails closed. The native binary is staged with the extension; no artifact-relative production dependency remains.

Phase 3 legacy/isolation runners explicitly pass `woodVisualV3Enabled=false` and `woodRenderHierarchyEnabled=false` where their purpose is authority, Flow, Point, rigid-layout, or historical comparison. Phase selection outside Phase 3 does not activate the Phase 3-only V3 observer. V0 remains an explicit fallback/diagnostic path and cannot be enabled together with V3.

## Correctness and lifecycle evidence

Three rotated OFF/ON production-equivalent runs plus one normal-app default-ON run produced identical dry, wet, and metrics hashes. Both logs reported mass-balance error `0`, Resident revision `1200`, and unchanged Flow fuel/temperature/smoke publication. All default-ON runs ended with V3 revision and processed revision `1200`, failure `0`, and no rollback of wood or Flow.

The independent real-Kit lifecycle probe passed `17/17` gates. It verified two fixed atlas resources, unchanged/stale revision handling, visual-only failure recovery, timeline restart, stage reload with forced latest base/emission republish, stable Prim paths and Mesh topology, render Mesh without physics, retained analytic collider, consumer revision equality, and visible reflection within the bounded probe frames. Stage reload first republish took `3.9539 ms`. Crash, dump, and automatic upload counts were zero.

The 240-second burn retained the deterministic authority hashes, mass balance `0`, delayed wet ignition, Flow active blocks, and V3 failure `0`. Final authoritative state included:

| State evidence | Dry log | Wet log |
|---|---:|---:|
| Surface mean temperature | 1189.22 K | 549.53 K |
| Remaining moisture | 4.658 kg | 24.377 kg |
| Char mass | 6.724 kg | 0.447 kg |
| Ash mass | 0.0190 kg | 0.0004 kg |

These values feed the native surface payload and produce the dry/wet contrast, dark char, rough ash contribution, and temperature emission visible in the production demo. Unmodelled render logs keep the neutral fallback appearance.

## Performance result

All performance runs used Candidate Performance, RTX Real-Time 2.0, DLSS Performance, two bounces, 1280×720, and the unchanged 210 W (60%) power limit. Capture and encoding were outside the performance population, and no additional RenderProduct or HydraTexture was created.

| Measurement | V3 OFF | V3 ON |
|---|---:|---:|
| 20-log visible viewport, 3 runs | 47.054 FPS | 45.784 FPS |
| HUD mean frame time | 21.329 ms | 21.904 ms |
| Kit update interval p95, median run | 28.035 ms | 28.374 ms |
| Production-equivalent Phase 3 loop, 3 runs | 98.328 FPS mean | 50.312 FPS mean |
| Normal app default path, 1 run | — | 30.528 FPS |

The 20-log production-equivalent viewport remains above the normal 45 FPS target. The normal app run remains above the 30 FPS minimum but has little margin; it includes the normal app's developer/UI extension surface and is a follow-up performance risk, not a correctness failure. The user-visible value of stateful wood appearance and the absence of periodic stalls justified conditional promotion.

Across the three benchmark ON runs and normal-app qualification, 2,412 publication records had these aggregate tails:

- provider setter: p50 `1.6348 ms`, p95 `9.3610 ms`, p99 `10.8140 ms`, max `12.6456 ms`
- total publication: p50 `2.4329 ms`, p95 `10.1752 ms`, p99 `11.7879 ms`, max `13.9464 ms`
- total publications above 30 / 33.333 / 50 ms: `0 / 0 / 0`

Base-only, emission-only, both, and unchanged publications are separately recorded in the machine-readable report. A benchmark run performed 868 texture uploads, 99 quantized unchanged skips, and 504 visual commits. The adaptive scheduler published at an effective `2.5125 Hz`, with actual visual commits at `2.1000 Hz`, inside the intended 2.5–5 Hz control range once quantized no-op commits are excluded.

The visible-FPS comparison measured the public `ViewportAPI.frame_info` render counter only. Display-present FPS, raw renderer frame intervals, GPU render time, and 1% low were not available from the safe public path and are not estimated.

## Promotion gate and remaining constraints

The promotion report passed `14/14` gates. This phase therefore changes the product default, not the authority or transport contract. Remaining constraints are:

- CPU-source publication still has a measurable p95 near 10–15 ms depending on scene and probe; it must remain low-frequency/change-aware.
- The normal app has only about 0.5 FPS of measured headroom above the 30 FPS floor in the single qualification run. A sustained regression below 30 FPS reopens the decision.
- DynamicTextureProvider does not provide a multi-texture atomic commit. V3 remains an eventually consistent observer, although this CPU-source route publishes complete buffers and the stage-reload gate converged.
- GPU-source rings, shape deformation, and flame-derived lighting are separate phases and were not modified.
- The fixed Flow 110.0.0 topology safe stop from Phase V3T-M remains in force.

Machine-readable evidence is in `docs/devlog/assets/phasev3tp/production_promotion_report.json`; raw publication samples are in `production_promotion_samples.json`.
