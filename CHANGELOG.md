# Changelog

- Safely stopped the first Phase 6EC restart root after condition A completed four public readback samples and `shutdown_complete`: its inline case-runner PowerShell grew beyond 7 GiB while post-shutdown evidence remained incomplete. Conditions B/C were not started, no dump was created, and the exact runner PID was stopped after path/start-time verification.
- Isolated every Phase 6EC formal and visual case runner behind the existing Phase 6EA guarded-helper boundary with direct stdout/stderr files, a 720-second timeout, a 512 MiB Private Bytes limit, and process-tree cleanup. The Phase 6ED exception policy and production paths remain unchanged; the invalid root is retained and will not be reused.

- Corrected the Phase 6EB Windows-exception evidence boundary in production-neutral Phase 6ED. Log scanning now uses line-streamed explicit exception/exit/access-violation context instead of treating every bare `0xC........` value as a crash.
- Added hardware/value negative fixtures and explicit exception positive fixtures, preserving the original 24 Phase 6EB contracts while expanding the policy suite to 31/31. Missing or unreadable logs remain fail-closed without inventing a fault module or offset.
- Reclassified the saved Phase 6EC axis-control log read-only in a new artifact root: the RTX 2070 `Sub System Id : 0xC75C1462` is not an exception, all 13 correction gates passed, and the existing run evaluates as functional pass, normal exit, and performance-eligible. Original artifacts, production defaults, and Phase 6EC execution remain unchanged.
- Reconfirmed Phase 6EA resource safety 7/7 and static contracts 6/6, the expanded Phase 6EB policy 31/31, and the standard suite across eight processes with 78/78 tests in 308.5 seconds. Devlog validation found 369 local references, 182 JSON files and 148 SVG files with no missing, malformed, replacement-character, or duplicate-ID failures; production app SHA-256 and the latest-demo pointer remain unchanged.

- Added the production-neutral Phase 6EC static-rotation runner around the exact Phase 6DY Cylinder Mesh CollisionProxy. Offline Y40 preparation passed 14/14 gates with unchanged topology/schema, center-preserving unit transform, and a 0.111532 m (2.2306 velocity-cell) emitter clearance.
- Safely stopped at the first axis-aligned control. The public Flow probe reached `shutdown_complete`, active blocks 26, fuel 0.8 and OS exit 0 with no residual/fatal/dump/upload, but the unchanged Phase 6EB exception matcher classified the GPU inventory value `Sub System Id : 0xC75C1462` as exception-shaped evidence and therefore returned `unknown_shutdown_failure`.
- Did not retry condition A or start rotated ON/OFF and visual-evidence processes. Recorded the false-positive boundary without changing Phase 6EA/6EB policy, production code/defaults, the production app SHA-256, or the latest-demo pointer.
- Passed Phase 6EC 7/7, Phase 6EA 7/7 and 6/6, Phase 6EB 24/24, Release build (6.94 s), Phase 0 RTX, Phase 3 authority/mass balance, and the eight-process standard suite (78/78, 303.1 s). Devlog static validation found 341 local references, 181 JSON files and 147 SVG files with no missing, malformed, replacement-character, or duplicate-ID failures.

- Added the Phase 6EB known-NGX shutdown policy: a maximum 60-second post-`shutdown_requested` grace, non-invasive bounded CDB stack fingerprinting, repeated full-dump avoidance, verified PID/path/start-time identity, and fail-closed handling for any unknown non-exit.
- Split every covered Kit result into functional, lifecycle, and performance-acceptance axes. A fully completed run with the exact NGX telemetry signature may pass functionally, but is not a normal exit and is excluded from shutdown timing and performance populations.
- Reused the Phase 6EA atomic capture lock and guarded helper for CDB, with 45-second timeout, 512 MiB private-memory ceiling, direct file redirection, and streamed token matching. Diagnostic failure never authorizes target-Kit termination.
- Added positive known-residual, negative unknown-residual, exception/dump/timeout/corrupt-input, lifecycle, and mixed-aggregate contracts. All 24 targeted tests passed; the final real `kit_only` smoke exited normally in 1.423 seconds and production app SHA-256 remained `94162F82...F02A`.
- Reconfirmed Phase 6EA resource safety 7/7, its static contract 6/6, and all eight standard test processes with 78/78 tests in 302.2 seconds. Devlog validation found 338 unique local references, 180 JSON files, and 146 SVG files with no missing, malformed, or replacement-character failures.
- Recorded the historical baseline as 22 normal exits in 24 controlled processes, one signature-confirmed residual, and one pre-policy residual that is deliberately not relabeled. Production code/defaults and the latest demo remain unchanged.

- Symbolized the preserved Phase 6EA full dump with WinDbg/CDB and Microsoft public symbols without rerunning condition A. The Kit main thread waits on thread handle `0x1D4C`, targeting NVIDIA telemetry worker `0x1A60`, during `gpu.foundation` -> Direct3D -> NGX D3D12 shutdown -> telemetry uninitialization.
- Located the target worker in `NvTelemetryBridge64` `WaitNamedPipeW` on a GUID-named local pipe. D3D12 background threads were idle, and the all-thread stacks showed no main-chain GPU fence, DLL unload, or held-critical-section boundary.
- Kept raw debugger logs, symbols, and the 5.95 GB dump outside Git. The upstream pipe/service/NGX ordering trigger remains unconfirmed, so Phase 6DU and rotation remain paused; production code/defaults and the latest demo are unchanged.
- Passed the expanded Phase 6EA contract 6/6 and all eight standard test processes with 78/78 tests in 354.2 seconds; static devlog validation found 336 local references, 179 JSON files, and 145 SVG files with no missing or malformed assets.

- Added the production-neutral Phase 6EA shutdown-residual diagnosis and reproduced the non-exiting Kit process with the exact Phase 6DY qualified stage after OpenUSD, Hydra, viewport, stage close, renderer drain, and `shutdown_requested` all completed.
- Proved that the Phase 6DY and regenerated Phase 6DZ axis stages differ only in generated documentation; geometry, topology, schema, approximation, transforms, relationships, and Prim order are equal.
- Narrowed the last common shutdown boundary to `Shutting down plugin gpu.foundation.plugin`; the prior successful run continued with `PerfMonitorManager::stop`, while the hang stopped there.
- Preserved a Git-ignored 5.95 GB full hang dump (133 threads, 438 modules, no ExceptionStream; 132 captured instruction pointers in `ntdll.dll`) and recorded the lack of a symbolized unwind or durable WCT result instead of claiming a root function.
- Stopped conditions B/C, the 3-run stability check, and all rotation work after condition A hung. Production code/defaults and the latest-demo pointer remain unchanged.
- Passed the Release build in 9.41 seconds, lifecycle 6/6, rotation/ROI 5/5, Phase 6EA diagnostics 5/5, and all eight standard processes with 78/78 tests in 380.1 seconds; static devlog validation found 333 local references with zero missing or malformed JSON/SVG assets.

- Prepared Phase 6DZ's seven rotation-isolation stages from the qualified Phase 6DY Cylinder. All retain the same local geometry SHA-256, schemas, `convexDecomposition`, unit scale, and pivot; start/end controls are byte-identical and cylindrical `convexHull` remains excluded.
- Stopped Phase 6DZ on the unchanged axis-aligned entry control: it reached OpenUSD, USD context, Hydra, first viewport frame, stage close, renderer drain, and `shutdown_requested`, but the Kit process did not reach normal OS exit within 420.092 seconds. No rotated or Flow-readback condition was started.
- Recorded fatal/dump/upload/device-lost/TDR 0, RTX 3090/CUDA 0, and unchanged production app SHA-256. The isolated remaining Kit process was path-verified and terminated; Phases B–G remain held pending a normal control exit.
- Passed the Release build in `6.86 s`, Phase 6DY lifecycle contract `6 / 6`, Phase 6DZ rotation contract `5 / 5`, the focused Flow collider test `1 / 1`, and all eight standard processes with `78 / 78` tests in `293.4 s`. Devlog static validation found 332 unique references with zero missing, JSON, SVG, or replacement-character failures.

- Reused the unchanged Phase 6DW runner/probe directly for Phase 6DY and qualified the five-process A-E Box-to-Cylinder matrix through pure OpenUSD, USD context, Hydra, first viewport frame, ordered close/drain, plugin shutdown, and normal OS exit.
- Isolated Box `convexHull` as an approximation-only change and a closed 12-segment Cylinder `convexDecomposition` as a topology-only change. Both opened and exited normally; the historically failed cylindrical Hull condition remained excluded.
- Completed three public NanoVDB readback controls around the Cylinder. The cylinder-contained core had zero temperature, fuel, burn, smoke, and velocity at frames 60/120/180/200; nonzero values in the wider Box ROI are consistent with lateral bypass, while a small above-cylinder residual remains.
- Recorded 8/8 normal processes, fatal/dump/upload/timeout 0, identical Box before/after time series, RTX 3090/CUDA 0, and unchanged production SHA-256. Production code, app composition, defaults, and the latest-demo pointer remain unchanged.
- Passed the Release build in `6.80 s`, the six-test lifecycle contract, the focused Flow collider contract `1 / 1` in `0.073 s`, and all eight standard processes with `78 / 78` tests in `305.9 s`.
- Passed static devlog validation with 330 unique local references, zero missing references, zero JSON/SVG failures, and zero UTF-8 replacement characters.

- Added the production-neutral Phase 6DX stage-open safe preflight and limited its executable matrix to the known-good Box, a Box approximation-only change, and a Cylinder-topology-only change; the previously failed cylindrical Hull branch was not runnable.
- Stopped on the first known-good Box control after a bounded 420.474-second timeout at `renderer_readiness_warmup_started`, before stage preparation, OpenUSD open, USD-context connection, Hydra attachment, or any Box-to-Cylinder ablation.
- Classified the newly added no-window pre-stage viewport-frame wait as an invalid harness boundary relative to the qualified Phase 6DW ordering. No crash, dump, upload attempt, production hash change, or topology result occurred, and Phase 6DU remains paused.
- Passed the Release build in `6.79 s`, the standard suite in 8 processes with `78 / 78` tests in `304.5 s`, and the JSON/SVG/HTML static checks. Browser rendering was unavailable; Phase 0 RTX was not rerun because production code and app composition were unchanged and the diagnostic matrix had safely stopped at its control.

- Added the production-neutral Phase 6DW GPU/renderer lifecycle baseline after the RTX 2070 installation: Windows and Kit consistently enumerate RTX 3090 as GPU/CUDA index 0 and RTX 2070 as index 1, while Kit renders and presents on the RTX 3090 path.
- Qualified all seven lifecycle boundaries with both the existing and a new empty isolated cache (14/14 normal OS exits, fatal/crash/dump/upload 0), including the Phase 6DT known-good Box through first RTX frame and the known-good Flow simulation through shutdown.
- Established that Phase 6DT, 6DU, and 6DV artifacts all postdate the GPU change and reboot; the hardware change remains historically unqualified, but a generic current two-GPU or stale-cache teardown failure was not reproduced.
- Reopened Phase 6DU only for a future independent, staged Box-to-Cylinder ablation. The failed cylindrical `mesh_hull` condition was not rerun, production defaults and app SHA-256 remain unchanged, and no new demo was needed for this internal diagnostic phase.
- Added production-neutral Phase 6DV read-only MINIDUMP analysis and classified the preserved Phase 6DT/6DU stage-open crashes as the same `0xC0000005` read of `0x20` at `omni.fabric.plugin.dll+0xD6960`; matching debugger symbols were unavailable, so function-level attribution remains unqualified.
- Reopened the Phase 6DT known-good Box through pure OpenUSD in the Phase 6DU-equivalent isolated launcher, but stopped before Hydra ablation because two controls reached probe/plugin shutdown yet failed to produce a normal OS process exit, including one with an eight-frame renderer-readiness prelude.
- Preserved the no-retry boundary: the failed Phase 6DU Cylinder condition was not rerun, no new dump or automatic upload occurred, the production app hash remained unchanged, and Cylinder Flow collision remains unqualified.
- Added a staged Box-to-Cylinder ablation runner and fine-grained OpenUSD/context/Hydra/viewport lifecycle markers for a future restart, while holding Phase 6DU until a known-good Box completes the same harness with a normal exit.
- Passed the Release build in `6.01 s`, the focused Flow-scene collider contract `1 / 1` in `0.073 s`, and static devlog JSON/SVG/HTML checks; browser rendering remained unavailable because no browser binding was connected.

- Added the production-neutral Phase 6DU static cylindrical Mesh proxy probe with a 12-segment, closed-manifold `0.16 m × 1.8 m` cylinder, local-cylinder ROIs, stage-before-connect authoring, public readback path, and crash-safe isolated runner.
- Passed every offline geometry gate (`26` vertices, `36` faces, finite, outward winding, no degenerate/open edges), exact analytic/render/proxy transform parity, and a `0.190 m` emitter surface gap before the first runtime preflight.
- Stopped the first `convexHull` preflight at a native stage-open `0xC0000005` in the Fabric/Hydra/RTX boundary, preserved the 1,516,001-byte dump outside Git, detected zero upload attempts, and did not retry or continue to rotation/coexistence conditions.
- Recorded Phase 6DU as unresolved rather than treating the crash as a failed occlusion result. Production code/defaults and the latest-demo pointer remain unchanged; dynamic transforms and Phase 6DR integration are not ready.
- Passed the Release build in `6.78 s` and the focused Flow-scene collider contract `1 / 1` in `0.093 s`; Phase 0 RTX and the full suite were not rerun because production code and app composition were unchanged.

- Reproduced automatic PhysX-to-Flow collision with the bundled Flow 110.0.0 `PhysicsCollision.usda`: official Collision ON reduced temperature mean to `0.167659 / 0.003147 / 0` of OFF in the collider-core / above / far-above ROIs, and the rendered comparison showed matching occlusion.
- Isolated the Phase 6DS missing boundary to collision representation. Adding the official schema bundle to a Cube changed nothing, while an equivalent Mesh with `PhysicsCollisionAPI`, `PhysicsMeshCollisionAPI`, and a convex approximation reduced core/above/far scalar channels to zero across three independent runs. The official auxiliary PhysX schemas, layer 2, `forceSimulate=false`, and app composition were not required.
- Recorded one excluded `0xC0000005` startup crash during the incomplete Mesh-schema ablation without retrying or attributing causality; its dump remains local, automatic upload attempts were zero, and all 19 formal processes shut down cleanly with unchanged production hashes.
- Added the Phase 6DT runner, public NanoVDB samples, normalized difference report, SVG, official OFF/ON diagnostic video, design note, and devlog card. Production code/defaults and the latest-demo pointer remain unchanged; a static Cylinder mesh-proxy qualification is proposed as the next independent collision Phase.
- Passed the Release build in `7.25 s` and the focused Flow-scene collider contract `1 / 1` in `0.078 s`; Phase 0 RTX and the full standard suite were not rerun because no shared production code or app composition changed.

