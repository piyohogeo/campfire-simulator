# Phase 6FE — lag-aware Flow occupancy memory response

## Frozen history and scope

Phase 6FD remains a formal failure of its frozen same-sample contract: C1 observed `active_drop_private_increase_fraction=0.8095238095`, above `0.75`. This phase does not edit or reclassify that result. Phase 6EY and 6EX also remain historical evidence only. No historical sample is eligible for the Phase 6FE runtime population.

Phase 6FE changes only the diagnostic interpretation of the finite resource time series. Production code, defaults, the four-log stage, Point payload, Flow settings, CollisionProxy, authority state, V3, the 14 GiB Kit ceiling, and the 16 GiB unique-tree ceiling remain unchanged. Runtime is limited to three independent C0/C1 pairs. C0 performs one public readback and releases all aliases. C1 performs one public readback, one `numpy.asarray(fuel)`, and the already established ordered alias release. Repeated readback is excluded.

The machine-readable contract is `scripts/phase6fe_lagged_memory_response_contract.json`. Its SHA-256 is fixed before runtime in the adjacent `.sha256` file.

## Read-only historical audit

Phase 6EY, 6EX, and 6FD samples were aligned by timestamp across active blocks, Kit Private Bytes and Working Set, unique-tree Private Bytes, GPU dedicated memory, timeline frame, and durable marker. The normal cadence is approximately 0.5 seconds. Every material adjacent occupancy drop (at least 16 blocks) was evaluated at the same sample and at one through four following samples.

The audit showed that same-sample response is not an invariant of the known-good population. Phase 6EY contains delayed reclaim, active-field rebound during the response window, and bounded cache retention. Phase 6FD C1 contains 15 eligible drops: 2 immediate reclaims, 3 delayed reclaims, 6 rebound overlaps, 2 bounded-cache events, and 2 short continued-growth events. Its largest four-sample transient was 154.059 MiB, while the complete observation later recovered about 730 MiB and retained a negative last-half slope. This is evidence against the old one-to-one predicate, not retroactive evidence that Phase 6FD passed.

Phase 6EX has a shorter historical observation and remains failed for its own frozen evidence boundary; the new audit does not supply its missing formal population.

## Frozen engineering contract

The response window is four samples, bounded to 3.0 seconds. A material drop is at least 16 active blocks. An 8 MiB reduction identifies observable reclaim. Recovery on the first sample is `immediate_reclaim`; recovery on samples two through four is `delayed_reclaim`. If occupancy recovers at least 50% of the drop before memory can respond, the event is `active_rebound_overlap`. A non-reclaiming event within the finite transient bound is `bounded_cache_retention`. A non-rebounding event that finishes at least 64 MiB above its pre-drop value with at least three positive memory steps is `post_drop_continued_growth`.

The event layer permits at most 25% continued-growth events, no more than two overlapping continued-growth events, and no event above 192 MiB within the finite response window. These event checks do not replace global boundedness. The inherited global checks still require adequate samples and duration, bounded absolute occupancy, Private Bytes slope no greater than 8 MiB/s, projected Private Bytes drift no greater than 5%, normalized drift no greater than 25%, bounded half/window ratios, high-water recovery or plateau, and all unchanged resource/lifecycle ceilings. Only the obsolete same-sample drop predicate is excluded.

This is an engineering qualification over the observed finite interval. It is not a proof of allocator internals, and it does not claim that CPU committed memory must be returned to the OS for every occupancy decrease.

## Synthetic calibration

Before Kit runtime, fixtures must recognize immediate reclaim, two-sample delayed reclaim, and bounded cache retention as safe, while rejecting occupancy-independent monotonic growth, post-drop continued growth, and repeated accumulation. Calibration artifacts are separate from formal runtime artifacts. If those fixtures do not separate safe and leak-like patterns, runtime must not start.

## Runtime safe stop

The first artifact root stopped before Kit launch because the shared diagnostic runner's `ReportPhase` validation set did not yet contain `phase6fe`. It produced no physical or formal sample. That compatibility omission was fixed independently in `b11d217`; the root remains a frozen harness safe stop.

A second empty root then started the six-process formal order. `run01 C0` passed representative startup with active blocks `269 / 505 / 688 / 1118` at frames 1/30/60/120, exact Point/source identities, one public readback, complete lifecycle, a 2.958-second stage close, and normal OS exit. Fatal, dump, upload, CDB, and cleanup-residual counts were zero.

The lagged event layer passed: 16 eligible drops classified as 1 immediate reclaim, 2 delayed reclaims, 8 active-rebound overlaps, 2 bounded-cache retentions, and 3 short continued-growth events. The continued-growth fraction was 18.75%, the longest overlap remained within the frozen bound, and the maximum four-sample transient was 130.918 MiB. The obsolete same-sample predicate would also have passed in this C0.

Global boundedness did not pass. Kit Private Bytes slope was `9,743,456 bytes/s` (`9.292 MiB/s`) against the predeclared `8 MiB/s` maximum. Projected drift was only 1.654%, high-water recovery/plateau was true, and observation-end memory was 760,311,808 bytes below the pre-readback marker, but the hard slope gate remains authoritative. Kit peak was 14,865,702,912 bytes (13.845 GiB), leaving 166,682,624 bytes (158.961 MiB) below the unchanged 14 GiB ceiling. C1 and runs 2/3 were not started; there was no retry or threshold change.

Therefore Phase 6FE is not qualified, one fuel-alias lifetime remains unqualified, and repeated readback remains blocked. The result narrows the current failure from the old same-sample response model to run-to-run global slope variability near the fixed ceiling. A future phase would need a separately frozen longer observation or repeated independent readback-free controls to distinguish bounded transient slope from sustained growth; this phase does not make that change.

Regression remained green: Release build, Phase 0 RTX, Phase 3 authority/mass-balance/Flow input, focused Phase 6E/6F contracts 262/262, and the eight-process standard suite 78/78. Phase 3 reported zero dry/wet mass-balance error, active blocks final/peak 258/328, and peak fuel input 1.0. The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`; fatal, dump, automatic-upload, CDB, and cleanup-residual counts were zero.
