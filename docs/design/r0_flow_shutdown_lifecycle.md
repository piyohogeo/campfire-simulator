# Phase 6EY Flow dynamic-stationarity qualification safe stop

Phase 6EY leaves the Phase 6EX `24.382% > 15%` result unchanged. The separately frozen contract is `campfire.phase6ey.dynamic-stationarity-qualification-contract.v1`, SHA-256 `58C9755FF8F3F8E67752E558F572CB1B997A14E1976E0241B586E1DE64CA4AB4`. It removes no previous failure and admits no historical sample to the formal population.

The contract observes post-frame-320 running Flow for a fixed 24 seconds. It requires at least 40 aligned active/resource samples spanning 20 seconds, 100 outer samples, four windows with at least eight aligned samples each, and unchanged resource/lifecycle limits. Rather than constraining raw active-block range, it combines block and memory regression slopes, projected drift, half/window return ratios, both increase and decrease observations, late high-water behavior, memory response to block retirement, block-normalized memory, correlation, and high-water recovery. Deterministic fixtures accepted constant noise, periodic motion, drop/recovery, and bounded block-correlated memory, while rejecting linear and accelerating occupancy growth, memory-only growth, and non-recovering cache growth.

R0 run 1 produced 49 aligned samples across `23.981730 seconds` and 106 outer samples. Active blocks had min/mean/median/p95/max `1145 / 1364.980 / 1367 / 1528 / 1560`, slope `+2.520950 blocks/s`, projected drift `4.429%`, and increase/decrease fractions `58.333% / 41.667%`. Kit Private Bytes slope was `+3,790,730 bytes/s` (`+3.615 MiB/s`), projected drift `0.654%`, and normalized slope `-16,280.663 bytes/block/s`; final-to-initial window mean ratio was `1.016594`, and high-water recovery/plateau passed. Every frozen dynamic-stationarity check passed.

The process also completed all lifecycle markers, stage close in `2.559663 seconds`, normal OS exit, and exact cleanup. Kit/tree peaks were `14,683,439,104 / 14,846,590,976 bytes`; fatal, dump, automatic upload, device loss/TDR, CDB, and residual counts were zero. Production remained unchanged.

Immediately after that normal exit, aggregation raised `KeyError: plateau_contract`: the new analyzer passed the Phase 6EY contract to a shared Phase 6EV lifecycle parser that still derives obsolete plateau fields. The correction supplies that parser a permissive in-memory compatibility view only; Phase 6EY qualification still uses exclusively its frozen stationarity thresholds and the fixed post-frame-320 `stability_observation_sample` population. Offline analysis verifies the one completed run as bounded partial evidence. The orchestration failure remains fail-closed: run 2/3 and R1 were not started, the formal population is `0/3`, and the run was not retried. A fresh artifact root and explicit approval are required to resume. The unresolved Phase 6EU native SRW-lock owner remains a shutdown risk.

Release build, Phase 0 RTX, Phase 3, the focused Phase 6E contracts (`214/214`), and the standard suite (`78/78`, eight processes, `303.6 seconds`) passed. Phase 3 retained dry/wet mass-balance error 0, authority hashes unchanged, active blocks final/peak `262/376`, and peak fuel 1.0. Static devlog validation passed 739 references, 253 IDs, 205 JSON files, and 171 SVG files. Production app SHA-256 remained unchanged.

# Phase 6EX extended running-Flow stability observation safe stop

Phase 6EX preserves the Phase 6EW `18/20` sample safe stop as immutable history. Its new pre-runtime contract is `campfire.phase6ex.r0-stability-qualification-contract.v1`, SHA-256 `BF2D8160267C3F108952C5A92C7DB688C34C74CE29014635945A84722D66DAB2`. No Phase 6EU–6EW sample was reused. Production code/defaults, Point schema/order/revision, wood authority, Flow settings, CollisionProxy geometry, and the corrected four-log placement stayed unchanged.