- Added the production-neutral, default-off Phase 6DS static Flow-collision probe with a complete offline-authored Flow 110.0.0 graph, public NanoVDB ROI sampling, and four conditions across 12 isolated Kit processes.
- Measured the effective velocity cell at `0.050000 m`; the `0.25 m` Box was five velocity cells thick and the Emitter-to-Box gap was 4.5 cells. Aligned Collision ON retained inside-core / above-far OFF ratios of `1.008 / 1.001` for temperature, `1.001 / 1.011` for smoke, `1.004 / 0.996` for burn, and `0.996 / 1.000` for velocity magnitude.
- Found no monotonic 0.5/1-cell position response; their aggregate ROI values were identical. Numeric readback and OFF/ON rendered captures both show continued passage, so Cylinder and dynamic-collider work were not started.
- Preserved Phase V3T-R and V3T-M safe stops and every production default. All 12 processes completed safe shutdown with fatal/crash/dump/upload counts zero and unchanged production app hashes; the Release build succeeded in `8.75 s`, and a diagnostic comparison video was added without changing the latest-demo pointer.

- Measured a production-neutral Phase V3T-R debug split candidate: debugger-free normal reached `50.231 FPS`, explicit developer `30.525 FPS`, and benchmark `50.488 FPS` across nine order-rotated processes while V3, Flow, authority hashes, and zero mass error were retained.
- Verified that normal/benchmark loaded none of the nine developer extensions and opened no debugpy listener, while the explicit developer candidate loaded all nine and listened only on `127.0.0.1:3000`. Separate visible-window runs reproduced the performance classes.
- Withheld the production dependency change after a non-formal explicit V3-OFF regression crashed during Kit quick shutdown (`0xC0000005`, `usd_usdGeom.dll+0x7A171`). The local dump was preserved outside Git, automatic upload remained zero, and the same condition was not automatically rerun.
- Added reproducible derived-app measurement/collection/report tooling and Phase V3T-R design/devlog evidence. No new video was created because the candidate has no intended visual difference; the verified V3T-P latest demo remains current.

- Isolated Phase V3T-Q's normal/benchmark FPS boundary with four derived-app conditions across 12 order-rotated processes: developer-bundle conditions measured `32.211 / 31.998 FPS`, while no-developer conditions measured `55.427 / 56.241 FPS`; production app hashes and defaults were unchanged.
- Reduced the bundle result to `omni.kit.debug.python` starting `debugpy.listen()`: the Python debug extension with listen disabled retained `56.010 FPS`, while default listen measured `30.832 FPS`; debug settings and developer window groups stayed in the fast class.
- Audited effective scheduler values before PLAY, after PLAY, after warmup, and before pause. No condition-specific 30 Hz setting exists; the common simulation minimum is 30 Hz, and all formal conditions use the same main/render/present/tick/VSync contract.
- Added p99 to deterministic timing summaries, reproducible derived-app/focused runners, full extension/startup evidence, a visible-window confirmation, a machine-readable report, and the Phase V3T-Q devlog card. No new video was produced because this diagnostic has no intended visual change; the verified V3T-P latest demo remains current.
- Qualified the Phase V3T-Q safe stop with a Release build, Phase 0 RTX, production normal and benchmark Phase 3 runs, matching authority hashes, zero mass-balance error, no fatal/dump evidence, and all 78 standard tests across eight processes.

- Promoted CPU-source Wood Visual V3 to the normal and production-benchmark app defaults after 14/14 production gates, identical OFF/ON authority hashes, mass error 0, and 17/17 real-Kit lifecycle gates.
- Packaged the qualified native wood producer with the extension; explicit native paths still override it and missing production binaries fail closed.
- Kept legacy, Point, rigid-layout, and isolation paths explicitly V3 OFF; V0 remains an exclusive fallback/diagnostic mode.
- Measured 20-log visible FPS at 47.054 OFF versus 45.784 ON, normal-app default at 30.528 FPS, and aggregate CPU publication total p95 at 10.175 ms with no 30 ms tail events.
- Added a production-default burn demo, machine-readable samples/report, lifecycle crash safety, and reusable V3T-P promotion runners. GPU texture transport and held Phase V3T-M Flow topology remain unchanged.

- Added a reusable latest-change demo workflow with phase-owned scenario runners, a shared Candidate Performance encode/safety/manifest boundary, and explicit post-playback promotion. Phase 6DR supplies the first before/after capture scenario; no latest pointer is replaced until the encoded candidate is actually played and accepted.
- Published the first verified latest demo as the phase-owned 11.5-second Phase 6DR rigid-lifecycle video. Its 15/15 Kit run produced 89/90 unique source frames with no fatal token, native crash dump, or automatic upload attempt; browser playback reached the end before the latest manifest was promoted.
- Requalified the Release build in 8.49 seconds, Phase 0 RTX with exit 0, and all eight standard processes with 77/77 tests in 355.5 seconds. The latest and Phase-owned modal buttons, an existing video button, all 309 local devlog references, and Japanese text rendering were checked after publication.

- Qualified Phase 6DR's default-off normal-app rigid lifecycle with 15/15 real-Kit gates: a 37-degree frame was authored before stage connection, a stopped 53-degree transform plus translation committed layout revision 2 once, an unchanged refresh skipped publication, and stage replacement recovered without a pending revision. Final Resident revision was 710 across all three consumers, Point resyncs were zero, Flow peaked at 291 active blocks, all 60 captured frames were unique, and the isolated run had zero crash, dump, or upload attempt.
- Requalified the release build in 8.20 seconds, Phase 0 RTX in 22.3 seconds, all eight standard processes and 77/77 tests in 354.7 seconds, Phase 2 collision in 34.6 seconds, Phase 6DQ at 11/11 gates, and the Candidate Performance V3/Flow scenario at Resident revision 1200 with zero mass-balance error, active-block final/peak 259/355, and zero V3 failure.

- Qualified Phase V3T-O's production-neutral 240 Hz diagnostic: twelve formal processes raised static scenes from the production ~116.7 FPS ceiling to 166.4-169.9 FPS at 97.6-99.0% GPU, while production-equivalent Flow moved only from 47.858 to 50.696 FPS. All formal runs had zero fatal token, dump, and upload attempt; production rates and defaults remain unchanged.

- Adopted the Phase V3T-N project frame-budget policy without rewriting historical gates: Candidate Performance remains temporary standard, 45 FPS / 22.222 ms is the normal target, 30 FPS / 33.333 ms is the minimum, and 60 FPS / 16.667 ms is a light-scene ideal. The existing 47.858 FPS / 20.90 ms Flow-volume reference leaves estimated average-visible-counter margins of 1.322 ms and 12.433 ms respectively.

- Phase V3T-M reached a production-neutral partial safe stop: 33 qualified processes measured the Candidate Performance timeline/PhysX boundary, Flow-absent stage boundary, and an AutoBaseline reference, while repeated Flow stage-connection crashes were fail-fast isolated as `0xC0000005` reads at `omni.fabric.plugin.dll+0xD6960`. Sensitive dumps remain local and upload-disabled; no production setting was changed.

- Adopted Phase V3T-L Candidate Performance as the temporary rendering standard for normal/benchmark startup, development videos, probes, and regressions: RTX Real-Time 2.0, DLSS Performance, and RTPT max bounces 2, with AO unchanged.
- Verified the effective values in separate normal and benchmark processes at 1280×720, VSync OFF, 120 Hz main/render, 59 Hz present, and the unchanged 210 W power limit. AutoBaseline and Candidate Balanced remain explicit comparison presets; RTX Minimal and AO OFF are not production candidates.
- Regressed the explicit V3 demo through the inherited standard: revision 1200, zero mass-balance error, Flow active-block final/peak 278/305, 505 V3 visual commits, 868 texture uploads, and zero V3 failures; the rendered frame retained flame/smoke, shadows, V3 surface texture, and hot emission.
- Requalified Release build in `8.21 s`, Phase 0 RTX exit 0, and all eight standard processes with `77 / 77` tests in `354.5 s`.

- Added a production-neutral isolated-Kit crash-safety boundary before Phase V3T-M: repo-local privacy opt-out, automatic dump upload disabled, compressed local dump preservation, run-scoped dump directories, and crash-token fail-fast are now shared by the V3T-G through V3T-L diagnostic runners.
- Qualified the boundary with a normal startup, an intentional native `0xC0000005`, and a post-crash startup: Crash Reporter GUI 0, upload attempts 0, preserved 410,922-byte dump, unchanged dump SHA-256, and unchanged relevant Windows crash-reporting registry snapshots.
- Kept dumps, Kit logs, and raw dump-analysis JSON outside Git. Recorded the common real-crash signature for AO OFF and `flow_layer_translucency_only` (`0xC0000005` read `0x20`, `omni.fabric.plugin.dll+0xD6960`) without attributing it to AO; both conditions remain held.
- Requalified all eight standard processes and `77 / 77` tests in `371.6 s` after the isolated-runner safety changes.

- Added production-neutral Phase V3T-L lightweight RTX preset probes with an eight-consecutive-visible-frame readiness gate and effective-setting verification from bundled Kit 110.2 UI paths.
- Measured 30/30 clean formal processes: Candidate Balanced/Performance reduced ground-and-stones from the V3T-K `17.40 ms` reference to `8.57 ms`, Cylinder20 from `21.73 ms` to `8.57 ms`, and Flow+volume from `40.79 ms` to `22.02 / 20.90 ms`; neither Flow result met the declared 58-FPS near-present gate.
- Held AO changes after the AO-OFF Flow-volume preflight produced a native `0xC0000005` read at `omni.fabric.plugin.dll+0xD6960`; the Crash Reporter dump remains Git-ignored, while its SHA-256 and limited no-symbol stack evidence are recorded.
- Rejected RTX Minimal as a production candidate despite a `60.081 FPS` preflight because the real Phase 3 V3 scenario failed the Flow active-block compatibility gate. Balanced/Performance visual-only V3 captures retained geometry, shadows, emission, flame, and smoke; Performance remains fallback-only.
- Kept production defaults unchanged and did not change the 210 W power limit. The 100% comparison remains approval-gated.
- Requalified Release build, Phase 0 RTX, all eight standard processes and `77 / 77` tests, plus six alternating V3T-C runs with identical authority hashes, zero mass-balance error, Resident revision 1200, and active wood-owned Flow blocks.

- Added production-neutral Phase V3T-K using only the existing visible viewport's public `ViewportAPI.frame_info` / `fps`; 39 stage processes and 9 AA processes completed with zero stage-ID/fatal errors, no added RenderProduct/HydraTexture/capture, and the RTX 3090 power limit held at 210 W (60%).
- Isolated the Auto-AA stage path from empty RTX `101.523 FPS` through ground/stones/lights `54.939`, 20 cylinders `46.017`, V3 Mesh `46.136`, fixed textures `45.536`, unprovided dynamic URI `44.781`, rigid STOP `44.775`, timeline PLAY `36.229`, explicitly all-OFF authored Flow `44.247`, global-OFF but active Flow subtree/settings `31.483`, simulation `24.524`, and volume `24.517 FPS`.
- Found no V3 Mesh penalty relative to cylinders and only a `0.755 FPS` fixed-to-unprovided-dynamic difference; the ~32 FPS boundary is reproduced when global Flow and Emitter are OFF but authored Simulate/Render prims and layer Flow render settings remain active. Explicitly disabling those boundaries improved the same constructed Flow scene by `12.764 FPS`.
- Measured the global-OFF/active-subtree representative scene at `59.812 / 31.156 / 31.130 FPS` for DLSS Performance / Auto / DLAA. Performance approached but did not pass 60 FPS in any formal run; internal render resolution and Ray Reconstruction runtime state remain unavailable through the inspected public Kit 110.2 boundary.
- Kept production code and defaults unchanged. V3 remains default OFF, Sphere remains the production emitter, and the disabled Flow-subtree cost is recorded as a future profiler/stage-authoring audit rather than changed in this phase.
- Requalified the unchanged production paths with all eight standard test processes and `77 / 77` tests passing; the final combined static-gate plus suite command completed in `352.9 s`.

- Suppressed interactive Windows Application Error UI only inside the intentional Phase V3T-J crash fixture using process/thread error mode plus public WER `NO_UI`; the smoke runner now has a bounded, hidden fixture process while `kit.exe` and machine-wide settings remain unchanged.

- Added Phase V3T-J's target-local `0xC0000005` full-dump path without registry or machine-wide changes: a probe-loaded unhandled-exception handler invokes an external helper only on crash and records full-memory dump path, size, SHA-256, exception metadata, revision, slot, and lifecycle markers outside Git.
- Proved the collector with a real crash fixture: exit `0xC0000005`, `11,374,239`-byte minidump, `Memory64ListStream` present, SHA-256 `f86026adcc5749a298f4cf418ac7a6bb37fe9a461ffc00e9d77d1e902156d07b`.
- Rejected the first `DEBUG_ONLY_THIS_PROCESS` Kit path because it held RTX RtPso compilation beyond 200 seconds and timed out; none of that run is reused in the formal population.
- Completed 24 / 24 normal target-local-handler Kit processes across CPU reference, GPU ring3 normal, timeline restart, stage replacement, Provider regeneration, extension disable, GPU-init fallback, and publication-failure fallback with ordered teardown, zero dumps, zero stage-ID errors, and zero CUDA/device/pointer fatal markers.
- Combined with Phase V3T-G, recorded 102 selected non-reproductions without claiming safety or resolving the Phase V3T-F crash. GPU transport remains probe-only/default OFF and production V3 remains CPU-source/default OFF.
- Final Phase V3T-J regression passed the release build, Phase 0 RTX, 8/8-process 77/77-test standard suite, six-run V3T-C authority/mass/Flow matrix, and 24/24 ordered shutdown-log gate; the exact hashes and active-block range are recorded separately.

