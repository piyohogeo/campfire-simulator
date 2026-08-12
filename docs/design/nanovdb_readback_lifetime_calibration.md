# Phase 6EU NanoVDB public readback lifetime calibration safe stop

## Scope and frozen history

Phase 6EU creates a new production-neutral contract for separating public NanoVDB acquisition, Python/native lifetime, fuel conversion, scalar aggregation, bounded JSONL persistence, and minimum spatial sampling. Phase 6ES and Phase 6ET remain immutable resource safe stops; no artifact, 14 GiB result, classification, or unfinished matrix was reused or reclassified. Production code/defaults, Point schema/order/length/revision, wood authority, Flow settings, CollisionProxy geometry, and the corrected four-log placement are unchanged.

The frozen contract is `campfire.phase6eu.nanovdb-readback-lifetime-contract.v1`, SHA-256 `206E1051BA05327AA996E461B250C0B0D23A26BF7F89CB764E8AD30694FADA2C`. It defines R0 through R6 as staged groups and preserves the 14 GiB Kit, 16 GiB unique-tree, 512 MiB runner/diagnostic, and 8 GiB system-headroom limits. R0 must complete three normal-exit plateau runs before any acquisition condition starts. Later groups similarly fail closed. The 93.33%/100% supply comparison and video are outside this contract.

## Implemented boundaries

The shared default-preserving probe now supports these explicit diagnostic-only modes:

- `none`: no `get_latest_nanovdb_readback()` call.
- `acquire_discard`: acquire the public tuple, record bounded type/identity metadata, and retain no channel field.
- `fuel_convert`: add only `np.asarray()` of the fuel object and record dtype, shape, strides, ownership, `.base`, and sharing metadata.
- `fuel_scalar`: add fixed sum/mean/min/max without retaining the field.
- `fuel_jsonl`: persist one record below 16 KiB per frame.
- `fuel_spatial`: add only the frozen representative-Collider ROI through the existing public save/read path.

No inferred/private release method is called. The returned object exposes no validated public release contract, so only natural scope end, explicit Python `del`, and optional diagnostic `gc.collect()` are modeled; the latter two are not production proposals. `tracemalloc` records Python-tracked allocations while explicitly not claiming native, GPU, or Flow coverage. Fine-grained markers pair the public call, tuple audit, conversion, aggregation, reference release, next frame, JSONL write, timeline stop, renderer drain, and shutdown with a synchronous process-memory snapshot. No GPU global synchronization is introduced.

## Executed population and safe stop

A fresh artifact root completed the warm-up normally, then started only `baseline/run01/R0_none`. No NanoVDB readback was called. The Flow run reached all ten frozen frames through frame 320, with active blocks `505, 688, 894, 1118, 1314, 1329, 1251, 1346, 1303, 1356`. Kit peak was `14,547,746,816 bytes` (`13.548645 GiB`), below the unchanged `15,032,385,536-byte` Kit ceiling. Unique-tree peak was `14,710,587,392 bytes`; minimum available physical memory and commit headroom remained `83,286,867,968` and `101,963,591,680 bytes`.

The probe completed its samples and wrote `measurement_complete`, but did not reach `timeline_stopped`, stage close, renderer drain, or `shutdown_complete` in the durable result. The 330-second inner lifecycle monitor reached absolute timeout. CDB produced a bounded all-thread/module stack, but the accepted five-token NGX signature did not match; diagnostic capture therefore remained fail closed. The outer guard found exact surviving identities for Kit, its conhost, and the telemetry transmitter, stopped only those PIDs, and verified zero residual. There was no fatal token, crash dump, automatic-upload attempt, device loss, or TDR. The lifecycle classification is `unknown_shutdown_failure`, not a known external residual and not a normal exit.

Only one of 27 formal processes was attempted and zero entered the accepted population. R0 runs 2/3 and R1-R6 were not started and the failed condition was not retried.

## Partial resource evidence

The frozen stability frames 240/280/320 had active blocks `1346/1303/1356`, a 3.970% range relative to their mean. Nearest outer-guard Kit samples were `14,256,705,536`, `13,902,397,440`, and `13,818,634,240 bytes`, decreasing twice with an indicative slope of about `-80.1 MB/s`. This suggests neither monotonic per-frame growth nor an increasing high-water in that short interval. It is not a formal plateau: only 16 outer resource samples fell in the interval, below the frozen minimum of 20, and normal OS exit was absent.

The run also exposed a separate instrumentation defect: the initial in-process `GetProcessMemoryInfo` call lacked explicit Windows `argtypes`/`restype` declarations and returned `error 0`. The safe-stop run was not retried. A small non-Kit fixture then verified a corrected, isolated `PROCESS_MEMORY_COUNTERS_EX` helper: the x64 structure is 80 bytes and returns finite Private Bytes/Working Set. The analyzer preserves the invalid synchronous samples and uses nearest outer-guard samples only as labeled partial evidence.

## Classification and restart boundary

Observed:

- readback-free four-log Flow remains a high-memory condition near, but below, the 14 GiB limit;
- active blocks and nearest-guard Private Bytes were stable/decreasing across the declared late frames;
- the longer frame-320 path did not complete stage close/shutdown in this run;
- exact cleanup succeeded and no crash/dump/upload/device fault occurred.

Strong inference:

- the Phase 6ET first-readback result cannot yet be separated from acquisition lifetime because Phase 6EU never reached R1;
- JSON/NPZ, NumPy conversion, scalar aggregation, and spatial sampling cannot have caused this Phase 6EU stop because none ran.

Unconfirmed:

- whether the shutdown residual is related to the longer Flow lifetime, instrumentation overhead, RTX/Flow teardown timing, or another native wait;
- whether one acquire is bounded, repeated acquisition accumulates resources, conversion copies the field, or persistence adds measurable memory.

The 14 GiB limit is not raised. R1-R6, GC follow-ups, 93.33%/100%, video, and production integration remain blocked. A restart requires explicit approval and a new artifact root. It must begin again at R0 because this population lacks three normal exits, while retaining the corrected process-memory fixture and the same frozen contract unless a separately reviewed lifecycle contract supersedes it.

## Regression verification

The Release build completed in 7.80 seconds. Phase 0 RTX and Phase 3 completed with exit code 0; Phase 3 retained dry/wet mass-balance error 0, the established authority SHA-256 values, Flow active blocks final/peak 264/352, and peak fuel input 1.0. The complete Phase 6E focused set passed 181/181 in 29.212 seconds. The standard eight-process suite passed 78/78 in 334.3 seconds. Static devlog validation passed 399 references, 201 JSON files, 167 SVG files, and 2 ZIP files. Production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.