Only observation duration changed. Stability begins at frame 240; after the normal frame-320 sample, Kit continues updating with timeline and Flow playing for a fixed eight seconds. The external guard remains at 0.20-second sampling. The collection target is 30 and the hard minimum remains 20. The active-block range limit remains 15%, Private Bytes slope remains at most `+8 MiB/s`, and the same 14-GiB Kit, 16-GiB unique-tree, 512-MiB runner/diagnostic, 8-GiB system-floor, lifecycle, and normal-exit gates apply. The extra window performs no readback, field conversion, NPZ persistence, or transport analysis.

The required non-Kit fixture ran for eight seconds and produced 34 valid samples. Timestamps were strictly increasing, PID/creation-time/full-path identity stayed constant, memory values were finite, the bounded seven-digit PowerShell timestamp parser agreed with its six-digit form, and no child remained. It therefore cleared the pre-Kit gate.

R0 run 1 then completed frame 320 and 122 extra Kit updates during the eight-second extension. The marker-bounded stability interval lasted `13.278606 seconds` in total and contained 48 external resource samples, exceeding both target and minimum. Kit Private Bytes had slope `+725,458.45 bytes/s` (`+0.692 MiB/s`), with 29 increases, 9 decreases, and 9 unchanged transitions, so the memory-specific plateau tests passed. Kit peak was `14,614,773,760 bytes` (`13.611069 GiB`), terminal was `13,760,348,160 bytes` (`12.815323 GiB`), tree peak was `14,778,298,368 bytes`, runner peak was `95,346,688 bytes`, and diagnostic peak was `16,850,944 bytes`; all guards remained within their frozen limits.

The longer observation exposed a different failure. Across frame 240/280/320 and the extra-window samples, active blocks ranged from `1121` to `1447`, a range fraction of `24.382%`, exceeding the frozen `15%` physical plateau gate. The extra samples show the field falling to 1121 near +6.05 seconds and recovering to 1397 near +7.53 seconds; this is not a telemetry-count defect. The run nevertheless reached every lifecycle marker, stage close completed in `1.949598 seconds`, extension shutdown in `0.007502 seconds`, OS exit was normal, and fatal/dump/automatic-upload/device-lost/TDR/CDB/cleanup-residual counts were zero.

The runner therefore stopped without retry at R0 run 1. Run 2, run 3, cross-run qualification, and R1 were not started. Formal R0 remains `0/3`. Phase 6EW remains failed for its original sample-count reason, while Phase 6EX independently fails the unchanged active-block stability gate. The observation design succeeded, but NanoVDB acquire/lifetime separation cannot proceed until a separately approved Phase explains or predefines an appropriate active-block stability window without retroactively weakening either contract. The unresolved Phase 6EU native SRW-lock owner also remains a lifecycle risk.

Release build, Phase 0 RTX, Phase 3, the Phase 6E focused contracts (`205/205`), and the standard suite (`78/78`, eight processes, `306.2 seconds`) passed. Phase 3 retained dry/wet mass-balance error 0, authority hashes `0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10` and `148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9`, active blocks final/peak `256/393`, and peak fuel 1.0. Static devlog validation passed 406 local references, 252 IDs, 204 JSON files, 170 SVG files, and 2 ZIP files. Production app SHA-256 stayed `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`, and no Kit, CDB, or `nvidia-smi` process remained.

# Phase 6EW corrected-marker R0 lifecycle qualification

## Frozen scope and runtime contract

Phase 6EW preserves the Phase 6EU unknown-shutdown evidence and the Phase 6EV marker-gate safe stop without overwriting or reclassifying either artifact. The new contract is `campfire.phase6ew.r0-lifecycle-qualification-contract.v1`, SHA-256 `1B549CE271C55CFA62BFB2E4021992658C03692CAE350E6832560ED048D10BB9`. No Phase 6EU/6EV sample is part of its formal population.