- Added the production-neutral Phase V3T-I visible-viewport FPS isolation path using only public `ViewportAPI.frame_info` / `fps`; all 18 formal Kit processes completed with zero RTX stage-ID errors and no added RenderProduct, HydraTexture, capture, or encoder.
- Audited effective loop limits (main/render 120 Hz, present 59 Hz, VSync OFF) and retained the observed RTX 3090 210 W enforced limit versus 350 W default (60%) without issuing a power-setting command.
- Measured three independent runs at 71.969 FPS for empty RTX, 59.978 / 31.807 / 27.150 FPS across 640x360 / 1280x720 / 1920x1080, and 24.080 / 24.101 FPS for Flow simulation-only / simulation-plus-volume.
- Classified pixel/GPU load as dominant under the fixed power limit; reflection, indirect lighting, realtime denoiser, and UI visibility were non-dominant in short preflight. Display-present FPS and raw frame p95/p99 remain explicitly unmeasured.

- Added Phase V3T-H's visible-viewport-only average render FPS probe after rejecting and isolating the first copied-RenderProduct approach, which emitted 14,067 `IRenderSettings::getRenderSettings failed getting a stage-id` errors before shutdown.
- Added live and post-exit fail-fast rejection for any stage-ID error; normal process exit is no longer sufficient to qualify the render path.
- Enumerated all 13 public `omni.stats` scopes and 274 nested nodes and found no stat matching the visible FPS HUD; audited the bundled HUD to confirm that it reads public `ViewportAPI.fps` and derives displayed frame time as `1000 / FPS`.
- Measured the existing visible viewport with no added HydraTexture or RenderProduct across 15 clean Kit processes: average FPS was `33.0106` for Flow OFF/V3 OFF, `22.3432` for Flow ON/V3 OFF, and `23.1000` for Flow ON/V3 CPU-source; all accepted logs had zero stage-ID and fatal errors.
- Explicitly left raw render-frame p95/p99, 1% low, frame thresholds, and display-present FPS unmeasured because Kit 110.2 exposes no public raw completion timestamp mapped safely to the visible viewport.
- Observed CPU-source V3 Provider setter p95 `76.905 ms`, full publication p95 `79.024 ms`, Kit update rate `23.932 /s`, and timeline sim/wall `0.399` across 903 publications; the small aggregate FPS reversal versus V3 OFF is within three-run variation and is not treated as an improvement.
- Kept production modules and defaults unchanged: V3 and GPU transport remain default OFF, the GPU production candidate remains absent, Point/rigid remain default OFF, and Sphere remains the production emitter.
- Requalified the corrected Phase V3T-H boundary with release build `9.41 s`, Phase 0 RTX, all eight standard processes and `77 / 77` tests in `394.0 s`, V3T-C `6 / 6` OFF/ON runs with authority/Flow/RTX invariants intact, and Phase 6DQ `11 / 11` gates at revision `710`; the committed Phase 6DQ evidence was preserved.
- Added the production-neutral Phase V3T-G shutdown-isolation probe and ran 78 independent Kit 110.2 / Flow 110.0.0 / RTX processes for CPU-source, Provider-only, Warp-only, synchronized GPU, GPU ring3, retained-resource, stage-first, and shutdown A–E boundaries.
- Observed 78/78 normal `0x00000000` exits with no timeout, `0xC0000005`, CUDA illegal-address, device-lost, or invalid-pointer report; each process retained fsync'd boundary markers and an explicit extension `on_shutdown` begin/end record.
- Classified the V3T-F crash as not reproduced rather than solved: no resource or shutdown-order condition produced a positive discriminator, the public Provider source-consumed fence remains unavailable, and GPU lifetime/root cause remain unconfirmed.
- Kept the GPU production candidate absent, CPU-source V3 and V3 default OFF unchanged, and declined re-adoption because the required 20-run selected lifecycle sequence including stage replacement and Provider recreation was not performed by this isolation phase.
- Evaluated the Phase V3T-F triple GPU-source ring as a temporary production candidate, then fully reverted the candidate after the isolated lifecycle process crashed during Kit shutdown with Windows exit `0xC0000005`.
- Retained 720 Flow+RTX timing samples for 20 logs, 120×60 RGBA8 base+emission, three independent runs, 20 warmup and 120 measured publications per transport.
- Reduced the all-run Provider setter p95 from `29.8788 ms` on the CPU-source reference to `0.2531 ms` on GPU ring3; GPU source-ready wait p95 was `0.6105 ms`, with no 5 ms setter samples.
- Kept end-to-end latency separate: publication-to-next-RTX-frame p95 remained `56.8542 ms` for GPU ring3 versus `72.3302 ms` for CPU reference, so the transport is not claimed to solve Flow+RTX frame latency.
- Exercised pre-crash initialization fallback, mid-publication fault fallback, timeline restart, stage replacement, Provider recreation, bounded convergence, and 1,200 continuous GPU publications, but did not promote those observations past the mandatory crash-free lifecycle gate.
- Recorded that the public `DynamicTextureProvider` API exposes no source-consumed fence or guaranteed GPU-pointer reuse point; the exact relationship between that missing lifetime boundary and the shutdown backtrace remains unconfirmed.
- Left production modules, normal/benchmark app settings, the V3 demo preset, CPU-source V3, V3 default OFF, Point/rigid default OFF, Sphere default, Flow 110.0.0, wood authority, physics, checkpoint, revision, rollback, Mesh, and collision unchanged.
- Requalified the reverted baseline with release build `8.89 s`, Phase 0 RTX exit 0 in `21.6 s`, all eight standard processes and `77 / 77` tests in `406.8 s`, V3T-C 6 / 6 runs and 10 / 10 functional gates, and Phase 6DQ `11 / 11` gates at revision `710`.
- Added the production-neutral Phase V3T-E GPU-source ring, RTX pixel-readback, fault, long-run, and actual extension-manager lifecycle probe without changing V3T-C, Phase 6DQ, production modules, or defaults.
- Compared CPU reference, fully synchronized single GPU source, double ring, and triple ring for 96×15 and 120×60 RGBA8 base＋emission across six matrix processes, three rotated independent runs, 20 warmup and 120 measured publications per mode, totaling 2,880 performance samples.
- Reduced the 120×60 explicit source-ready wait p95 from `0.7911 ms` for the single synchronized GPU buffer to `0.0599 / 0.0689 ms` for double/triple rings while retaining Provider setter p95 `0.2008 / 0.2193 ms`.
- Confirmed that GPU-source transport does not solve Flow＋RTX frame latency: the next requested frame remained `31.6607 / 31.5550 ms` p95, while the CPU-source Provider call reproduced a `27.5362 ms` p95 tail.
- Classified 240 public RTX PNG readbacks as 206 latest-complete and 34 mixed-revision, with mixed counts `8 / 9 / 9 / 8` for CPU/single/ring2/ring3; no invalid pixels occurred, but pixel correctness did not qualify.
- Exercised timeline stop/resume, stage reload/replacement, Provider regeneration, two injected failures with CPU fallback, 1,200 continuous ring3 updates, close-after-publication, and actual extension-manager shutdown; 10 / 12 lifecycle gates passed and all seven long-run checkpoints were latest-complete.
- Fixed the shutdown owner boundary so the isolated extension records Warp synchronization → Provider destruction → source-allocation release without retaining the IExt object or emitting pointer/device-lost/use-after-free warnings.
- Declined production integration because the public `DynamicTextureProvider` API exposes no source-consumed fence or documented GPU-pointer reuse lifetime, normal readback still contains mixed revisions, and lifecycle qualification is incomplete; CPU transport/fallback and all defaults remain unchanged.
- Requalified the release build in `8.34 s`, Phase 0 with RTX ready in `16.423 s`, all eight standard processes and `77 / 77` tests in `385.0 s`, all six isolated V3T-C runs with `7 / 7` authority/Flow/RTX gates, and isolated Phase 6DQ with `11 / 11` gates without rewriting its committed evidence.
- Added the independent Phase V3T-D DynamicTextureProvider boundary probe without changing the production V3 consumer, V3T-C, Phase 6DQ, or any default.
- Measured 42 separate processes, 20 warmup publications per case, 120 measured samples per case, three independent runs, two RGBA8 atlas sizes, base/emission/both, fixed/changing content, CPU/GPU source, RTX, and Flow for 25,920 retained samples.
- Classified the V3T-C `cpu_upload_ms` field as a `DynamicTextureProvider` CPU-source publication call rather than raw memcpy bandwidth: 20-log two-texture p95 was `1.8164 ms` unconnected, `1.8089 ms` Mesh-connected without RTX rendering, `2.1147 ms` under RTX with Flow OFF, and `28.8968 ms` under RTX plus Flow.
- Qualified a synchronized, probe-owned Warp GPU baseline at setter p95 `0.2021 ms` plus explicit CPU-to-GPU staging p95 `1.4223 ms` under Flow, while the next requested RTX frame remained `31.4113 ms`; GPU publication is therefore not a production integration decision or an end-to-end frame-latency fix.
- Measured source preparation separately at p95 `0.2708 ms` for CPU-source and `0.2868 ms` for GPU-source in the 20-log, two-texture changing case, confirming that source generation is not the observed 28.8968 ms publication tail.
- Preserved all Prim paths, material bindings, asset paths, and USD revisions throughout every measured population; all Flow runs had active blocks, and GPU telemetry remains explicitly whole-process rather than provider-owned.
- Recorded that fixed and changing content behaved alike, 96×15 and 120×60 behaved alike, and 16.67 ms quantization was weak; Flow-time CPU-source synchronization is the strong boundary candidate, while the exact provider/resource/fence implementation remains unconfirmed.
- Requalified the release build in `9.02 s`, Phase 0 with RTX ready in `162.1 s`, all eight standard processes and `77 / 77` tests in `417.4 s`, all six V3T-C OFF/ON runs with authority and reflection gates intact, and Phase 6DQ at `11 / 11` gates without rewriting its committed evidence.
- Added Phase 6DQ's explicit `residentPointRigidLayoutEnabled=false` setting and selected `rigid_frame_v1` exactly once before offline Point stage authoring and Kit context connection.
- Preserved the legacy cardinal fallback and rejected rigid/legacy-qualification contradictions, orphaned qualification settings, and invalid translation-skip combinations before stage construction.
- Qualified the normal extension path on Flow 110.0.0 with 11 / 11 gates, 720 points, revision 710, 391 peak active blocks, 58 / 60 unique frames, zero Point resyncs, and clean shutdown.
- Requalified release build, Phase 0, and the complete eight-process 77 / 77 standard suite in 379.5 seconds; Point and rigid layout remain default OFF and Sphere remains the production default.
- Added Phase 6DP's real-Kit rigid-frame application-owner probe without exposing a new normal-app setting or changing any production default.
- Qualified 11 / 11 gates across rigid owner composition, revision 1 publication, 37-to-53-degree stopped refresh, unchanged-layout skip, running-write rejection, live-migration rejection, real stage close/attach/rebuild, revision 3 continuation, and idempotent shutdown.
- Requalified the complete eight-process 76 / 76 standard suite in 382.6 seconds after adding the isolated owner probe and report tooling.
- Kept Point and V3 default OFF, Sphere as the production fallback, and the existing wood authority, snapshot, checkpoint v1, Flow 110.0.0, collision, revision, and rollback contracts unchanged.
- Added Phase 6DO's default-off rigid-frame native producer and connected arbitrary right-handed log transforms to the existing immutable `ResidentPublishedSnapshot`/Point schema without changing wood authority, checkpoint v1, Flow 110.0.0, or production defaults.
- Kept the legacy native layout export unchanged and added `campfire_native_surface_layout_frames`; legacy producers do not resolve the new symbol, while rigid producers validate finite right-handed orthonormal frames before writing scratch positions.
- Extended immutable layout payloads and owner state with mutually exclusive cardinal axes or rigid frames; representation remains fixed for a session, participates in the retry digest, and cannot migrate live.
- Qualified 15 / 15 real native/Kit gates: identity-X positions and channels are byte-identical, 37-degree rotation has `0.0 m` maximum reference error, reflection fails closed, and injected publication failure restores USD/native state before exact retry.
- Verified explicit rollback/republish, export/open reconstruction, and cross-representation recovery rejection; historical legacy-Y byte equivalence remains explicitly excluded because it is a reflection.
- Requalified the release build, the focused three-test Kit boundary, and the complete eight-process 76 / 76 standard suite in 328.8 seconds.
- Kept Point and V3 default OFF and Sphere as the production emitter; the next independent gate is opt-in rigid-session application-owner orchestration.
- Resumed Phase 6DM as Phase 6DN and implemented the planned immutable Point layout-representation contract without changing wood authority, `ResidentPublishedSnapshot`, checkpoint v1, native ABI, Flow 110.0.0, physics, or production defaults.
- Added stable `legacy_cardinal_axes_v1` and reserved `rigid_frame_v1` identifiers, included representation in the immutable surface-payload digest, and pre-authored one static `campfire:layoutRepresentation` Token before stage connection.
- Rejected payload, stage, layout-refresh, and replacement-consumer representation mismatches before attempt accounting, USD writes, or old-consumer close; publication never rewrites the stage Token and live sessions cannot switch representation.
- Qualified 14 / 14 source-contract gates and 13 / 13 real-Kit anonymous-USD runtime gates; the release build and expanded eight-process 75 / 75 standard suite passed in 460.9 seconds.
- Kept the rigid-frame producer unconnected and Point default OFF; the next independent gate is rigid-frame byte/revision equivalence rather than an in-session migration.
- Fixed V3T-C as the safe stop for further V3 optimization. The remaining bottleneck is the public CPU texture-upload boundary, and V3 work reopens only for a public direct-GPU update API, a Kit/Flow upgrade evaluation, or demonstrated operator impact.
- Made the explicit V3 preset the default evidence path for future development-log videos and human wood-state inspection while keeping normal applications V3 default OFF.
- Added Phase V3T-C's three alternating integrated V3 OFF/ON pairs with the same Resident-native producer, Flow/RTX scene, render hierarchy, camera, warmup, and two fixed captures per run.
- Preserved both authoritative wood SHA-256 values, the metrics CSV SHA-256, zero mass-balance error, ignition times, Resident revision, Flow fuel input, and active Flow across all six runs.
- Measured update-frame p95 medians of `7.9833 ms` OFF and `6.5593 ms` ON with zero 33.33/50 ms update frames in both groups; V3 publication p95 remained `36.1233 ms`, dominated by a `35.4457 ms` DynamicTextureProvider CPU-source publication call (historical field name `cpu_upload_ms`).
- Measured publication-to-next-RTX-update reflection at p95 `44.8087 ms` and one render update, and recorded whole-GPU utilization/memory separately from provider-owned memory.
- Added the single-command `run_visual_v3_demo.ps1` opt-in preset, which enables the render hierarchy, Resident adapter, native backend, and V3 together while existing Point/V0/V1 conflicts fail closed.
- Kept both normal Kit apps and production V3 default OFF because the isolated 20-log publication p95 remains `4.7540 ms` against the `1.0 ms` reference target; Cylinder fallback, Flow, Point, wood authority, and Phase 6DM remain unchanged.
- Captured a new 60-frame/6-second actual-combustion V3 trajectory and same-camera OFF/ON images, and published the compact machine-readable V3T-C report.
- Requalified the release build, Phase 0 RTX, Phase 2, V0 OFF/ON and 13/13 probe, V1 8/8, V2 8/8, the expected Cylinder-only V3 boundary at 6/9, V3M-A 6/6, V3M-B 10/10, V3M-C 17/17, and the expanded 74/74 eight-process suite in 365.7 seconds.
- Added Phase V3T-B's additive native RGBA8 beauty packer while retaining the immutable V2 payload, stable surface identity, compact descriptor, and default-off V3 boundary.
- Reused three session-owned native pack resources and matched every base/emission texel against the NumPy reference for four and twenty logs across 105 packs; invalid floats and surface permutations remain detectable.
- Defined displayed versus processed revision semantics and skipped base/emission uploads independently; 105 identical quantized revisions issued zero texture uploads and zero USD Sets.
- Added an adaptive visual scheduler that retains 5 Hz for rapid heat and threshold crossings while publishing small changes at a bounded 0.4-second cadence (2.5 Hz on the fixed 5 Hz source).
- Qualified 17 / 17 V3T-B Kit/RTX gates, 17 / 17 V3M-C regression gates, the release build, Phase 0 RTX, and the expanded 74 / 74 eight-process suite; requested camera captures force both atlases to republish.
- Recorded the unfavorable performance result: native 20-log pack p95 `2.7026 ms` versus NumPy `2.3398 ms`, and changing publication p95 `4.7540 ms`; V3 remains default-off pending integrated V3T-C measurement.
- Added Phase V3T-A's session-stable compact atlas descriptor and changed the default V3 mapping from a guttered 4x4 pixel cell to one exact RGBA8 texel per surface cell without changing surface identity, Mesh topology, physics, Flow, or production defaults.
- Qualified 12 / 12 Kit/RTX compact-atlas gates across four and twenty logs, encoded cell sampling, side/cap/seam mapping, transform, stage reload, managed paths, and nearest-sampled 1x1 versus 2x2 rendered equivalence.
- Reduced the two-atlas 20-log transfer from `921,600` to `57,600 bytes` per revision (16x smaller); the four-log scene now authors a minimal `96x15` descriptor instead of reserving all twenty slots.
- Measured the compact 20-log isolated publication at p95 `1.8627 ms` beauty packing, `0.0741 ms` boundary work, `2.2883 ms` upload, `1.1126 ms` revision commit, and `4.8254 ms` total over 100 post-warmup samples.
- Kept V3 default-off because the `1.0 ms` reference publication target remains unmet; native beauty packing and change-aware publication are reserved for the independent V3T-B commit.
- Requalified the release build, Phase 0 RTX scene, V3M-B 10 / 10 probe, V3M-C 17 / 17 probe, and complete eight-process 73 / 73 standard suite after compact-atlas integration.

