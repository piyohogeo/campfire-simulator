# Phase 6ES directional scalar transport / full-supply safe stop

## Scope

Phase 6ES keeps the Phase 6ER safe stop frozen and uses a new artifact root and schema. It does not restart Phase 6ER's remaining processes or change production, defaults, Point ordering/schema/revision, wood authority, Flow settings, or CollisionProxy geometry.

The Phase has two intended questions: whether local control-volume transport can separate through-Collider scalar from legitimate side/top detours, and whether enabling the 96 Points whose assumed 0.05 m support spheres intersect another log can safely provide 1440/1440 supply. Calibration stopped on the fixed resource gate before either question could be formally qualified.

## Offline Point classification

The 0.05 m support sphere remains an engineering assumption equal to one velocity voxel. Flow 110.0.0 exposes no exact public Point support radius. An offset of 0 is relative to a surface-cell center rather than the mathematical Mesh surface. At the tested inward position, authored-Mesh self signed distance spans -0.0275 to -0.0150 m.

| Condition | Offset | Active Points | Other centers inside | Active assumed other-support intersections |
| --- | ---: | ---: | ---: | ---: |
| A filtered | -0.0125 m | 1344/1440 (93.33%) | 0 | 0 |
| B full experimental | -0.0125 m | 1440/1440 (100%) | 0 | 96 |
| C offset-zero filtered | 0 m | 1280/1440 (88.89%) | 0 | 0 |

The 96 B Points do not have centers inside another log. Only their assumed support spheres overlap. This experimental policy remains probe-only.

The offline root also contains a 5,760-record JSONL (four conditions × 1,440 immutable payload indices). Each record preserves self/other signed distance, center-inside and support-intersection flags, enable/disable reason, and original/enabled fuel, temperature, and smoke. The aggregate report stores its SHA-256 rather than embedding the records again.

## Directional transport proxy

The control volume is authored in the non-emitting blocker log's local coordinates. Planes lie 0.05 m outside its Mesh bounds at bottom/inlet, top/opposite, both radial sides, and both end caps. Each plane selects a one-channel-voxel-thick slab. The outward proxy is `max(u dot n, 0) * scalar * tangential voxel area`; reverse transport uses the opposite velocity sign. Frame integrals and trapezoidal time integrals are recorded.

A synthetic uniform +Z fixture passed the predeclared sign contract: top outward and bottom inward were positive while side/end transport was zero. The public readback channels are temperature, fuel, burn, smoke, velocity, and divergence. None provides an independent passive source-identity tracer, so source ownership cannot be proven without changing the probe model. The metric is a direction-aware scalar transport proxy, not a physical flux or a strict conservation law.

Two controls completed identically in separate roots. Emitterless Collision ON produced zero blocker deep and face transport for temperature/smoke. Collision OFF at frame 200 produced temperature deep sum 643.0003, top outward 0.2771604, side/end outward 0.0092034, bottom inward 0.3641086; smoke values were 563.7634, 0.2800176, 0.0017533, and 0.2380481 respectively. This establishes signs and a positive path but not a collision qualification.

## Resource safe stop

The first corrected four-log condition, `filtered_933_on`, exceeded the unchanged 14 GiB Kit Private Bytes guard during early Flow sampling:

- root 1: 15,100,735,488 bytes, duration 102.84 s;
- root 2 after scalar-collector bounding: 15,722,414,080 bytes, duration 99.13 s.

Both stopped at `timeline_playing` after three samples. Runner peaks stayed below 97 MB, tree peaks below 15.87 GB, physical and commit headroom remained well above their floors, and exact cleanup left no process. Fatal, dump, automatic upload, device lost, and TDR counts were zero.

Root 1 is retained as the initial invalid calibration. Root 2 used velocity capture for all Colliders and scalar capture only for one predeclared representative production-four blocker. Since the Kit peak remained above the same limit, scalar collector multiplicity is not a sufficient explanation. No limit was raised and the condition was not run a third time.

## Decision

No formal qualification contract was frozen, and the 100% condition, offset-zero runtime, three-run matrix, and videos were not started. Therefore Phase 6ES cannot decide whether the 5 cm filter is necessary, whether all 96 Points are safe, or which offset is recommended. The next separately approved step is a bounded four-log Flow/collector memory calibration that preserves the existing limits. Only after it succeeds may directional transport thresholds be frozen.

Release build, Phase 0 RTX, and Phase 3 passed. Phase 3 retained dry/wet mass-balance error 0, active blocks final/peak 274/335, and peak fuel 1.0. The focused safety/collision contracts passed 161/161 and the standard suite passed 78/78 tests across eight processes in 342.5 seconds. The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.