The contract fixes a corrected-marker L0 control, three independent readback-free R0 runs through frame 320, and one public `get_latest_nanovdb_readback()` acquire/discard at frame 60 that is allowed only after R0 is 3/3 normal-exit, plateau-qualified, and reproducible. Stage close is bounded at 180 seconds, based on the frozen 102.595644-second Phase 6EV observation plus 77.404356 seconds of margin. The in-process and outer bounds are 540 and 900 seconds. Resource limits remain 14 GiB Kit, 16 GiB unique tree, 512 MiB runner/diagnostic, and 8 GiB physical/commit headroom.

Production code/defaults, Point schema/order/length/revision, wood authority, Flow settings, CollisionProxy geometry, and the corrected four-log layout are unchanged. This is a diagnostic-only lifecycle order and is not a production shutdown recommendation.

## L0 result and bounded report correction

The new L0 process reached active blocks `505/688`, emitted `final_sample_complete` after the common sample loop, completed every timeline/renderer/reference/stage/extension/runner marker, and exited normally with code 0. Stage close took `2.522739 seconds`; Kit and unique-tree peaks were `13,470,588,928` and `13,635,239,936 bytes`. No cleanup was required and fatal, dump, upload, device-loss, TDR, CDB, and residual counts were zero.

The first post-process aggregation stopped because PowerShell's round-trip timestamp contained seven fractional digits (`2026-08-12T09:26:26.7250933Z`), while Python `datetime.fromisoformat()` accepts at most microseconds on this path. This occurred after Kit had exited and did not invalidate the L0 lifecycle evidence. The parser now truncates only excess fractional digits to six and has a focused fixture. A narrowly scoped resume path required the same frozen contract hash, unchanged production hash, a `running/L0_short/0-completed` state, and absence of R0/R1 directories. It re-analysed the one existing L0 process without rerunning Kit, then admitted R0 because every L0 gate passed.

## R0 run 1 and safe stop

R0 run 1 completed all ten frames `30/60/90/120/150/180/200/240/280/320`, with active blocks `505/688/894/1118/1314/1329/1251/1346/1303/1356`. It completed all lifecycle markers, stage close in `4.016914 seconds`, extension shutdown, and normal OS exit. Kit peak was `14,630,817,792 bytes` (`13.626011 GiB`), terminal Kit Private Bytes `13,806,632,960 bytes`, unique-tree peak `14,793,801,728 bytes`, runner peak `96,174,080 bytes`, and diagnostic peak `17,145,856 bytes`. Minimum available physical memory and commit headroom remained `88,234,360,832` and `107,168,890,880 bytes`; GPU 0 dedicated allocation peaked at 6,947 MiB.

The active-block range over frames 240/280/320 was `3.970037%`, below the frozen 15% limit. The fitted Private Bytes slope was `-4,469,949.9 bytes/s`, below the `+8 MiB/s` ceiling, and the series was non-monotonic. However, the same interval contained only `18` outer resource samples against the predeclared minimum `20`. The formal plateau therefore failed. The runner did not retry the condition and did not start R0 runs 2/3 or R1. A normal exit and downward memory trend are useful partial evidence, but the complete R0 population remains `0/3` qualified.

Stage-close observations in this Phase are `2.522739` and `4.016914 seconds`; this is not a three-run distribution and does not supersede the frozen 102.595644-second Phase 6EV observation. Phase 6EW did not reproduce a native residual, so CDB was never invoked. The incomplete Phase 6EU CDB capture still leaves the stage-close/plugin-shutdown SRW-lock owner unknown.

## Verification and next boundary