- Added Phase V3M-C's default-off V2 surface-payload consumer for the stable V3M-B render Mesh using two fixed 480×240 RGBA8 dynamic textures and one revision-last USD Set per update.
- Added vectorized moisture/char/ash/temperature beauty packing for 20 logs × 360 stable surface identities without Python cell loops, per-cell USD attributes, live Prim creation, Point payload changes, or authority coupling.
- Qualified 17 / 17 Kit/RTX lifecycle gates including raw pointer upload, changed-frame visibility, unchanged-revision no-op, stale rejection, injected visual-only recovery, timeline restart, stage reload republish, provider close, stable managed paths, and stable Mesh topology digests.
- Measured the isolated 20-log path over 100 post-warmup samples: V2 native extraction p95 `0.7880 ms`, beauty pack p95 `2.7769 ms`, CPU upload p95 `2.4774 ms`, revision commit p95 `1.0142 ms`, and full visual publication p95 `5.4135 ms` for `921,600 bytes` per revision.
- Kept V3 default-off because the `1.0 ms` reference publication target is not met; GPU upload and provider-scoped GPU memory remain unqualified under the public Kit 110 ownership/API boundary.
- Recorded a real 240-second Resident-native combustion trajectory at 5 Hz with 1,200 visual revisions, 2,400 uploads, 1,200 USD revision commits, zero visual errors, 60 RTX frames, and a six-second MP4 distinct from the fixed-state diagnostic.
- Verified current-code V3 OFF/ON dry and wet authority SHA-256 exact parity, ignition `66.2 / 166.4 s`, zero mass-balance error, peak fuel `1.0`, revision `1200`, and nonzero Flow active blocks; exact Flow field equality is not claimed because CPU texture stalls change wall-frame pacing.
- Added three focused V3 mapping/lifecycle tests and passed the complete eight-process regression with 73 / 73 cases in 368.9 seconds.
- Stopped at V3M-C without enabling production by default, removing legacy Cylinder/V0/V1 paths, changing the analytic collider, deforming Mesh points, implementing V4, or resuming Phase 6DM.
- Added Phase V3M-B's default-off Xform/analytic-Cylinder/UV-Mesh production candidate while preserving the legacy Cylinder path as the default and rejecting V0/V1 conflicts.
- Authored a fixed 384-face Mesh that maps 288 side faces and 96 cap faces onto exactly 360 V2 surface identities; 24 side/cap corner faces deliberately reuse one state, and face-varying UVs sample guttered texel centres in a fixed 20-log atlas.
- Added representation-neutral root, collider, render-surface, dimension, transform, and material-target helpers; Resident snapshot display color and Resident Point layout now resolve through those helpers while diagnostic values and revision remain on the stable root.
- Qualified the final Mesh checker in Kit/RTX with 10 / 10 gates, including four distinct logs, 7,200 unique atlas samples, transform/reload persistence, no live structural change, exact authored physics parity, and exact Resident Point layout parity.
- Measured Phase 2 OFF/ON drop equivalence within the predeclared 0.02 m / 0.05 rad tolerances: 0.010646 m final-position error, 0.042244 rad orientation error, contact events 1,063 / 1,018, contact points 1,061 / 1,017, and Flow peak blocks 224 / 215.
- Measured Resident-native Phase 3 OFF/ON with exact dry/wet authority SHA-256, ignition 66.2 / 166.4 s, mass-balance error 0, revision 1,200, equal fuel and support values; all 13 combined V3M-B gates passed.
- Kept the feature default-off, the analytic Cylinder as the only collider, Mesh points immutable, V0/V1 available, V2 payload unconsumed, dynamic texture publication unintegrated, and Phase 6DM held.
- Completed the production-neutral Phase V3M-A Cylinder-root compatibility audit and isolated Xform/Collider/RenderSurface feasibility probe.
- Enumerated 1,034 source/stage evidence lines, five canonical saved stages with Cylinder-root evidence, and fourteen checkpoint/recovery files; defined one six-helper resolution boundary for a future default-off hierarchy.
- Qualified an isolated Xform root with RigidBody/Mass/damping, an invisible analytic Cylinder child with Collision/physics material, and a face-varying-UV Mesh child with no Physics/PhysX schemas.
- Rendered a fixed dynamic RGBA8 checker across 72 side quads and both twelve-triangle caps, then preserved exact child world transforms, Prim paths, topology digest, and URI through rotation, translation and stage reload.
- Passed all 14 isolated checks and all 6 combined V3M-A gates without modifying production scenes, settings, Flow/Point publication, checkpoint v1, V0/V1 defaults, V2 payload ownership, V3 integration state, or the held Phase 6DM work.
- Re-ran the complete eight-process standard suite after V3M-A: all 66 / 66 cases passed in 349.9 seconds, including 207.5 seconds of collapse coverage.
- Completed the fixed Kit/RTX Phase V3 feasibility probe and stopped before production integration because the required analytic Cylinder UV gate did not qualify.
- Confirmed the public `omni.ui.DynamicTextureProvider` publishes a stable `dynamic://` URI; CPU RGBA8 pixel replacement reached an authored-UV RTX material after two frames while the USD asset path and live Prim paths remained unchanged through transform, timeline stop/start, and stage reload.
- Confirmed CPU RGBA16F upload is accepted by the fixed API, while rendered RGBA16F quality and GPU-pointer upload remain unqualified; no safe public GPU pointer owner was introduced.
- Demonstrated with paired captures that an authored-UV diagnostic quad changes from red/blue to green/magenta while the same material on the existing analytic `UsdGeom.Cylinder` remains a uniform `(0,0)` fallback.
- Recorded the precise blocking boundary: the Cylinder exposes no controllable `st` primvar, so side, end caps, seam, inversion, and object-local 360-cell atlas mapping cannot be qualified without expanding the shape or shader contract.
- Did not implement the 20-log atlas, V3 observer/flag, shader alternatives, Mesh substitution, V4, default changes, V0 removal, or Phase 6DM resumption; V0 and V1 remain default-off fallback/comparison paths.
- Passed all 12 V3 final gates, the release build, Phase 0 RTX regression, the 66 / 66 eight-process suite, and paired Resident-native Phase 3 V0 OFF/ON runs through revision 1200 with exact authoritative-state SHA-256 parity, zero mass-balance error, active Flow, and zero visual errors.
- Added Phase V2's independent `ImmutableWoodVisualSurfacePayload` and native bulk producer for temperature, moisture, char, ash, and stable local-surface identity without modifying Point payloads, sidecars, session consumers, layouts, physics, Flow, or defaults.
- Added the audited MSVC bulk pack entry point to the existing native library; it traverses the resident SoA in log-major/local-cell order, rejects invalid values before completion, and creates no per-cell Python objects.
- Compared every channel and identity element against an independent reference for 720 and 7,200 surface cells and proved that a two-cell permutation with the same value multiset is not hidden by aggregate statistics.
- Passed all 8 V2 gates and the complete 8-process regression with 66 / 66 cases in 350.2 s.
- Measured 20-log p95 costs separately: native pack 0.4738 ms, boundary copy 0.1132 ms, validation 0.6203 ms, digest 0.1406 ms, and total 1.3646 ms over 100 post-warmup samples.
- Added the independent, default-off Phase V1 eight-band visual probe without resuming or changing the held Phase 6DM layout production work.
- Aggregated stable local wood-cell identity into eight axial surface bands and reused V0 dry/wet/char/ash/emission semantics; the physical Cylinder, collision, Flow source, authority, schemas, and production defaults remain unchanged.
- Pre-authored 8 render-only diagnostic Cylinders per log in a dedicated stage, kept all physics APIs on the original logs, and skipped all USD writes for an unchanged revision.
- Captured same-camera, same-light, fixed-snapshot V0/V1 images and a four-second comparison video; the evidence is explicitly not a combustion trajectory and shows materially improved axial locality.
- Passed all 8 V1 gates and the complete 8-process regression with 64 / 64 cases in 350.1 s.
- Measured the 20-log V1 fallback at 160 render Prims, at most 481 attribute Sets per revision, 44.6918 ms mean and 52.4202 ms p95 publication; V1 is not a production transport and does not meet the 1.0 ms reference budget.
- Added the independent, default-off Phase V0 per-log wood visual observer after completing and committing the Phase 6DM layout audit at `57fe3bc`.
- Derived diffuse color, roughness, and emission only from existing immutable `ResidentPublishedSnapshot` aggregate values; wood authority, Flow, Emitter, collision, shape, Point payload, layout representation, schemas, and production defaults remain unchanged.
- Selected pre-authored per-log `UsdPreviewSurface` materials after a Kit/Flow 110 probe showed that `displayColor` cannot represent roughness or emission; live updates reuse cached attributes and never create or delete Prims.
- Passed all 13 four-log material gates, including deterministic finite values, distinct dry/wet/char/ash states, preserved physics binding, zero Sets for an unchanged revision, no live Prim creation, and matched OFF/ON captures.
- Completed paired Resident-native Phase 3 runs through revision 1200 with exact ON/OFF authoritative-state SHA-256 values, Flow active blocks, zero visual failures, and unchanged ignition/mass-conservation results.
- Measured the two-log production visual observer at 0.4340 ms mean and 0.7652 ms p95 over 239 post-warmup updates; update-frame p95 was 8.7928 ms OFF and 8.5964 ms ON in separate sequential runs.
- Recorded the scalability limit: the four-log all-fields-changing probe measured 4.4895 ms publication p95, so the proposed 1.0 ms reference budget for 20 logs is not qualified; V1 bands and V2/V3 surface payload/texture work remain unimplemented pending approval.
- Added three focused V0 lifecycle/mapping tests and re-ran the complete eight-process suite with 62 / 62 cases passing in 368.8 s, including 210.7 s of collapse coverage.
- Added Phase 6DM's static AST/source compatibility audit for a future immutable Point layout-representation field without changing production code.
- Confirmed the current boundary precisely: 10 payload fields, two constructor sites, exact pending payload reuse, revision-safe consumer handoff, and five missing representation checks/identifiers.
- Defined a five-area minimum production delta with a trailing legacy-default payload field, sidecar publish/status validation, pre-authored USD Token, pre-close consumer comparison, and owner shared-state propagation.
- Kept wood JSON, Resident snapshot schema, checkpoint v1, stage recovery orchestration, native ABI, Flow 110.0.0, physics, and defaults outside the first integration change; a future Point checkpoint requires a new schema version.
- Passed all 19 Phase 6DM audit gates and verified production extension source hashes remained unchanged.
- Re-ran the complete regression after Phase 6DM: all 8 test processes and 59 / 59 cases passed in 369.3 s, including 213.4 s of collapse coverage.
- Added Phase 6DL's isolated immutable layout-representation prototype around the unchanged production `ResidentApplicationSession`.
- Qualified both `legacy_cardinal_axes_v1` and `rigid_frame_v1` through commit, injected primary failure, exact Point rollback, stopped consumer replacement, identical pending-payload retry, and continued revision 3.
- Rejected cross-representation payload publication and consumer replacement before writes or old-consumer close; equal replacement descriptor values remain recoverable without requiring Python object identity.
- Passed all 20 Phase 6DL gates while leaving production extension sources, Sphere default, Point default-OFF, Flow 110.0.0, physics, schemas, persistence, rollback, and revision contracts unchanged.
- Re-ran the complete regression after Phase 6DL: all 8 test processes and 59 / 59 cases passed in 342.6 s, including 200.9 s of collapse coverage.
- Added Phase 6DK's real-Kit, anonymous-USD transform/channel-identity probe using the production `create_log()` authoring path and two separate 720-point scenarios.
- Passed all 14 Phase 6DK gates: cardinal, 45-degree, and arbitrary-axis USD frames were right-handed and preserved stable surface-cell position/channel order with zero observed float32 position error.
- Demonstrated the legacy Y reflection's value impact: all 360 geometric coordinates remained present, but all 360 cell-varying temperatures moved to different coordinates; log-constant fuel and smoke remained aligned.
- Kept production integration unqualified and required an explicit session-bound migration policy before adding immutable frame metadata or selective publication to the existing Point sidecar.
- Re-ran the complete regression after Phase 6DK: all 8 test processes and 59 / 59 cases passed in 344.9 s, including 204.3 s of collapse coverage.
- Added Phase 6DJ's isolated MSVC rigid-frame surface-layout DLL without modifying or linking it into the production Phase 6AU native source.
- Passed all 10 Phase 6DJ gates at 720 points: identity-X byte parity, exact 45-degree and arbitrary-3D reference results, and atomic rejection of scale, shear, reflection, non-finite frames, and insufficient capacity.
- Proved that the legacy Y-axis swap is a reflection: its point set matches a proper 90-degree rotation exactly after sorting, but same-index positions differ by up to 0.177489 m, so per-cell channel alignment must be resolved before integration.
- Measured isolated 720-point kernel p95 at 0.0240 ms for the legacy cardinal function and 0.0266 ms for the rigid-frame spike; these values exclude USD, notices, Flow ingestion, simulation, and rendering.
- Passed the full eight-process 59/59 standard suite after Phase 6DJ in 379.2 seconds, including 225.9 seconds of collapse coverage.
- Added the Phase 6DI design-only contract for an additive per-log rigid-frame layout ABI, preserving the existing cardinal ABI and rejecting scale, shear, reflection, and other non-rigid transforms.
- Defined immutable byte-level changed-field detection before Vt conversion, selective Point attribute Sets, layout-revision-on-position-change, resident-revision-last publication, and exact rollback/retry/recovery requirements.
- Kept the work default-off and production-neutral, and explicitly separated reduced Set-call/conversion work from the still-unresolved complete-array USD authoring and Flow ingestion cost.
- Added Phase 6DH's stage-free audit of the pinned Flow 110.0.0 runtime interface, packaged public Python API, and native export tables.
- Confirmed that all 19 `IFlowUsd` members are voxelization, conversion, readback, or field-query surfaces; no attachment/detachment, subscriber enumeration, direct ingest timer, or profiling control is exposed.
- Confirmed that the packaged Python API contains only `PublicExtension` and command registration, while binary exports are limited to eight Carbonite lifecycle entries and one Python `PyInit` entry; this is not presented as proof about private implementation internals.
- Passed all 12 Phase 6DH gates with no stage connection and unchanged production app SHA-256, and ended subtractive consumer-isolation work rather than relying on an unsupported private hook.
- Added Phase 6DG's stage-free, default-off audit of the public Flow USD extension lifecycle boundary using the pinned Kit/Flow runtime.
- Confirmed that immediate `omni.flowusd` disablement succeeds and removes the `FlowUsd` StageUpdate node, while `omni.usd.schema.flow` remains enabled.
- Rejected extension disablement as a narrow performance control because dependency resolution also disables `campfire.app`, removing the Resident producer rather than isolating only the Flow USD subscriber.
- Restored `omni.flowusd`, `campfire.app`, and the original StageUpdate node exactly, passed all 16 Phase 6DG gates and the final 8-process 59/59 standard suite in 351.6 seconds (collapse coverage 210.4 seconds), and preserved the production app SHA-256 and all production defaults/contracts.
- Added Phase 6DF's derived, profiler-off FlowUsd StageUpdate enablement matrix: three paired 500-revision runs configure the node before target-stage connection and restore it after every process.
- Preserved exact native-state and Point positions/fuel/temperature/smoke SHA-256 values, 500/500/500 consumer revisions, 500/500 publications, and zero failures or Point resyncs across all six cases.
- Measured run-median enclosing-update p95 at 14.2288 ms with FlowUsd StageUpdate enabled versus 13.7408 ms disabled (+3.55%); the per-run ranges overlap, so the contrast is not a direct Flow-ingest timer.
- Kept ChangeBlock exit live in both modes (layout p95 medians 1.1046 versus 1.0046 ms; channel p95 medians 0.9748 versus 0.8597 ms), showing that StageUpdate disablement does not prove synchronous USD notice subscribers were removed.
- Rejected the disabled mode as an adoption candidate because active blocks changed from 32 to 0 and all NanoVDB readback channels disappeared, even though authoritative/source values remained exact; production defaults and app SHA-256 remain unchanged.
- Passed all 13 Phase 6DF gates and the final 8-process 59/59 standard suite in 351.7 seconds (collapse coverage 207.9 seconds), with the FlowUsd node restored and profiler capture disabled in every run.
- Added Phase 6DE's default-off runtime audit of the fixed Kit profiler, Tf notice, StageUpdate, and `omni.flowusd` surfaces without changing production configuration or publication contracts.
- Confirmed that public `carb.profiler.IProfileMonitor` can return completed-frame named zones and round-tripped two custom calibration zones while restoring capture mask `0 → 1 → 0`.
- Correlated 13 live Resident Point updates with active Flow blocks `24–32` and observed USD notice/pending-update, Fabric, Hydra, and PhysX zones, but no direct FlowUsd ingest timer, registered-subscriber enumeration, or Flow-specific named zone.
- Excluded all profiler-capture durations from performance acceptance because capture inflated an application update to seconds and nested zones overlap; the Phase 6DD residual remains unattributed pending a derived, profiler-off consumer-enablement comparison.
- Passed all 19 Phase 6DE gates and the final 8-process 59/59 standard suite in 385.9 seconds (collapse coverage 233.4 seconds), with 760/760 publications, zero sidecar failures or Point resyncs, restored profiler masks, and unchanged production-app SHA-256.
- Added Phase 6DD default-off `ObjectsChanged` callback timing and live four-Set versus six-Set ChangeBlock-exit timing, while preserving the existing coalesced transaction, rollback, and revision-last behavior.
- Proved that Set-call count differs from notice changed-path count: 60 layout snapshots produced 4 or 6 changed paths, while 700 channel snapshots produced 2, 3, or 4, with one snapshot notice per each of 760 publications and no resync.
- Measured live ChangeBlock-exit p95 at 1.4380 ms for layout snapshots and 0.9623 ms for channel snapshots; the existing diagnostic callback itself measured only 0.1508 ms and 0.0996 ms respectively.
- Added a five-run isolated USD baseline across 1/2/4/6 authored attributes: full-layout exit median p95 was 0.0071 ms without a listener and 0.0112 ms with one enumerating listener, explicitly rejecting live-minus-isolated subtraction as a Flow-ingest timer.
- Passed all 12 Phase 6DD gates, the release build, Phase 0 RTX regression, focused transaction test, and the final 8-process 59/59 standard suite in 408.3 seconds (collapse coverage 240.5 seconds), with unchanged production-app SHA-256; reused the same deterministic Phase 6DC video rather than duplicating media.
- Added Phase 6DC default-off changed-tick timing for all four Vt conversions, previous-value snapshots, `Sdf.ChangeBlock` entry/exit, four array Sets, two revision Sets, the full publication transaction, and producer commit.
- Measured 56 changed publications at 720 points: transaction p95 was 1.8616 ms, with `ChangeBlock` exit p95 1.3539 ms, four array-Set p95 sum 0.2221 ms, four Vt-conversion p95 sum 0.0961 ms, and previous-value snapshot p95 0.1183 ms.
- Added an enclosing `next_update_async` wall-time comparison (changed p95 98.2902 ms, unchanged p95 75.8272 ms) while explicitly leaving direct `omni.flowusd` ingest timing unavailable through the inspected public Flow 110 Python, `IFlowUsd`, and StageUpdate surfaces.
- Passed all 9 Phase 6DC gates with 760/760 snapshots, 56 changed and 704 unchanged publications, no sidecar failure, unchanged production-app SHA-256, and a direct six-second RTX capture; production defaults and transaction contracts remain unchanged.
- Passed the release build, Phase 0 RTX regression, focused transaction test, and the final 8-process 59/59 standard suite in 396.3 seconds; collapse coverage completed in 232.2 seconds.
- Added Phase 6DB default-off repeated-translation timing and an unchanged-origin precheck that avoids native Point layout allocation/build work without changing changed-tick publication, rollback, or revision behavior.
- In matched Flow 110 runs at 720 points, reduced native layout candidate builds from 760 to 56, avoiding 704 builds and 306.2019 ms of measured candidate time; optimized changed ticks measured position Vt conversion p95 0.0335 ms, `pointPositions.Set()` p95 0.1205 ms, and full publication transaction p95 1.7951 ms.
- Passed all 8 Phase 6DB gates with 760/760 snapshots published and zero sidecar failures in both runs; retained production Sphere/Point defaults and all existing physics, JSON, rollback, revision, and immutable snapshot contracts.
- Passed the release build, Phase 0 RTX regression, focused rollback/precheck test, and the final 8-process 59/59 standard suite in 406.2 seconds; collapse coverage completed in 239.9 seconds.
- Added the default-off Phase 6DA running-translation snapshot path: candidate Point positions remain immutable until `positions`, `layoutRevision`, channels, and consumer revision commit together, with producer/layout rollback on downstream failure.
- Measured a 20.000000 mm running log edit at revision 344→345: the Point centroid moved 19.999996 mm, displacement differed by 0.0000037 mm, maximum alignment error was 0.0000053 mm, and layout revision advanced 9→10.
- Kept required Flow readbacks and 24 active blocks nonzero at both samples; rotation tracking, within-update Flow reset exclusion, seamless visual continuity, and complete solver checkpoint continuity remain unqualified.
- Passed the release build, Phase 0 RTX regression, rendered devlog/modal verification, and the full 8-process 59/59 standard suite in 433.5 seconds after adding the Phase 6DA contract tests.
- Added Phase 6CZ sampled Resident/Flow boundary telemetry and a direct 60-frame RTX video, correlating revisions 350→351 with log transform, Point centroid, active blocks, and NanoVDB readback.
- Measured a Point-centroid jump of Y +40.130 mm and Z -19.997 mm (44.837 mm total), while Flow active blocks remained 44→48 and temperature, fuel, burn, smoke, and velocity readbacks remained nonempty at both observable samples.
- Kept seamless visual continuity and complete Flow-solver checkpoint continuity unqualified: the two-sample public readback cannot exclude reset-and-repopulation within one Kit update, and dynamic log-to-Point tracking remains unimplemented.
- Treated the four historical Phase 6CO STOP/stopped-layout gates as superseded under the corrected 30,000-frame safety cap; all other Phase 6CO scenario gates passed and the production application SHA-256 remained unchanged.
- Added Phase 6CY uninterrupted Resident renderer qualification: one PLAY crosses disabled viewport updates, the first enabled 1280×720 frame, and a capture callback without probe pauses or time resets.
- Qualified timeline continuity for that bounded run with revision 0→57, Flow active-block peak 24, one root layer, zero STOP/PAUSE events, zero PhysX/Flow stage-reattach errors, and an unchanged production-app SHA-256; visual seam continuity and Flow-field checkpointing remain unqualified.
- Retained the historical Phase 6CQ STOP-expectation mode while adding an observation-only mode, and rejected its sequential pause/reset matrix as continuity evidence because the matrix repeatedly recomposed the stopped log layout and stage attachments.
- Added Phase 6CX quit-limit qualification: Kit's `quitAfter=900` is an application-update frame cap, and a warm recheck auto-quits before the renderer timeline probe can publish its report.
- Superseded the Phase 6CT STOP baseline and the Phase 6CU-CW causal contrasts; the same production app remains PLAY after the viewport frame and retry with a 30,000-frame cap, both with the normal cache and a newly isolated application shader cache.
- Raised the renderer diagnostic safety cap to 30,000 frames for Phase 6CQ, 6CR, 6CS, 6CU, 6CV, and 6CW while keeping production configuration and the unresolved Resident/Flow visual-continuity qualifications unchanged.
- Added Phase 6CW public root-identity isolation: an isolated derived app named `campfire.simulator` matches the production public app identity, selected settings, important extension IDs, and non-sensitive option-name set but remains PLAY after the viewport frame and retry.
- Kept production unchanged and narrowed the repeated STOP boundary beyond app filename/name to root load origin, config stack, or startup lifecycle not exposed by the matched public identity.
- Added Phase 6CV serialized root-configuration isolation: six Editor-rooted variants covering static settings, generated version lock, package/template metadata, and extension search paths all remain PLAY after the first viewport frame and retry at fixed 1280x720.
- Kept the production app unchanged and narrowed the repeated STOP boundary to production root-app identity or lifecycle outside the serialized `.kit` declarations; continuity and Flow-field checkpoint qualifications remain false.
- Added Phase 6CU derived-app initialization isolation: four Editor-rooted variants covering head/tail declarations, Campfire's direct dependency set and order, and the Extensions Manager dependency all remain PLAY after the first viewport frame and retry at fixed 1280x720.
- Kept the production app unchanged and narrowed the repeated STOP boundary to production root-app initialization, including static declaration application, the generated version lock, package metadata, or root lifecycle.
- Added Phase 6CT application-boundary isolation: a matched editor-base extension set remains PLAY at fixed 1280x720, while matching all 15 non-sensitive runtime-settings differences in the Campfire app still reproduces STOP on both the first and retry playback.
- Kept the `fillViewport=true` workaround unadopted and narrowed the remaining boundary to application initialization order, viewport creation timing, or internal state outside the settings allowlist.
- Added Phase 6CS offline scene and application-boundary isolation: Flow, PhysX, Phase 3 content, Resident ownership, headless mode, FlowUsd alone, the inactive Campfire extension, async renderer init, and fixed viewport mode alone are not sufficient for the repeated post-frame timeline STOP.
- Measured `fillViewport=true` as a Campfire-app workaround that preserves PLAY after the first viewport frame, but did not adopt it because it replaces deterministic 1280x720 capture with UI-sized rendering; production and continuity qualifications remain unchanged.
- Added Phase 6CQ renderer/Hydra boundary isolation: the normal Resident interactive lifecycle remains PLAY to 0.8 s and advances revision 0 to 3 before the first completed viewport frame, then reproduces STOP at 0.0 s immediately after that frame.
- Confirmed that neither a capture callback nor ongoing viewport updates are required for the STOP and that disabling each public StageUpdate node—or all five together—does not remove it; the first completed frame's attachment state remains under investigation.
- Added Phase 6CR plain-stage isolation: the same saved Point/Flow/PhysX stage reproduces the post-viewport-frame STOP without composing the Resident backend, USD adapter, Point sidecar, session, or owner.
- Added Phase 6CP StageUpdate boundary isolation: normal and benchmark apps expose the same five enabled nodes, and the plain stage, composed Resident owner, and renderer-disabled extension interactive lifecycle all remain PLAY with zero STOP events.
- Confirmed the interactive Resident owner actually advances Point revision from 0 to 4; the unresolved PLAY→STOP is therefore currently confined to the RTX capture qualification path, while renderer-enabled production continuity remains unqualified.
- Added Phase 6CO as a default-off negative timeline-boundary audit: explicit stage/session range, auto-update, looping, and `Timeline.commit()` still reproduce PLAY→STOP twice at 0.0 s in the normal Resident Point owner path, while an isolated stage probe remains playing.
- Replaced late-only continuity evidence with a Phase 6CO video that actually spans the layout boundary: 10 RTX frames before the 40 mm edit and 50 immediately after it, with Point/log alignment held within about 1.86 nm and Flow solver-field continuity still unqualified.
- Corrected the Phase 6CM and 6CN development-log captions: both older clips contain only revisions 651–710 after recovery and do not visually prove the revision 300→301 boundary measured by telemetry.
- Added Phase 6CN atomic stopped-layout publication, authoring predeclared `pointPositions` and `layoutRevision` in one rollback-capable transaction without advancing the Resident snapshot revision; the former 40 mm exposure fell to about 1.9 nm.
- Kept Phase 6CN explicitly partial: its real Flow/RTX run records PLAY immediately followed by STOP and does not qualify timeline, Flow solver-field, stage-recovery, or seamless visual continuity.
- Reclassified the visible Phase 6CJ–6CL log jumps and flame resets as an unresolved continuity defect; their consumer, revision, command, and observer results remain valid, but seamless Flow/visual recovery is no longer claimed.
- Added a default-off Phase 6CM frame-aligned continuity diagnostic for PhysX log origins, 360-point group centroids, Resident revision/tick, timeline state, and Flow active blocks; it measured a 40.000 mm pre-publication gap, numerical alignment after revision 301, and zero playing timeline samples while keeping seamless continuity explicitly unqualified.
- Added the Phase 6CL default-off transform observer, filtering real USD notices by stopped log xform, coalescing 13 rapid edit requests into two owner-thread commands, and advancing layout revision only once for the final supported transform.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-08-04

