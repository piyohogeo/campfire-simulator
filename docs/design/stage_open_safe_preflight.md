# Phase 6DX stage-open safe preflight

## Purpose and safety boundary

Phase 6DX attempted to restart the Box-to-Cylinder stage-open classification after Phase 6DW re-established normal renderer lifecycles. The previously failed cylindrical `mesh_hull` condition was not run. The executable matrix was deliberately limited to the known-good Box, a Box approximation-only change, and a Cylinder-topology-only change retaining `convexDecomposition`.

Production code, the production app, Flow 110.0.0, V3, Resident state, emitters, colliders, and defaults were not changed. Every condition was assigned a separate Kit process with a 420-second timeout, crash-upload opt-out, dump preservation, fatal-token gates, production SHA-256 checks, and no automatic retry.

## Result

The first and only process was the unmodified Phase 6DT known-good Box stage. It selected RTX 3090 / CUDA device 0 but timed out at 420.474 seconds. Its last durable marker was `renderer_readiness_warmup_started`.

No stage was prepared, opened through pure OpenUSD, registered in the USD context, or connected to Hydra. No first renderer update or viewport frame was recorded. The Box approximation and Cylinder topology branches were therefore not started.

| Condition | Started | Last boundary | Exit | Crash / dump / upload |
|---|---:|---|---:|---:|
| known-good Box | yes | pre-stage viewport-frame wait | timeout | 0 / 0 / 0 |
| Box + `convexHull` | no | fail-fast | n/a | n/a |
| Cylinder + `convexDecomposition` | no | fail-fast | n/a | n/a |

The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A` before and after the process. No crash dump, automatic-upload attempt, native fatal token, CUDA illegal address, device-lost event, or RTX stage-id error was observed.

## Classification

### Observed

- The new harness waited for eight viewport frames before constructing or connecting a stage.
- In the no-window minimal viewport app, that pre-stage frame wait did not complete within the bounded process lifetime.
- Phase 6DW's qualified sequence only required an active viewport before connecting the stage; it waited for a viewport frame after the USD context and Hydra boundary.
- The matrix stopped on the control and did not run any Box-to-Cylinder difference.

### Strong inference

The pre-stage `next_viewport_frame_async()` readiness step is not a valid control for this no-window composition. The result is a harness/lifecycle failure before stage content, not evidence about Box geometry, Cylinder topology, `physics:approximation`, collision schemas, or Flow occlusion.

### Unconfirmed

The historical `omni.fabric.plugin.dll+0xD6960` native fault remains unresolved. Nothing in this run establishes whether topology, approximation, hierarchy, render surface, analytic siblings, multi-GPU timing, or another Fabric/Hydra lifetime boundary contributes to that fault.

## Decision

Phase 6DU runtime validation is not resumed. A future independent harness must use the Phase 6DW-qualified readiness order, obtain a known-good Box normal OS exit, and stop again on any control anomaly. Only after that control may one-difference topology work resume. The previously failed Cylinder Hull branch must still not be automatically retried.

Because no visual state was produced or changed, no demo video was generated and the latest-demo pointer remains unchanged.

## Regression

- Release build: passed in 6.79 seconds.
- Standard suite: 8 processes, 78 / 78 tests passed in 304.5 seconds.
- Devlog static validation: 326 unique local references, missing 0, UTF-8 replacement characters 0; JSON and SVG parsing passed. Browser rendering was unavailable because no browser connection was available in this session.
- Phase 0 RTX was not rerun because production code and app composition did not change and the diagnostic runtime matrix had already stopped at its control boundary.