Release build completed in 6.98 seconds. Phase 0 RTX passed. Phase 3 passed in 25.9 seconds with dry/wet mass-balance error 0, authority hashes `0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10` / `148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9`, Flow active blocks final/peak `229/348`, and peak fuel 1.0. Focused Phase 6E contracts passed 196/196 in 25.337 seconds and the eight-process standard suite passed 78/78 in 306.6 seconds. Production app SHA-256 remains `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.

NanoVDB acquisition/lifetime separation cannot proceed from this population because R0 is not 3/3 plateau-qualified. A future Phase must define its telemetry sampling/gate before runtime and use a fresh artifact root; it must not reinterpret this 18/20 result. No visible product behavior changed, so no demo video or latest-demo update is warranted.

---

# Phase 6EV readback-free R0 shutdown lifecycle

## Scope and frozen evidence

Phase 6EV is a production-neutral lifecycle calibration. Phase 6EU remains a frozen `unknown_shutdown_failure`; its artifacts, invalid synchronous process-memory samples, partial plateau evidence, and unstarted R1–R6 conditions were not overwritten or reclassified. Production defaults, Point payload ordering/length/revision, wood authority, Flow settings, CollisionProxy geometry, and the corrected four-log layout remain unchanged.

The new pre-runtime contract is `campfire.phase6ev.r0-lifecycle-contract.v1`, SHA-256 `19FD34C5616DE4090F0EC512646F56E5069BC233C5EF35A4E9D58D28A2F26E92`. It freezes L0 short readback-free control, three independent frame-320 R0 runs, and one frame-60 acquire/discard R1 that is allowed only after R0 is 3/3 normal-exit and all plateau gates pass. Resource ceilings remain 14 GiB Kit, 16 GiB unique tree, 512 MiB runner/diagnostic, and 8 GiB physical/commit headroom.

## Phase 6EU shutdown audit

Observed facts:

- frames 240/280/320 reached active blocks `1346/1303/1356`; the run used no NanoVDB readback;
- durable markers reached `measurement_complete`, `timeline_stopping`, and `timeline_stopped`, but not stage-close completion;
- the residual identities were Kit PID 21380, conhost PID 14796, and telemetry transmitter PID 21656; outer exact-identity cleanup removed all three and verified zero remaining processes;
- Kit peak was `14,547,746,816 bytes`; there was no access violation, fatal token, dump, upload attempt, device loss, or TDR;
- the bounded CDB capture timed out after obtaining only the initial threads, so it is not a complete all-thread ownership graph;
- the main thread was waiting through `ntdll!RtlAcquireSRWLockExclusive`, `MSVCP140!mtx_do_lock`, and `omni_ext_plugin!carbOnPluginShutdown` offsets;
- the named `std::async UsdContext loader thread` was waiting through `RtlAcquireSRWLockExclusive`, `omni_usd!UsdContext::loadRenderSettingsFromStage`, and `omni_usd!UsdContext::closeStage+0x360`;
- the captured profiler thread was in `NtDelayExecution`; render, Flow, RTX/NGX, and remaining Python/native threads were not captured before the CDB timeout;
- the accepted five-token NGX signature did not match.

Strong inference: Phase 6EU most likely stopped inside the public stage-close path at a stage-close/plugin-shutdown SRW-lock boundary. This is not evidence of an access violation or of a fault in project production code. The lock owner and complete native dependency chain remain unknown because private symbols and the remaining thread stacks were unavailable.

## Diagnostic-only shutdown ordering

The Phase 6EV probe reuses the existing exact process monitor/cleanup policy and the previously exercised `omni.campfire.phasev3tg_shutdown` extension callback marker. It uses the same public timeline stop, Kit update, `UsdContext.close_stage_async()`, and post-close update primitives exercised by Phase 6DW/6EO, while adding bounded state at every boundary.

Compared with Phase 6EU, the diagnostic sequence explicitly confirms timeline stop, performs eight pre-close renderer updates, releases the acquired Flow interface and Python Emitter reference, clears volume/readback/collector references, calls `close_stage_async()`, verifies context disconnection, performs four post-close updates, requests app close, records `shutdown_complete`, observes the real extension shutdown callback, and finally records OS process exit in the parent runner. Every in-process marker uses the corrected 80-byte x64 `PROCESS_MEMORY_COUNTERS_EX` helper, includes timeline/stage/reference state, flushes, and calls `fsync`.

Phase 6DW closed the stage before its eight renderer drains; Phase 6EO stopped, updated three times, closed, updated three times, then released Flow. Phase 6EV intentionally isolates the references before close because Phase 6EU stopped at close. This remains a probe-only ordering and is not a production recommendation.

| Boundary | Phase 6EU | Phase 6DW / 6EO known-good evidence | Phase 6EV diagnostic |
| --- | --- | --- | --- |
| Timeline stop | stop + 12 updates | stop; 6EO uses 3 updates | stop request before/after + confirmed state |
| Renderer drain | 12 updates after close | 6DW 8 after close; 6EO 3 before and 3 after | 8 before close + 4 after close, every update marked |
| Stage close | before Flow release | public close completes in known-good runs | after pre-drain and Python/native interface release |
| Flow/provider refs | Flow interface after close; volume/Emitter refs implicit | 6EO Flow release after close | Flow/Emitter then volume/readback/collector refs explicitly cleared before close |
| Extension callback | not separately marked | existing Phase V3T-G marker already exercised | the same extension is reused; begin/end are fsynced |
| App/OS exit | inner 330 s absolute timeout; outer cleanup | normal exit in referenced runs | app-close, shutdown-complete, extension callback, and parent OS-exit evidence separated |
| Telemetry child | residual cleaned by outer exact identity | no residual in known-good samples | observed by the unchanged guard; L0 exited without cleanup |

## L0 result and safe stop

The fresh L0 process reached frames 30/60 with active blocks `505/688`. All synchronous memory samples were valid. Kit peak was `13,597,253,632 bytes` (`12.663429 GiB`), tree peak `13,760,684,032 bytes`, and runner peak `95,117,312 bytes`, all below the unchanged limits.

Timeline stop, eight pre-close updates, Flow/Emitter release, and volume/readback reference release completed. `close_stage_async()` then took `102.595644 seconds` but returned. The USD context became disconnected, four post-close updates completed, `shutdown_complete` was written, both extension shutdown callback markers were flushed, and the process exited normally with code 0. No CDB invocation was required, cleanup was unnecessary, and fatal/dump/upload/device-fault/residual counts were zero.

The L0 contract nevertheless failed closed because `final_sample_complete` was accidentally emitted only from the legacy full-readback branch, so readback mode `none` omitted this required marker. This was a diagnostic branch-placement defect, not a native lifecycle failure. The marker was moved after the common sample loop and covered by the focused static contract, but L0 was not rerun: the frozen no-retry rule stops this artifact root at the first gate failure.

Therefore formal R0 remains `0/3`, no plateau is qualified, R1 was not started, and NanoVDB lifetime work cannot resume yet. A new artifact root and explicit approval are required. The next run must start again at L0 with the corrected marker, then proceed to three R0 runs only if L0 passes.

## Remaining risks

- A 102.6-second stage close is bounded and exited normally once, but is not yet a stable lifecycle result.
- The release-before-close ordering may have allowed eventual progress, but one L0 run cannot establish causality.
- Phase 6EU's complete lock owner/thread dependency remains unknown.
- R0 memory plateau and all acquisition-lifetime questions remain untested.
- No production or visible behavior changed, so no demo video and no latest-demo update are warranted.

## Regression verification

The Release build, Phase 0 RTX, and Phase 3 all completed successfully. Phase 3 retained dry/wet mass-balance error 0, authoritative state hashes `0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10` and `148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9`, active blocks final/peak `246/330`, and peak fuel input 1.0. Focused Phase 6E contracts passed 187/187 in 28.807 seconds. The eight-process standard suite passed 78/78 in 346.9 seconds. Static devlog validation passed 402 local references, 250 IDs, 202 JSON, 168 SVG, and 2 ZIP files. No Kit, CDB, or `nvidia-smi` process remained, and production app SHA-256 stayed `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.