### Added

- Added the Phase 6CL stage-rebind-aware transform notice observer and queue coalescing counters, with running/non-transform filtering and a 14-gate real Flow/RTX qualification video.
- Added the Phase 6CK bounded FIFO and compact Resident Point control window, with owner-thread-only USD execution, structured accepted/rejected results, explicit shutdown discard, and a 13-gate real Flow/RTX qualification video.
- Added the Phase 6CJ explicit qualification path for PLAY-time stopped layout refresh, monotonic layout revision, current-layout recovery factory sharing, normal-owner stage lifecycle observation, and real Flow/RTX continuation after consumer replacement.
- Added the Phase 6CI default-off normal application composition, including complete offline schema authoring before context connection, extension-owned timeline/update lifecycle, primary and Point consumer pre-authoring, and a reproducible 10-gate real-Kit/Flow capture.
- Added the Phase 6CG production-but-unactivated Resident Point module, extracting the generic native surface producer, immutable byte payload, and transactional Point sidecar from benchmark ownership, enforcing pre-authored Flow schema and geometry/ABI validation, and proving byte-exact extraction plus full stage-recovery continuation in real Flow 110.
- Added the Phase 6CF default-off owner-thread stage recovery orchestrator, driving the qualified close/drain/attach lifecycle from real Kit events, retaining pending work across injected consumer-factory failure, retrying the exact immutable payload, and continuing Flow without live structural resync or production activation.
- Added the Phase 6CE default-off replacement-stage recovery path, validating stopped owner-thread consumer handoff, exact pending payload retry across Kit `close_stage_async`/`attach_stage_async`, revision-seeded primary and Point reconstruction, post-attach Flow recovery, and clean shutdown without pending discard.
- Added the Phase 6CD default-off session-owned Point sidecar, coupling its immutable 7,200-point payload to the existing Resident pending/retry lifecycle, rolling it back when primary snapshot publication fails, restricting layout replacement to stopped owner state, failing closed on stage replacement, and recording a real 60-frame Flow/RTX capture.
- Added the Phase 6CC default-off Resident-native surface-array producer, separating static 7,200-point layout from dynamic fuel/temperature/smoke channels, preserving immutable snapshot revisions, and qualifying the single Point Emitter through Flow 110 core simulation and RTX rendering without activating the production path.
- Added the Phase 6CB default-off, preset-independent Flow 110 Point Emitter qualification, proving a fresh pre-connected stage with individual layer, relationship, material, timeline, viewport, core simulation, sparse-field, array-equivalence, revision, notice, and no-live-resync gates from 16 through 7,200 points.
- Added the Phase 6CA production-but-unactivated `ResidentApplicationSession` owner with explicit states, owner-thread enforcement, downstream immutable-snapshot pending/retry, fail-closed normal shutdown, explicit forced discard, pure lifecycle coverage, and real Kit/native failure-recovery gates.
- Added the Phase 6BZ isolated owner-thread Resident checkpoint session, qualifying a non-terminal clone-stage save barrier, failure-safe continuation, and exact uninterrupted-versus-restored next-revision equivalence while deferring production UI and automatic persistence.
- Added the Phase 6BY isolated Resident checkpoint package spike with a versioned two-entry manifest/USDA format, atomic replacement, corruption and revision-consistency rejection, exact model-state validation, and revision-continuous Kit/MSVC restore while leaving production auto-resume disabled.
- Added the Phase 6BX default-off Resident lifecycle recovery gate, explicit same-stage revision/tick resume seeds, three-consumer resume validation, native rollback, downstream immutable-snapshot replay/retry, idempotent shutdown, and revision-continuous restart coverage.
- Added the Phase 6BW post-ChangeBlock shared-SoA adoption re-evaluation, rerunning all 16 proxy/ABI/lifecycle gates and deferring production adoption because the current 1,200-step Resident hot path already performs zero numeric re-imports.
- Added the Phase 6BV four-configuration emitter availability matrix, safely measuring one and twenty Point emitters at 7,200 points, retaining the qualified two-log Sphere reference, and refusing an end-to-end ranking while Point and NanoVDB consumers remain unavailable.
- Added the Phase 6BU fixed-Flow native API availability audit, confirming 19 public `IFlowUsd` members but no external NanoVDB consumer-write boundary, and made the Phase 6BT runner release its persistent context before exit and report safe unqualified outcomes without treating them as execution failures.
- Added the Phase 6BR–6BT fixed-Flow NanoVDB buffer/consumer probes, identifying four float channels plus packed RGBA8 and safely rejecting five unqualified public USD consumer arrangements without changing production.
- Added the Phase 6BP/BQ default-off fixed-Flow runtime probes, rejecting unsafe live PointCloud structural mutation, recording the native binding contract, and measuring persistent point-to-NanoVDB generation from 360 to 7,200 points without changing production.
- Added the Phase 6BO default-off emitter transport scalability audit, confirming aggregate Point and NanoVDB schemas in the fixed Flow SDK, measuring 360–7,200 Point payloads with source/copy/Set/notice separation, rejecting per-surface-point Prims, and leaving real Flow ingestion/rasterization as explicit follow-up work.
- Added the Phase 6BN trackless real-Flow adoption audit, balanced native-producer comparison, exact-output gates, explicit historical-runner opt-outs, and a browser-readable adoption report.
- Added the Phase 6BM default-off real-Flow `Sdf.ChangeBlock` resident publication candidate, revision-gated notice telemetry, same-block immutable rollback coverage, balanced native-producer measurements, and a browser-readable qualification report.
- Added the Phase 6BL local-Kit `Sdf.ChangeBlock` contract prototype, proving 19-to-1 USD notice coalescing, revision-consistent publication, explicit same-block snapshot replay, and a revision-gated in-memory timing reduction while leaving production unchanged.
- Added Phase 6BK default-off lightweight USD tail profiling, correlating 236 commits per run with Flow/render load without adding USD reads; real-Kit results attribute a median 83.0% of p95 publication time to `UsdAttribute.Set` while preserving exact authoritative outputs.
- Added the Phase 6BJ default-off production resident-native Phase 3 lifecycle path, connecting 1,200 native wood steps through immutable snapshots to the existing USD adapter with exact authoritative outputs; functional gates pass while USD tail-performance adoption remains deferred.
- Added the Phase 6BI direct resident-native output connection to the existing immutable `ResidentPublishedSnapshot` schema, with exact field-order, copy, revision, failure-isolation, lifecycle, and 4 ms performance gates while keeping production disabled.
- Added the Phase 6BH default-off immutable-shadow USD Set-skip candidate, retaining mandatory revision writes and full failure replay while passing the 4 ms gate in all three paired real-Kit runs.
- Added the Phase 6BG default-off lightweight resident USD commit trial with transactional bootstrap, revision-last publication, failure-only immutable snapshot replay, fail-closed recovery, and three paired real-Kit measurements.
- Added the Phase 6BF opt-in USD prim/attribute handle-cache trial, preserving actual authored old-value reads and transactional rollback while recording a repeatable but insufficient p95 improvement from 4.4762 ms to 4.1751 ms.
- Added the Phase 6BE opt-in redundant USD Set audit with USD-stored-value classification, per-attribute changed/unchanged counts and Set timings, three-run exact-output gates, and evidence that no-op skipping alone is insufficient for the 4 ms transaction target.
- Added Phase 6BD opt-in transactional USD profiling, separating snapshot construction from adapter publication and measuring prim lookup, payload preparation, attribute lookup, rollback-journal capture, `UsdAttribute.Set`, commit, and unattributed overhead across three paired real-Kit runs; production publication behavior remains unchanged.
- Added the isolated Phase 6BC-S shared NumPy/C++ SoA authority research spike with generation-checked Python cell proxies, edit leases, fail-fast step exclusion, exact rollback/schema gates, ABI validation, and three-run performance evidence; production and USD publication remain unchanged.
- Added the Phase 6BC default-off Kit resident snapshot adapter with owner-thread lifecycle enforcement, transactional USD rollback, one-revision Flow/visual/support publication, exact baseline-output gates, and real RTX 3090 timing evidence.
- Added the Phase 6BB resident backend lifecycle trial covering fresh Python-view export, revision-conflict rejection, transactional edit/native rollback, structural candidate rebuild, exact serialization, and idempotent shutdown export.
- Added the Phase 6BA headless native 5 Hz / 12-frame scheduler contract, immutable three-consumer revision fan-out, Python-reference tolerance gates, and structural-dirty safe stop.
- Added the Phase 6AZ explicit resident revision/dirty ownership trial, exact one-log state import, structural rebuild classification, and a documented rejection of unmarked direct writes in native mode.
- Added the Phase 6AY resident native publication boundary for 11 immutable app/Flow/support outputs per log, exact Python-contract comparison, and a measured rejection of full public-state scanning as an automatic fallback.
- Added the Phase 6AX resident three-pathway Arrhenius complete-step candidate, bounded secondary-tar branch coverage, tolerance-based lockstep evidence, and a 4 ms performance report.
- Added the Phase 6AW resident piecewise-complete wood-step candidate, including evaporation, pyrolysis, char oxidation, phase finalization, step outputs, cumulative products, exact ignition-history comparison, and a 4 ms performance gate.
- Added the Phase 6AV resident immutable-conduction-topology kernel, exact 62,400-edge comparison, pairwise energy-conservation gate, and next-reaction-boundary report.
- Added the Phase 6AU MSVC native contiguous-state boundary probe, exact 20-log Kit-Python comparison, per-step object-roundtrip rejection, and resident-SoA qualification report.
- Added the Phase 6AT error-budgeted whole-log approximate-sleep trial, three tolerance candidates, exact-step accuracy references, moving-heat performance gates, and native-path decision report.
- Added the Phase 6AS app-equivalent scheduler contract trial, immutable multi-consumer output revisions, fixed latency audit, and moving-heat activity test that rejects exact dormancy as stable capacity control.
- Added the Phase 6AR deterministic 5 Hz/12-frame wood scheduler trial, exact whole-log dormant gate, activity-ratio timing matrix, synchronous-state equivalence checks, and compact development-log video trigger.
- Added the Phase 6AQ Kit-Python scaling benchmark for 2, 5, 10, and 20 simultaneously active logs, exact per-log state gates, 4 ms budget analysis, and a compact development-log video trigger.
- Added the Phase 6AP two-depth re-profile of the adopted slotted-cell path, exact-output gates, current-hotspot report, and compact development-log video trigger.
- Added and adopted Phase 6AO slotted authoritative wood-cell storage after an exact-output, alternating three-pair end-to-end gate, while retaining mutable public fields and the serialized schema.
- Added the Phase 6AN post-inline two-depth re-profile, exact-output gates, current-hotspot report, and compact development-log video trigger.
- Added the Phase 6AM inline homogeneous sensible heat-capacity path, mutable-state fallback and exception tests, alternating three-pair adoption gate, browser-readable report, and a new real-run development-log video.
- Added the Phase 6AL two-depth re-profile of the adopted Phase 6AK path, exact-output gates, current-hotspot report, and compact development-log video trigger.
- Added the Phase 6AK step-local homogeneous heat-capacity path, public-state fallback tests, alternating three-pair adoption gate, and browser-readable report with a compact video trigger.
- Added the Phase 6AJ two-depth adopted-path re-profile, with separate three-run broad and per-cell timing sets, exact-output gates, and a browser-readable candidate report.
- Added the Phase 6AI constant-model heat-capacity fast path, mutable-state and fallback tests, alternating three-pair adoption gate, and browser-readable report with a compact video trigger.
- Added the Phase 6AH opt-in per-operation sensible-heat profile, three-run invariant gate, and browser-readable candidate-selection report.
- Added an opt-in deterministic Phase 3 viewport-frame capture and ffmpeg H.264 encoding path, with a real 1280×720 burn-scenario video embedded in the browser-readable development log.
- Added reusable compact development-log video triggers and an accessible shared playback modal with focus restoration, Escape/backdrop close behavior, and direct-file fallback.

