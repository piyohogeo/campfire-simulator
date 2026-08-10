# Phase V3T-J GPU transport crash-evidence isolation

## Decision

Phase V3T-J does not restore the GPU-source transport to production. The GPU ring remains a probe-owned, default-off experimental path. CPU-source remains the production/reference path, no demo preset is changed, and wood/Flow authority, Point/Sphere emitters, collision, rigid layout, checkpoint, and serialization are untouched.

Twenty-four formal Kit processes exited normally, so no Kit crash dump was produced. Combined with Phase V3T-G this is 102 selected non-reproductions, not a safety proof. The single Phase V3T-F `0xC0000005` remains unexplained and is not negated.

## Dump collection design

No ProcDump, WinDbg, cdb, or dumpchk executable was installed in the fixed environment. A machine-wide WER LocalDumps registry configuration was not used because it is broader than the isolated target and can require administrative changes.

The first custom approach launched Kit with `DEBUG_ONLY_THIS_PROCESS`. It successfully produced a full-memory dump for a tiny access-violation fixture, but it materially changed Kit behavior: RTX remained in `RtPso async compilation` waits beyond 200 seconds and the process timed out at 240 seconds. That run is invalid and excluded from every result. The external-debugger approach is retained only as rejected evidence.

The accepted collector has two probe-only native components:

1. The isolated Python probe loads `phasev3tj_crash_handler.dll` and calls one public exported install function with fixed helper, dump, and metadata paths.
2. The DLL installs a process-local `SetUnhandledExceptionFilter`. It performs no work during normal updates. For an unhandled `0xC0000005` only, it starts `phasev3tj_dump_helper.exe` and keeps the crashing thread blocked.
3. The helper calls `MiniDumpWriteDump` from outside the target process with the target PID, crashing thread ID, and remote `EXCEPTION_POINTERS`. It requests full memory, handle data, unloaded modules, full memory info, thread info, and token info.
4. Dump and crash metadata are flushed before the filter returns `EXCEPTION_CONTINUE_SEARCH`; normal Windows crash termination still occurs.

This changes no registry key or OS-wide setting and does not require administrator rights. The filter is installed only inside the isolated probe process. It is not linked into or loaded by a production app without the probe.

The target or a later-loaded component could replace the top-level exception filter after the durable installation marker. Therefore “armed” is an observed installation event, not a guarantee that all future native failures will reach this handler.

## Collector proof

The dedicated fixture loads the same DLL/helper pair and performs an actual null-pointer write. The fixture exited with `0xC0000005`; the helper generated:

- Path: `C:\Users\junic\src\campfire-simulator\artifacts\phasev3tj-dump-smoke-handler2\fixture_access_violation_full.dmp`
- Size: `11,374,239 bytes`
- SHA-256: `f86026adcc5749a298f4cf418ac7a6bb37fe9a461ffc00e9d77d1e902156d07b`
- Minidump signature: `MDMP`
- `Memory64ListStream` present: yes
- Git-managed: no

The dump itself remains under ignored `artifacts/` and is not committed or pushed. The committed report contains only its local path, size, hash, stream validation, and collector metadata.

## GPU transport lifecycle matrix

Fixed conditions are Kit 110.2, Flow 110.0.0, `omni.hydra.rtx` 1.0.4, RTX 3090 / driver 591.86, 20 logs, 1280x720, one 120x60 RGBA8 base atlas plus one emission atlas, three permanent Warp source slots per texture, and Flow+RTX enabled. Production V3 remains OFF.

| Transport / scenario | Runs | Normal exit | Access violation | Ordered teardown |
|---|---:|---:|---:|---:|
| CPU reference / normal | 3 | 3 | 0 | 3 |
| GPU ring3 / normal | 3 | 3 | 0 | 3 |
| GPU ring3 / timeline STOP/restart | 3 | 3 | 0 | 3 |
| GPU ring3 / stage replacement | 3 | 3 | 0 | 3 |
| GPU ring3 / Provider regeneration | 3 | 3 | 0 | 3 |
| GPU ring3 / explicit extension disable | 3 | 3 | 0 | 3 |
| injected GPU initialization failure / CPU fallback | 3 | 3 | 0 | 3 |
| injected pre-setter publication failure / CPU fallback | 3 | 3 | 0 | 3 |

Each process retains durable markers for crash-handler installation, last publication revision/slot, publication gate close, teardown publication rejection, timeline stop, source-generation synchronization, stage close, Provider destruction, GPU allocation release, extension disable, and normal quit. Every formal process reached `normal_quit_posted` in the required order. Stage-ID, CUDA illegal address, device lost, and invalid-pointer log counts were zero.

The initialization-failure and publication-failure conditions each recorded exactly one CPU fallback. The publication failure is injected before either Provider setter, so fallback begins at the next complete base+emission boundary. The faulted GPU path does not reuse its pointer. This is probe behavior and does not add a production setting or transport.

## Evidence classification

Observed:

- The process-local handler/helper pair can write and validate a real full-memory `0xC0000005` dump without registry changes.
- All 24 formal Kit processes exited normally with the lifecycle ordering above and produced no dump.
- Phase V3T-G (78) plus Phase V3T-J formal (24) now provides 102 selected non-reproductions.

Strong inference:

- The accepted handler adds negligible steady-state work compared with the rejected debugger-attached path because it is dormant until the unhandled filter runs.
- The selected stage/Provider/timeline/fallback/teardown sequences do not readily reproduce the Phase V3T-F shutdown failure in this fixed environment.

Unconfirmed:

- The Phase V3T-F faulting module, offset, thread, native stack, and root cause. There is no new Kit crash to analyze.
- DynamicTextureProvider source-consumed fence and safe GPU pointer reuse lifetime. No public contract was found, and non-reproduction cannot replace one.
- WinDbg symbol quality. WinDbg/cdb are absent; because no Kit dump was generated, no installation or administrator request was made. If a real dump is captured, symbol-limited analysis is the next action before another adoption decision.

## Reproduction

```powershell
.\scripts\run_phasev3tj_dump_smoke.ps1
.\scripts\run_phasev3tj_gpu_revalidation.ps1 -Runs 3 -Warmup 6 -Updates 30
```

The formal raw markers/process records, aggregate report, and SVG are stored under `docs/devlog/assets/phasev3tj/`. The local full dump remains in ignored `artifacts/`.

## Final regression

The final release build passed with build ID `0.1.0+master.0.06e9537a.local`. Phase 0 produced the fixed 1280x720 RTX frame successfully. The standard suite passed 8/8 processes and 77/77 tests in 341.7 seconds, including 190.0 seconds of collapse coverage.

The six-process Phase V3T-C OFF/ON matrix preserved identical dry and wet authority SHA-256 values in every run, reported zero mass-balance error for both logs, and produced positive Flow active-block peaks from 136 through 318. Its logs contained zero stage-ID errors. The Phase V3T-J shutdown gate remained 24/24 ordered teardowns with zero access violation, CUDA illegal-address, device-lost, invalid-pointer, or stage-ID marker. The machine-readable record is `docs/devlog/assets/phasev3tj/regression_report.json`.
