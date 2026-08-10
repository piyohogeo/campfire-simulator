# Phase V3T-R — production / Python debug split candidate

## Decision

The proposed dependency split is **not promoted** in this phase. A production-neutral derived-app matrix proved that removing `omni.kit.developer.bundle` and its debug startup path restores normal-app performance, while a separate localhost-only developer composition preserves debugpy and VS Code attachment. However, the final explicit V3-OFF regression attempt ended in a native `0xC0000005` during Kit quick shutdown. The requested crash/dump-zero gate therefore did not pass, so `campfire.simulator.kit` remains unchanged.

The invalid run is not part of the performance population and was not automatically repeated. Its dump remains local under `artifacts/` and is not tracked by Git.

## Candidate architecture

`run_phasev3tr_debug_split.ps1` derives two temporary apps under the requested artifact directory:

- production candidate: the built normal app with the developer bundle and its three generated lock entries removed;
- developer candidate: a small composition over that production candidate plus `omni.kit.developer.bundle`, with debugpy listening only on `127.0.0.1:3000` and without waiting for a client.

The real benchmark app remains the debugger-free control. Derived apps and production app hashes are recorded, and no repository app is edited during the measurement. A future promotion must add an explicit developer `.kit` and launcher only after all lifecycle gates pass.

## Observed performance

All formal processes used Kit 110.2, Flow 110.0.0, RTX Real-Time 2.0, Candidate Performance, DLSS Performance, two bounces, 1280x720, CPU-source Wood Visual V3, the same Phase 3 authority/seed/camera, persistent settings OFF, user config OFF, and the unchanged 210 W power limit. Capture, encode, additional RenderProduct, and HydraTexture were excluded.

| Condition | Runs | Mean visible FPS | Derived frame time | GPU | Power | VRAM |
|---|---:|---:|---:|---:|---:|---:|
| derived normal, debugger-free | 3 | 50.231 | 19.924 ms | 17.21% | 151.71 W | 3594 MiB |
| explicit developer | 3 | 30.525 | 32.772 ms | 14.13% | 143.30 W | 4099 MiB |
| benchmark | 3 | 50.488 | 19.808 ms | 17.48% | 151.46 W | 3604 MiB |

The derived normal gained `18.021 FPS` over the V3T-Q normal-with-developer baseline (`32.211 FPS`) and was only `0.257 FPS` below benchmark. The developer composition retained the known approximately-30-FPS debug cost; this is not a production failure.

Each formal condition retained identical dry/wet authority SHA-256 values, mass-balance error `0`, CPU-source V3 publication counts (`603` observations, `868` uploads, `99` quantized skips, `504` visual commits per run), and nonzero Flow active blocks. Normal and benchmark loaded none of the nine developer extensions and opened no debugpy listener. Developer loaded all nine and opened exactly one localhost listener.

Two separate visible-window runs showed `49.185 FPS` for the debugger-free candidate and `31.457 FPS` for the developer candidate. Viewport/UI/RTX/V3/Flow startup and clean close completed. The camera manipulator extension was present, but automated user-input camera manipulation could not be performed in this environment; this remains an unqualified UI detail.

The FPS metric is the public `ViewportAPI.frame_info` visible-render counter. Display-present FPS, GPU render time, and raw render-frame percentiles were not available and are not inferred.

## Native crash evidence

One non-formal explicit V3-OFF run completed its scenario but crashed during quick shutdown:

- Windows exception: `0xC0000005`, write to `0xD0`;
- fault location: `usd_usdGeom.dll+0x7A171`;
- low-confidence boundary: UsdGeom / `UsdContext::unregisterViewOverrideToHydraEngines` / timeline / Kit quick shutdown;
- local compressed dump: 1,576,253 bytes, SHA-256 `E0734E2FA7A3E590AA6724F81AE4BAC6E387F990E053835D2F42B041E78701DC`;
- automatic upload: `0` (`uploadDumpsOnStartup=false`, old-dump upload skipped, upload URL empty, metadata `UploadSuccessful=0`);
- GPU texture transport: not active.

This resembles the earlier V3T-F shutdown boundary but has a different measured module offset from the V3T-L Fabric crashes. Without WinDbg/CDB, matching private symbols, and an authoritative unwind, neither the dependency split nor V3 OFF is established as the cause. The dump itself, log, and raw analysis remain outside Git.

## Safety boundary and next step

Production V3 ON, Candidate Performance, Flow 110.0.0, Sphere Emitter default, Point/rigid defaults, wood authority, physics, collision, checkpoint, rollback, serialization, CPU texture transport, and the V3T-M Flow-topology safe stop are unchanged. No new video is produced because the candidate changes startup overhead only; the verified V3T-P latest demo remains current.

Reopen promotion only after an isolated teardown probe distinguishes stage/Hydra/timeline close ordering from the candidate dependency split, produces a crash-free explicit V3-OFF result, and completes actual camera-input UI smoke. Do not treat a successful retry alone as erasing this incident.

Machine-readable evidence is in `docs/devlog/assets/phasev3tr/`.

Final unchanged-production regressions passed: Release build `8.34 s`, Phase 0 RTX `22.8 s`, and the complete standard suite `8` processes / `78` tests in `324.2 s` (collapse coverage `189.3 s`). An earlier suite attempt whose outer supervisor timed out after only 75 current-run tests was discarded and rerun from the beginning.