- Added the Phase 6AG adopted-path internal re-profile, Phase 6Y comparison, exact-output gates, and browser-readable current hotspot report.

- Added the Phase 6AF runtime-topology mutability audit, explicit opt-in snapshot trial, alternating-pair benchmark, and browser-readable rejection report.

- Omniverse Kit Base Editorを基盤とするCampfire Simulatorアプリ。
- 決定的なPhase 0固定シーン生成とUSD書き出し。
- 固定カメラのヘッドレス画像キャプチャとJSON要約。
- シーン構造・再生成性を確認する拡張テスト。
- Phase 0を一括実行するPowerShell検証スクリプト。
- 実画面、実測値、検証結果、既知の問題を掲載する静的Web版開発日記。
- NVIDIA Flow 110.0.0によるPhase 1火炎シーン、移動Sphere Emitter、静的薪コライダー。
- Flow active block、end-to-end更新時間、NanoVDB CPU読み戻し、GPU利用を記録するヘッドレス検証。
- Phase 1の固定フレーム比較キャプチャと判断ゲートを掲載する開発日記エントリ。
- 永続ID、SI寸法、密度・質量、剛体・衝突・減衰を持つPhase 2の動的薪モデル。
- 5本目の薪を追加・持ち上げ・リセットできる最小GUIと、同じ操作を使うヘッドレス経路。
- 固定60 Hzで落下・静止・石囲い内への積層・Emitter追従・Flow稼働を判定するPhase 2検証。
- 落下中と積層後の実画面、物理タイミング、既知の同期コストを掲載するPhase 2開発日記。
- 1本1,152セルの熱伝導、水分蒸発、区分線形熱分解、炭化、炭酸化を扱うPhase 3木材モデル。
- 乾量基準含水率、version付きUSD状態保存、質量保存メトリクス、木材由来Flow燃料入力。
- 乾燥薪と湿潤薪を240秒比較し、CSV・JSON・固定キャプチャを検査するPhase 3ヘッドレスシナリオ。
- 着火遅延、質量収支、性能超過を実測値とともに掲載するPhase 3開発日記。
- 接触・向き・隙間・上方開口・風から酸素係数を求めるPhase 4通気近似。
- 密積みと井桁組みの着火・ガス放出比較、USD注釈、ヘッドレス画像検証。
- 軸断面ごとの残存支持率、炭の低強度近似、局所熱流束、支持喪失判定。
- 事前分割薪のFixedJoint解除、残存質量・コライダー更新、PhysX崩落、通気回復後の再燃検証。
- Phase 5の崩落前後キャプチャ、JSON要約、PowerShell受け入れスクリプト、Web開発日記。
- NISTIR 7094 Table 2の5層合板データを固定したPhase 6A校正参照と、等価クーポン・決定的36候補探索。
- 観測・初期・校正値を比較するUSD棒グラフ、SVGレポート、候補CSV、Phase 6ヘッドレス受け入れスクリプト。
- 合板の係数選択から隔離したNIST OSB外部材料ホールドアウトと、再調整なしの比較SVG・受け入れ判定。
- NISTIR 7094 Appendix Aの合板反復試験をSAMP.1/2選定・SAMP.3検証へ固定分割した、同一材料内の再調整なしホールドアウト評価。
- 公称12.7 mm、0.1 m角、5等厚層、片面加熱を明示し、観測初期質量を保持するPhase 6D平板試験片モデルと層温度SVG。
- 出典付き一次Arrhenius係数を使うPhase 6E見かけ反応と、温度依存速度曲線SVG。
- 同じ未反応木材に競合するガス・タール・チャーの3一次反応、経路別質量・収率追跡、共通倍率16候補探索を行うPhase 6Fモデル。
- NISTIR 4916の材料表に基づく合板・OSB別の熱伝導率と比熱、観測質量由来密度の維持、未解決接着界面を記録するPhase 6G材料プロファイル。
- USDA Wood Handbookの乾燥木材比熱式を材料別基準値へ正規化し、出典範囲280–420 Kへ固定するPhase 6H温度依存比熱モデル。
- NIST Model IIIの係数と固定1秒シナリオで、一次タールを二次ガスと残存タールへ質量保存的に再分類するPhase 6I診断モデル。
- Borosonらの一次実験範囲0.9–2.2秒・773–1073 Kで二次タール生成物分配を比較し、係数選定から隔離するPhase 6J滞留時間感度評価とSVGレポート。
- 完全なSI入力を要求する一次元Darcy気相輸送計算器、合板固有の欠測5入力、滞留時間を保留するPhase 6K結合ゲートとSVGレポート。
- 各層の乾燥木材消費率から未収縮の質量等価熱分解深さを求め、物理炭化層厚さと収縮係数を未確定のまま分離するPhase 6L診断とSVGレポート。
- 34.7 kW/m²・600秒のカバ合板炭化深さ実測を非採点で並べ、10条件中3条件だけの一致から物理厚さへの転用を拒否するPhase 6M外部比較可能性ゲートとSVGレポート。
- 35/70 kW/m²、4中断時刻、3反復の24条件で、厚さ変位・光学/300 °C前線・5層識別情報・質量履歴・不確かさを要求するPhase 6N測定契約、CSV受け入れゲート、SVGレポート。
- 初期面基準座標、DAQ時刻同期、24個のRun ID、質量・温度・表面・イベントの生データテンプレート、3外部承認を要求するPhase 6O実験実施計画とSVGレポート。
- 最初のRun IDへ空のmanifest・生データファイル・証拠ディレクトリを安全に生成し、計測値なし・実行未承認・取込み不可を検証するPhase 6Pオフラインrun-package dry runとSVGレポート。
- 実行情報9項目・外部証拠3件・責任研究室レビュー4項目を空欄で引き渡し、全入力後もリポジトリによる実行許可を拒否するPhase 6Qハンドオフ契約とSVGレポート。
- 物理式・格子・時間刻みを変えず、スカラー熱流束、熱伝導スナップショット、単一走査メトリクス、Flow入力再利用でCPU木材更新を短縮するPhase 6R性能改善、単体ベンチ、比較SVG。
- 起動、CPU木材、集計、Flow写像、Emitter USD、薪表示USD、Kit／Flow更新、画像保存、最終出力を排他的に測り、2 runの中央値と範囲を示すPhase 6S時間内訳レポート。
- CPU木材stepを8つの排他的区間へ分けるオプトイン計測、状態SHA-256不変条件、3 run中央値、相判定・定数比熱ホットパス改善を示すPhase 6T内部プロファイルとSVGレポート。
- 顕熱更新・状態確定をPython AoS、NumPy変換／常駐、Warp CUDA転送／常駐で比較し、毎step転送を含むGPU案を棄却するPhase 6U配列バックエンド境界ベンチマークとSVGレポート。
- coverage付き通常39件とcoverageなしNIST校正1件へ分離し、Kitの300秒上限内で標準40テストと生成API文書検査を復旧するPhase 6Vテスト構成とSVGレポート。
- 顕熱更新と状態確定だけをNumPy化する任意選択のPhase 6W全step経路、400 stepの完全同値ゲート、制御ベンチマーク、Phase 3出力比較、デバッガー混入時間の除外判断、SVGレポート。
- developer bundleをversion lockから除いたPhase 6X測定専用Kitアプリ、debug拡張実行時ゲート、成果物シーン隔離、交互順序2組のPython／NumPy end-to-end比較、Python既定確定レポート、coverageを保つ35＋4＋2件の標準テスト分割。
- debugger-free Phase 3で既定Python木材stepの8区間を3回測定し、顕熱更新を次の候補へ選ぶPhase 6Yオプトイン内部プロファイル、同値ゲート、JSON／SVGレポート。
- 顕熱ループ局所試作のprofile／非計測前後各3 runを分離し、内部5.45%短縮でもend-to-end悪化なら元コードへ戻すPhase 6Z採否ゲートとJSON／SVGレポート。
- 外部面積0の内部セルを境界熱計算から外すPhase 6AA早期分岐、debugger-free交互順序3組の採用ゲート、権威出力の完全一致検査、再現可能なJSON／SVGレポート。
- 乾燥／湿潤薪ごとの温度・質量clamp、相割当、相遷移を通常無効で集計し、性能値から分離するPhase 6AB状態分岐診断とJSON／SVGレポート。
- 温度・4質量の安全境界とNaN／負のゼロ処理を維持した比較分岐、profileと交互順序3組の採用ゲート、20.40%の木材step短縮を含むPhase 6AC。
- 相状態の下流依存監査、公開APIの逐次更新維持、Phase 3最終一回更新、完全な永続出力同値性、交互順序3組の採用ゲートを含むPhase 6AD。
- metrics下流フィールド監査、5値のhot-loop集計、完全な公開metricsと最終要約の維持、交互順序3組の採用ゲートを含むPhase 6AE。
- Thurner–Mannの公開A/E組をSI単位で固定したPhase 6E一次Arrhenius熱分解、48候補探索、温度–速度曲線SVG。

