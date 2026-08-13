# Phase 6FF — multi-window memory boundedness

## Frozen history and scope

Phase 6FD remains failed under its same-sample response predicate. Phase 6FE remains failed because run01 C0 measured `9.292 MiB/s` against its frozen `8 MiB/s` whole-window slope limit. Phase 6FF neither reclassifies those runs nor changes either historical threshold. Their samples are read-only design evidence and are not eligible for the new formal population.

Production code, defaults, the corrected four-log fixture, Point payload, Flow settings, CollisionProxy, V3, the 14 GiB Kit ceiling, and the 16 GiB unique-tree ceiling remain unchanged. Repeated readback, field persistence, additional channel conversion, forced GC, and production integration are excluded.

The machine contract is `scripts/phase6ff_memory_boundedness_contract.json`; its frozen SHA-256 is `0D69ACADBEC942103081E8892D35866D13E4254FA4A1E15B77CEC3FD27E0612C`.

## Read-only Phase 6FD/6FE audit

All three historical stability windows contained 49 aligned samples over approximately 24 seconds. Their whole-window / last-half / final-window slopes were:

- Phase 6FD C0: `4.896 / -11.837 / +1.326 MiB/s`; terminal residual `+23.227 MiB`, high-water recovery `385.152 MiB` after `0.451 s`.
- Phase 6FD C1: `0.756 / -6.131 / -77.864 MiB/s`; terminal residual `-277.500 MiB`, recovery `491.676 MiB` after `0.528 s`.
- Phase 6FE C0: `9.292 / +12.142 / -148.904 MiB/s`; projected drift `1.654%`, terminal residual `-209.285 MiB`, recovery `666.449 MiB` after `0.498 s`.

The Phase 6FE whole-window value therefore coexisted with two late rolling windows above 8 MiB/s and a large terminal recovery. That observation is consistent with a short mixed growth/reclaim interval, but 24 seconds and 49 samples are below the new minimum and do not prove long-term boundedness. The offline new-contract view consequently fails all historical runs on duration/sample coverage and does not retroactively pass them.

The synchronized marker evidence separately preserves startup, Flow growth, readback before/after, next-frame, stability, timeline stop, stage close, and shutdown boundaries. Working Set, unique-tree Private Bytes, GPU dedicated memory, active blocks, and Private Bytes per active block remain in each formal time series. Historical readback CPU deltas and later residuals are retained without treating process-level C0/C1 peak differences as conversion cost.

## Frozen boundedness model

The formal observation remains live after frame 320 for 48 seconds at a 0.5-second aligned cadence. It requires at least 80 aligned samples over 42 seconds, six equal windows, and at least nine overlapping 8-second rolling windows with 4-second stride.

Four independent layers are evaluated:

1. Absolute safety: Kit `<=14 GiB`, unique tree `<=16 GiB`, physical/commit floors `>=8 GiB`, complete lifecycle, normal OS exit, and zero fatal/dump/upload/residual.
2. Finite transient: maximum growth `<=1 GiB`; a high-water event must recover at least 64 MiB within 32 seconds or end in a final-window plateau.
3. Sustained boundedness: at most two consecutive late rolling windows may exceed the historical diagnostic level of 8 MiB/s; last-half slope `<=2 MiB/s` unless explained by material recovery and bounded normalized drift; final-window slope `<=0.5 MiB/s`; late window-floor slope `<=1 MiB/s` unless the same recovery/normalized condition holds; projected drift `<=5%`; normalized projected drift `<=25%`; terminal residual `<=512 MiB`.
4. Control delta: three no-readback runs establish natural peak, terminal, active-block, and close-time distributions before three one-readback C0 runs. Only after both groups pass may three C1 runs execute. C1 still permits exactly one public readback and one `numpy.asarray(fuel)` call; adjacent synchronized markers remain the primary alias-cost evidence.

The 8 MiB/s number is retained as a rolling diagnostic and persistence detector. It is not used to change Phase 6FE's decision. The new hard decision is the conjunction of finite transient, multiple late-window, recovery, projected-drift, terminal-residual, normalized, absolute-resource, and lifecycle evidence.

## Synthetic calibration

Before Kit runtime, the contract must accept startup-to-plateau, brief >8 MiB/s then recovery, bounded allocator cache, active-block-following finite growth, shader/resource transient, and delayed recovery after occupancy disappearance. It must reject occupancy-independent monotonic growth, late positive slope, staircase accumulation, per-block growth, absolute ceiling violation, and incomplete shutdown/residual. Formal runtime is prohibited unless the synthetic report passes and matches the frozen contract SHA-256.

## Runtime progression

The order is fixed: control run01–03, C0 run01–03, then C1 run01–03. Every condition is a separate process. A condition or three-run group failure stops the population without retry; later groups do not start. A successful Phase 6FF claim is limited to one representative-startup readback and one fuel same-object alias lifetime. Repeated readback remains a future phase even after full success.

## Formal runtime safe stop

The new root executed control run01 only. Startup was representative and the process collected 97 aligned samples over 47.966 seconds, completed stage close in 2.347 seconds, reached `shutdown_complete`, and exited normally. Fatal, dump, automatic upload, CDB invocation, and cleanup residual counts were zero.

Absolute and recovery evidence remained bounded: Kit peak was 13.537 GiB with 474.570 MiB remaining to the 14 GiB limit; tree peak was 13.690 GiB; maximum transient growth was 673.191 MiB; high-water recovery was 626.703 MiB after 0.528 seconds; terminal residual was +46.488 MiB; projected and normalized projected drift were 3.209% and 0.779%.

The predeclared persistence predicate failed. The 8-second rolling slopes were `-2.496, -0.091, +21.774, +53.823, -48.703, -16.901, +3.603, +17.028, +49.266, +40.604 MiB/s`. Three late windows exceeded the diagnostic 8 MiB/s level consecutively, above the frozen maximum of two. Although the final equal-window slope was only +0.488 MiB/s and high-water recovery was material, Phase 6FF does not change the contract after runtime. Control runs 02/03 and every C0/C1 run were not started. Control reproducibility, one-readback lifetime, and repeated readback therefore remain unqualified.

Regression remained green: Release build, Phase 0 RTX, Phase 3 authority/mass-balance/Flow input, focused Phase 6E/6F contracts 271/271, and the standard suite 78/78 in 320.5 seconds. Phase 3 retained zero dry/wet mass-balance error, active blocks final/peak 271/335, and peak fuel 1.0. Production SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`; no Kit, CDB, or helper process remained.
