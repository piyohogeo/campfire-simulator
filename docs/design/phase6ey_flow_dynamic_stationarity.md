# Phase 6EY Flow dynamic-stationarity qualification

Phase 6EY preserves Phase 6EX as a frozen safe stop. Phase 6EX produced 48 outer resource samples, a normal OS exit, and a bounded memory slope, but its predeclared active-block range was `24.382%` against the unchanged `15%` gate. Neither that gate nor the Phase 6EX result is reclassified.

The Phase 6EY contract is `campfire.phase6ey.dynamic-stationarity-qualification-contract.v1`. Its SHA-256 is `58C9755FF8F3F8E67752E558F572CB1B997A14E1976E0241B586E1DE64CA4AB4`. It changes only the diagnostic observation and classification method. The production app/defaults, Point schema/order/length/revision, wood authority, Flow settings, CollisionProxy geometry, corrected four-log placement, and resource ceilings remain unchanged.

## Read-only historical audit

Phase 6EU through 6EX artifacts are input only to metric design and are ineligible for the new formal population. Their aligned records preserve timeline frame, wall time, active blocks, Kit Private Bytes and Working Set, unique-tree Private Bytes, GPU dedicated memory, block and memory deltas, Private Bytes per active block, stage-close duration, and lifecycle result.

The Phase 6EX running-Flow stability interval contained 20 aligned active-block samples. Active blocks ranged from `1121` to `1447`, with 10 increases and 9 decreases. Linear slope was `-6.890 blocks/s`, Kit Private Bytes slope was `-6.186 MiB/s`, and same-sample block/private correlation was `0.189`. The sequence reached 1447, fell to 1121, then recovered to 1397. This is inconsistent with a simple one-way expansion during the observed interval; it is compatible with a sparse field whose allocated blocks grow and retire dynamically. The short interval is not reused as a Phase 6EY pass.

## Frozen engineering definition

“Dynamic stationarity” means only that Flow occupancy and memory do not diverge within a finite, frozen observation interval. It is not a proof of a physical steady state.

After the existing frame-320 sample, timeline and Flow continue for 24 seconds. Active blocks are sampled every 0.5 seconds and outer resources every 0.20 seconds. The contract requires at least 40 aligned active/resource samples spanning at least 20 seconds, at least 8 samples in each of 4 windows, and at least 100 outer resource samples. The expected counts are 48 and 120. The observation is bounded by 32 seconds; stage close remains bounded by 180 seconds, the inner process by 540 seconds, and the outer guard by 900 seconds.

The hard gate combines:

- active-block maximum `1800`, projected linear drift at most `20%`, half/window/final-window ratios, both increase and decrease observations, late high-water frequency, and consecutive-new-high limits;
- Kit Private Bytes slope at most `+8 MiB/s`, projected drift at most `5%`, normalized Private Bytes/block projected drift at most `25%`, and half-to-half Private Bytes ratio `0.95–1.05`;
- memory response when active blocks fall, plus either a `64 MiB` retreat from high water or a last-half slope no greater than `+4 MiB/s`;
- four-window distribution comparison, active-block/private-memory correlation, bounded lag correlation, and autocorrelation as reported diagnostic evidence.

The previous within-run `15%` active-block range gate is deliberately absent. The Phase 6EY checks instead reject sustained trends while permitting bounded cycles and recovery.

## Offline calibration

Eight deterministic fixtures were evaluated before runtime. Constant noise, periodic variation, recovery after a temporary drop, and bounded memory coupled to active blocks pass. Linear growth, accelerating growth, memory-only growth, and cache growth that persists after block retirement fail. Thresholds were fixed from this separation, not chosen to retroactively pass Phase 6EX.

R0 will run in three new independent processes. Each run must pass dynamic stationarity, unchanged resource limits, complete lifecycle markers, normal OS exit, and cleanup. Cross-run mean/median/p95/maximum occupancy, Kit peak/terminal memory, Private Bytes/block, memory slope, and stage-close time also have frozen reproducibility bounds. Failure stops the matrix without retry.

Only after R0 passes 3/3 may one R1 process call public `get_latest_nanovdb_readback()` once at frame 60 and immediately discard the returned references. R1 performs no NumPy conversion, scalar or spatial analysis, JSON/NPZ field persistence, directional transport, private release call, or forced garbage collection. Phase 6EY stops after R1; repeated readback and production work remain out of scope.
