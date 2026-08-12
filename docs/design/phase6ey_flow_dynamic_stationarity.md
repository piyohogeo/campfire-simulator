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

## Runtime result and safe stop

R0 run 1 completed 49 aligned post-frame-320 samples over `23.981730 seconds` and 106 outer resource samples. Active blocks had min/mean/median/p95/max `1145 / 1364.980 / 1367 / 1528 / 1560`, slope `+2.520950 blocks/s`, projected drift `4.429%`, increase/decrease fractions `58.333% / 41.667%`, and final/initial window mean ratio `1.016594`. Kit Private Bytes slope was `+3,790,730 bytes/s` (`+3.615 MiB/s`), projected drift `0.654%`, and Private Bytes/block slope was negative. All frozen dynamic-stationarity checks passed.

Stage close completed in `2.559663 seconds`; OS exit was normal. Kit and unique-tree peaks were `14,683,439,104` and `14,846,590,976 bytes`. Runner and diagnostic peaks were `95,346,688` and `16,908,288 bytes`. Fatal, dump, automatic upload, device loss/TDR, CDB, and cleanup residual counts were zero. Production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.

The first post-process analyzer stopped after Kit exit with `KeyError: plateau_contract`. The shared lifecycle parser still derives obsolete Phase 6EV plateau fields, while the new contract intentionally has no old active-range section. The fix provides a permissive in-memory compatibility view to that old parser only. It also makes explicit that the four Phase 6EY windows use the fixed post-frame-320 `stability_observation_sample` records, rather than sparsely mixing frame 240/280/320 anchors into equal-time windows. Neither change modifies the frozen contract or thresholds.

Offline re-analysis verifies run 1 as valid bounded partial evidence, but the orchestration failure is fail-closed. Run 2/3 and R1 were not started, no condition was retried, and formal R0 remains `0/3`. Phase 6EY therefore ends at a diagnostic post-processing safe stop. A new artifact root and explicit approval are required before the frozen matrix can be rerun. The unresolved Phase 6EU native SRW-lock owner remains a shutdown risk.

Release build, Phase 0 RTX, Phase 3, 214 focused Phase 6E contracts, and the standard suite passed. The standard suite completed `78/78` tests in eight processes and `303.6 seconds`. Phase 3 retained dry/wet mass-balance error 0, authority hashes `0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10` and `148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9`, active blocks final/peak `262/376`, and peak fuel 1.0. Static devlog validation found 739 local references, 253 IDs, 205 JSON files, and 171 SVG files with no missing reference or duplicate ID.