### Changed

- Standardized `Sdf.ChangeBlock` notice coalescing whenever the otherwise opt-in resident lightweight publication path is enabled, while keeping the global resident path off by default and retaining an explicit disable escape hatch.
- Added visible semantic Phase 6P–6AW headings to every recent development-log progress card so milestones remain identifiable outside link metadata and captions.
- Split the fixed-reference and full 180-second air-feedback regressions into dedicated non-coverage processes after two unchanged standard runs hit Kit's fixed 300-second coverage limit; retained collapse coverage, representative thermal/air coverage, all assertions, and all 41 tests.
- Enabled the Phase 6AM inline homogeneous sensible heat-capacity path after a 6.15% median two-log step improvement, 4.29% scenario improvement, 3/3 improving pairs, and exact authoritative outputs; per-cell temperature and mass reads remain uncached.
- Enabled the Phase 6AK step-local homogeneous heat-capacity path after a 13.15% median two-log step improvement, 9.95% scenario improvement, 3/3 improving pairs, and exact authoritative outputs; no coefficient is retained across steps.
- Split the wet-kindling coverage scenario into its own fixed-timeout process and stop it once both ignition events are observed, while retaining evaporation, ignition-order, mass-balance, finite-state, and non-negative-mass assertions; the standard suite remains 41/41 with coverage enabled.
- Enabled the Phase 6AI constant-model heat-capacity path in the standard Python application route after a 7.00% median two-log step improvement and exact authoritative-output checks; no heat-capacity values are cached.
- Split three long-running coverage scenarios into two dedicated Kit test processes after the primary group twice reached its fixed 300-second limit; all 41 checks and their coverage modes remain enabled.
- Moved real-wood, real-flame, laboratory-equipment testing and quantitative experimental calibration out of project scope; Phase 6N–6Q artifacts remain archived design history rather than completion gates.
- MVPのFlow結合方針を、木材状態を正とする一方向結合から開始する方針へ確定。
- アプリの既定シーンをPhase 2へ変更し、薪の権威位置からFlow Emitterを更新する構成へ拡張。
- アプリの既定シーンをPhase 3へ変更し、Flow入力の所有者を木材熱モデルへ移行。
- アプリの既定シーンをPhase 4の積層通気比較へ変更。
- アプリの既定シーンをPhase 5の拘束付き分割薪へ変更。
- アプリの既定シーンをPhase 6の校正結果比較へ変更。

### Notes

- 以下の項目は上流Kit App Templateの変更履歴。

## [110.2.0] - 2026-07-20

### Changed
- Updated to `Kit 110.2.0`
  - [Kit 110.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_2.html)
  - [Kit 110.2 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_2_highlights.html)

### Added
- Added a Testing Applications and Extensions guide (readme-assets/additional-docs/testing_apps_and_extensions.md)

### Fixed
- Hardened the USD Viewer messaging extension: a missing or empty `paths` payload is now a safe no-op, and exception details are no longer returned to the streaming client

## [110.1.2] - 2026-06-24

### Added

- Added the `omni.kit.renderer.ready` extension to the USD Viewer template
  - Emits an `RTX ready` log message once the renderer has finished initializing, making it easier to confirm shader compilation has completed when diagnosing streaming or shader caching issues

### Changed

- Updated to `Kit 110.1.2`
  - [Kit 110.1.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_2.html)

### Deprecated

- Deprecated the `-p` / `--package` option for `repo launch`; it will be removed in a future release. To run a packaged application, decompress the archive and launch the extracted application directly (see Packaging An Application)

### Removed

- Removed the Git LFS prerequisite from the setup instructions; Git LFS is no longer required to clone or use the repository
- Removed the Graphics Delivery Network (GDN) streaming option from the templates

## [110.1.1] - 2026-05-06

### Changed

- Updated to `Kit 110.1.1`
  - [Kit 110.1.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_1.html)
  - [Kit 110.1.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_1_highlights.html)
- `omni.kit.converter.cad` and `omni.kit.window.modifier.titlebar` cross dependency resolved for target platform check

## [110.1.0] - 2026-04-06

### Changed

- Updated to `Kit 110.1.0`
  - [Kit 110.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1.html)
  - [Kit 110.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_highlights.html)
- Templates are now **versioned packages** (`kit_core_templates`, `kit_sample_templates`) pulled as dependencies via packman, replacing the previous git-fetch and in-repo template model
  - Packages are declared in `tools/deps/repo-deps.packman.xml` and resolved into `_repo/deps/`
  - Template discovery uses `LocalTemplateCollection` pointing at package paths in `base_project/templates/templates.toml`
  - Existing workflows (`repo template new`, template selection UI) are unchanged
- Project directories now contain only your code and configuration; template content stays in `_repo/deps/` as external, versioned packages — giving a clear separation between your project files and template boilerplate

## [110.0.0] - 2026-03-05

### Changed

