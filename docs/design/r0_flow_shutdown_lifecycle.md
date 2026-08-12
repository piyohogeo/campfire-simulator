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