- Update to `Kit 110.0.0`
  - [Kit 110.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_0.html)
  - [Kit 110.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_0_highlights.html)
- Updated `stage_management.py` in `usd_viewer.messaging` extension template to make prims selectable in viewport and updated `omni.usd.StageEventType` to `ASSETS_LOADED` to fix camera exposure when resetting the camera in Web-Viewer-Sample front-end client.

## [109.0.3] - 2026-01-26

### Changed

- Update to `Kit 109.0.3`
  - [Kit 109.0.3 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_3.html)

## [109.0.2] - 2025-12-18

### Changed

- Updated to `Kit 109.0.2`
  - [Kit 109.0.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_2.html)

## [109.0.1] - 2025-12-04

### Added

- Kit added support for ARM64

### Changed

- Updated to `Kit 109.0.1`
  - [Kit 109.0.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_1.html)
  - [Kit 109.0.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_1_highlights.html)
- Tooling in tools/repoman was upstreamed to `repo_kit_tools`
- `repo package_container` replaces `repo package --container`
- `repo package` is now mapped to the `repo_package_app` tool in `repo_kit_tools`. It still uses the repo_package configuration in our repo.toml.
- Containerization files in tools/containers have been removed. They are now generated in an automated fashion during containerization by `repo package_container --app ${path_to_kit_file}`. You can generate and not containerize by running `repo package_container --app ${path_to_kit_file} --generate`
- Default image tag name changed from `kit-app-template:latest` to `appname:latest`. eg: `usd-viewer_nvcf:latest`
- Container `--name` updated to `--image-tag` supporting both image name and image tag `--image-tag [container_image_name:container_image_tag]`
- Updated required driver version `>=550.54.15` (Linux) or `>=551.78` (Windows).

### Deprecated

- tools/containers `entrypoint_memcached.sh.j2` now migrated to generated `entrypoint.sh`
- tools/containers `kit_args.txt` now migrated to generated `entrypoint.sh`
- tools/containers `Stream_sdk.txt` now migrated to generated `Dockerfile`

### Known Issue

- Basic C++ w/ Python Binding Extension test fails due to test environment configuration

## [109.0.0] - 2025-11-18

### Added

- Added new Livestream extensions `omni.kit.livestream.aov` and `omni.services.livestream.webrtc`

### Changed

- Updated to `Kit 109.0.0`
  - [Kit 109.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0.html)
  - [Kit 109.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_highlights.html)
  - `useFabricSceneDelegate = true` removed. Fabric Scene Delegate (FSD) is now enabled by default in Kit 109.0. Applications no longer need to explicitly enable FSD in `.kit` configuration files.
  - `auto_load_usd` for USD Viewer now supports relative paths
  - Set custom orientations for `UsdLux 25.05` for Y-up and Z-up stages in USD Explorer template and set `inputs:normalize = true` on that template's distant light.

## [108.1.0] - 2025-10-06

### Added

- Added `omni.kit.primitive.mesh` extension to Kit Base Editor and USD Explorer Templates to enable Create Mesh in viewport by default
- Added `omni.hydra.usdrt_delegate` extension to Kit Base Editor as dep needed for `useFabricSceneDelegate=true`

### Changed

- Updated to `Kit 108.1.0`
  - [Kit 108.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_1.html)
  - [Kit 108.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_1_highlights.html)

### Deprecated

- Deprecated `omni.kit.ngsearch` extension, no longer available after Kit 108

## [108.0.0] - 2025-08-12

### Changed

- Updated to `Kit 108.0.0`
  - [Kit 108.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_0.html)
  - [Kit 108.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_0_highlights.html)
- Changed "Omniverse Cloud Streaming" application layer to "NVCF Streaming" to align underlying technology and use case.
- Updated streaming extensions to `omni.kit.livestream.app` and `omni.services.livestream.session` to support NVCF Streaming.
- Removed omni.services.transport.server.http.port overrides.  Aligned all template applications to use default ports.
- Updated repository documentation to reflect changes in streaming changes.
- Updated crash reporter settings to compress crash reports.
- Update Windows `omni.kit.window.modifier.titlebar` extension version 
- Update repo tooling to most recent versions
- Updated application icon images for Composer and Explorer templates
- Enabled testing for USD Viewer Template messaging extension

### Fixed

- Fix duplicate key `.kit` file issues related to `settings.app.exts`

## [107.3.0] - 2025-05-27

### Added

- Added `repo template modify` tooling enabling developers to add Template Layers to existing applications created with 107.3 or newer.

### Changed

- Updated to `Kit 107.3.0`
  - [Kit 107.3 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_3.html)
  - [Kit 107.3 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_3_highlights.html)
- Updated packman version to 7.29 to address customer issues with network restrictions [Issue #80](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/80)

## [107.2.0] - 2025-05-05

### Added

- Added tooltip information to the VSCode debug extensions to clarify usage.
- Added tooling checks for path whitespace and OneDrive paths to improve developer experience.

### Changed

- Updated to `Kit 107.2.0`
  - [Kit 107.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_2.html)
  - [Kit 107.2 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_2_highlights.html)
- Remove hard .git dependency from tooling
- Exclude `_repo` from packaging operations.

### Fixed

- Fixed nondeterministic tool loading behavior raised in [Issue #65](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/65)
- Addressed spelling errors raised in [Issue #63](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/63)
- Addressed default repository definition causing issues with bootstrapping thin packages from [Issue #70](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/70)

## [107.0.3] - 2025-03-26

### Fixed

- Fixed issues with run time available registries by adding them directly to `.kit` templates
- Fixed issues with test time available registries by adding user.toml registry configurations

## [107.0.3] - 2025-03-20

### Added

- Added the ability select of application layers (streaming configurations) individually during templating
- Added a dedicated streaming configuration for NVCF based Omniverse Cloud (OVC) deployments
- Added C++ With Python Extension Template and Documentation
- Added streaming application creation and configuration documentation
- Added Developer Bundle extension by default to Base Editor, Composer, and Explorer templates
- Added an exclusion for Developer Bundle on streaming application layers

### Changed

- Updated to `Kit 107.0.3`
  - [Kit 107.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_0.html)
  - [Kit 107.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_0_highlights.html)
  - Updated repo tooling UX to clarify tool use and improve user experience
  - Changed previous Omniverse Cloud (OVC) streaming configuration to Omniverse Cloud Streaming (Legacy)
  - Updated to `Cad Converter 203.0.0` Release
    - [Cad Converter Release Notes](https://docs.omniverse.nvidia.com/extensions/latest/ext_cad-converter/release-notes.html)
  - Moved extension `type` declaration to the extension definition section within the templates.toml file
  - Removed `omni.usd.fileformat.sbasar` and `omni.kit.property.sbsar` extensions from the USD Composer Template kit file. The extensions will be available at a later date.

### Fixed

- Fixed Windows long path issues during `repo package`

## [106.5.0] - 2024-12-12

### Added

- Added `app.environment` name setting for all kit file templates

### Removed

- Removed `WALK_VISIBLE_PATH` from USD Explorer Setup Extension

### Changed

- Updated to `Kit 106.5.0`
  - [Kit 106.5 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_5.html)
  - [Kit 106.5 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_5_highlights.html)
- Updated Asset browser URLs
- Optimized OVC streaming file kit settings for OVC streaming deployments

### Fixed

- Updated Editor tutorial away from deprecated methods to use action based method for show/hide of menus

## [106.4.0] - 2024-11-18

### Added

- Added `stream_sdk.txt` to set timeout for stream SDK and updated container packaging to add it to container images
- Added `replay` to the `template new` tooling to allow for replaying app and extension creation to support automation
- Added companion tutorial section for using python pip packages

### Changed

- Updated to `Kit 106.4.0`
  - [Kit 106.4 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_4.html)
  - [Kit 106.4 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_4_highlights.html)
- Updated the `omni.kit.asset.browser` extension URLs to point to current asset libraries when not specified in Kit file
- Updated to `Cad Converter 202.0.0` Release
  - [Cad Converter Release Notes](https://docs.omniverse.nvidia.com/extensions/latest/ext_cad-converter/release-notes.html)

### Fixed

- Added missing notification of successful build `BUILD (RELEASE) SUCCEEDED` for Python only builds for Windows

## [106.3.0] - 2024-11-07

### Removed

- Removed the USD Viewer setup samples folder and the light_rigs folders from the USD Composer and USD Explorer setup templates. That data is now accessible from the `omni.usd_viewer.setup` and `omni.light_rigs` extension dependencies.

## [106.3.0] - 2024-11-04

### Added

- Built app containers support `NVDA_KIT_ARGS` and `NVDA_KIT_NUCLEUS` environment variables
  - `NVDA_KIT_ARGS` is passed directly into the kit executable
  - `NVDA_KIT_NUCLEUS` if set causes the container entrypoint to create an omniverse.toml configuration file with a single entry pointing at the provided nucleus server. This will also set the kit arg --/ovc/nucleus/server with the envvar value.
  - `repo launch --container` maps in these variables from the local environment as well
- Added `omni.kit.menu.common` to Kit Base Editor, USD Composer, and USD Explorer Template Kit files to enable Toggle Viewport Fullscreen and UI overlay with F7 and F11

### Changed

- Updated to `Kit 106.3.0`
  - [Kit 106.3 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_3.html)
  - [Kit 106.3 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_3_highlights.html)
- Updated build process to support auto-detection or user-specified host versions of `MSVC` and `WinSDK`, providing flexibility for Windows C++developers to leverage their existing installations. [Windows C++ Developer Configuration](readme-assets/additional-docs/windows_developer_configuration.md)
- Updated `omni.kit.usd_explorer.main.menubar` to version 1.0.38 so that it works correctly with `omni.kit.menu.common`
- Moved Light Rig binary data from kit-app-template repo to `omni.light_rigs` extension and added the extension to Kit Base Editor, USD Composer, and USD Explorer Template Kit files
- Moved USD Viewer sample assets from kit-app-template repo to `omni.usd_viewer.samples` extension and added the extension USD Viewer Template Kit file
- Moved Kit Service Template to bottom of Application list
- BUILD (RELEASE) SUCCEEDED message not supported for all build configurations

### Removed

- Removed Services dependencies from USD Composer Template that caused a firewall popup on first launch

## [106.2.0] - 2024-10-03

### Changed

- Updated to `Kit 106.2.0`
  - [Kit 106.2 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_2.html)
  - [Kit 106.2 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_2_highlights.html)
- Refactored Viewer Template default tests to avoid unnecessary dependencies

### Removed

- Unused `simulation` menu item from USD Composer Template

## [106.1.0] - 2024-09-18

### Added

- Support for containerization of streaming applications and services via `repo package --container`
- Support extension only builds via `repo build`
- Support the ability to launch created containers via `repo launch --container`
- repo_usd tooling dependency
- Support for USD Viewer Template to send scene loading state to client via messaging

### Changed

- Updated to `Kit 106.1.0`
  - [Kit 106.1 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_1.html)
  - [Kit 106.1 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_1_highlights.html)
- Aligned default testing for applications and extensions
- Update and align code formatting/style across templates

### Fixed

- Extra setup extensions appear in standard extension template menu
- "Could not find cgroup memory limit" error during build
- Fixed default manipulator pivot back to "bounding box base" in USD Explorer Template

## [106.0.3] - 2024-09-18

### Changed

- Updated to `Kit 106.0.3`
  - [Kit 106.0.3 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_3.html)

## [106.0.2] - 2024-07-29

### Added

- Support for local streaming configurations for UI based Applications
- Support for multiple setup extensions per application
- Ability to pass arguments to Kit via the `repo launch` tool
- USD Composer Application Template and Documentation
- USD Viewer Application Template and Documentation
- USD Composer Setup Extension and Documentation
- USD Viewer Setup Extension and Documentation
- Repository Issue Templates Bug/Question/Feature Request
- Omniverse Product-Specific Terms (PRODUCT_TERMS_OMNIVERSE)
- Support for type ordering in templates.toml
- Metrics Assembler to Kit Base Editor Template to support unit correct assets
- Support for automatic launch if only single `.kit` file is present in `source/apps`

### Changed

- Updated to `Kit 106.0.2`
  - [Kit 106.0.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_2.html)
  - [Kit 106.0.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_1.html)
- Updated all relevant application templates READMEs to reflect the addition of local streaming configurations
- Updated .gitattributes to ensure LFS is used for all relevant file types
- Updated .gitignore to exclude streaming app event traces
- Updated .vscode/launch.json to better support debugging behavior
- Updated LICENSE to separate NVIDIA License from Omniverse Product-Specific Terms
- Updated top level README.md to reflect additional templates and improve documentation clarity
- Updated Developer Bundle extension availability and corresponding documentation
- Updated public extension registry to reflect current Kit 106 registry location
- Updated templates.toml to support multiple setup extensions and new templates

## [106.0.0] - 2024-06-07

### Added

- Kit Base Editor Application Template and Documentation
- USD Explorer Application Template and Documentation
- USD Explorer Setup Extension and Documentation
- Kit Service Template and Documentation
- Simple Python Extension Template and Documentation
- Simple C++ Extension Template and Documentation
- Python UI Extension Template and Documentation
- Template configuration file (templates.toml)
- Added local `repo launch` tool for launching applications and fat packages directly
- Added local `repo package` functionality to improve package naming
- Omniverse EULA acceptance to Kit App Template via tooling
- tasks.json for better VSCode support
- SECURITY.md for security policy
- Notice for data collection and use
- Early access Developer Bundle extensions
- Kit App Template related Developer Bundle documentation (developer_bundle_extensions.md)
- Kit App Template related repo tools documentation (kit_app_template_tooling_guide.md)
- Usage and troubleshooting documentation for Kit App Template (usage_and_troubleshooting.md)
- repo_tools.toml to configure local repo tools

### Changed

- Updated to `Kit 106.0.0`
  - [Kit 106.0 Beta Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0.html)
  - [Kit 106.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_highlights.html)
- Updated repo_kit_template tooling to support Applications and Extensions
- Updated repo_kit_template tooling to allow for application setup extensions
- Updated top level README.md to reflect updated tooling and templates
- Updated LICENSE.md to reflect updated tooling and templates
- Updated .gitattributes to reflect use of templates rather directly from source
- Added configuration to repo.toml to support new tools and templates

### Removed

- Top level build .bat/.sh scripts in favor of using `repo build` directly
- Predefined `define_app` declarations from `premake5.lua` in favor of developer defined applications
- Predefined source/apps in favor of templates for developers to build from

