# Phase V3T-Q: normal / benchmark FPS boundary

## Scope and safety boundary

This Phase explains the previously observed normal-app `30.528 FPS` versus benchmark `50.312 FPS` gap. It does not reassess Wood Visual V3 and does not change either production `.kit` file, rendering rates, V3 defaults, Flow input, emitters, wood authority, physics, collision, checkpoint, rollback, or serialization.

All formal runs used the production-equivalent Phase 3 scene, Candidate Performance, RTX Real-Time 2.0, DLSS Performance, `maxBounces=2`, CPU-source Wood Visual V3 ON, 1280×720, `--no-window`, no persistent/user configuration, and the unchanged 210 W enforced power limit. Capture, encoding, added RenderProducts, and added HydraTextures were absent. The four conditions ran in separate processes and rotated order across three runs.

## Formal result

| Isolated derived app | Developer bundle | Visible FPS mean (min–max) | Derived frame time | GPU utilization | GPU power |
|---|---:|---:|---:|---:|---:|
| `normal_baseline` | yes | 32.211 (31.241–33.804) | 31.083 ms | 19.31% | 146.25 W |
| `normal_without_developer_bundle` | no | 55.427 (54.230–56.102) | 18.046 ms | 37.62% | 188.71 W |
| `benchmark_with_developer_bundle` | yes | 31.998 (30.874–33.689) | 31.297 ms | 18.77% | 145.54 W |
| `benchmark_baseline` | no | 56.241 (55.637–56.911) | 17.782 ms | 38.41% | 189.06 W |

Removing the bundle from normal gains `23.216 FPS`; adding the same bundle to benchmark loses `24.243 FPS`. After removing it, the normal/benchmark residual is only `-0.814 FPS`; with it present, the residual is `+0.213 FPS`. The app root does not explain the original ~20 FPS gap.

The low-FPS class also uses roughly half the GPU utilization and about 43 W less power. The qualified boundary is therefore CPU/lifecycle-side rather than pure GPU saturation. This does not identify a single internal callback duration.

Main update timing is measured by the existing `next_update_async()` segment, after four warmup samples:

| Condition | update mean | p50 | p95 | p99 | mean max across runs | derived update rate |
|---|---:|---:|---:|---:|---:|---:|
| normal + developer | 6.716 ms | 5.794 | 6.758 | 8.447 | 204.755 ms | 152.81 Hz |
| normal − developer | 5.200 ms | 4.906 | 6.012 | 11.340 | 32.980 ms | 192.54 Hz |
| benchmark + developer | 6.707 ms | 5.835 | 6.783 | 8.311 | 192.640 ms | 153.00 Hz |
| benchmark − developer | 5.017 ms | 4.944 | 5.903 | 6.704 | 7.779 ms | 199.32 Hz |

The large mean-max values in developer run 3 come from one >500 ms sample in each condition; p99 remains below 9 ms. These update-segment values are not raw renderer frame intervals.

V3 behavior stayed structurally consistent: each run recorded 603 publications, 868 uploads, and 99 quantized skips. Aggregate V3 total p95 was `9.024–10.497 ms`; CPU-source upload p95 was `8.401–9.551 ms`. Flow active blocks remained nonzero. The FPS diagnosis is not a V3 transport requalification.

## Extension set boundary

The bundle adds the same nine runtime extensions to either app root (package self-IDs excluded):

- `omni.kit.debug.python-1.0.2`
- `omni.kit.debug.settings-1.0.3`
- `omni.kit.debug.vscode-0.1.7`
- `omni.kit.dev.utilities.bundle-0.2.1`
- `omni.kit.developer.bundle-0.2.0`
- `omni.kit.widget.text_editor-1.1.1`
- `omni.kit.window.commands-0.2.9`
- `omni.kit.window.extensions-1.5.13`
- `omni.kit.window.script_editor-2.0.9`

The derived no-developer normal and benchmark baselines have the same 198 non-self extension IDs. Bundle conditions have 207. Full IDs, versions, and startup order for every process are retained in `app_path_fps_samples.json`.

The public extension-manager surface did not expose per-extension update subscriptions or callback duration. Local bundled source confirms that `omni.kit.debug.python` invokes `debugpy.listen()` at startup with its default listen mode; the extension itself does not register a Kit update callback in that wrapper. The internal debugpy/pydevd hook cost was not profiled, so it is not named as a specific callback.

## Focused probes

| Normal no-developer base plus | Visible FPS | Debug server listen observed |
|---|---:|---:|
| nothing | 55.126 | no |
| Python debug extension, listen disabled | 56.010 | no |
| Python debug extension, default listen | 30.832 | yes |
| VS Code debug path | 31.551 | yes |
| debug settings | 53.544 | no |
| developer window group | 56.048 | no |
| developer utilities bundle | 31.444 | yes |

This isolates `debugpy.listen()` as the minimum identified cause boundary. Loading the same Python debug extension without starting the server retains the fast class. The strong inference is debugger instrumentation/tracing on the CPU side; the exact debugpy internal mechanism remains unconfirmed.

## Scheduler and timeline observations

No condition had an explicit 30 Hz main, render, present, or viewport rate:

- main rate limit enabled; warmup value is 60 Hz in no-developer conditions
- rendering rate limit enabled at 120 Hz
- present rate limit enabled at 59 Hz
- viewport tick 120 Hz
- simulation minimum 30 Hz in all conditions
- global sync-to-present false; loop sync-to-present true
- renderer and app VSync false

The common simulation-minimum value of 30 does not discriminate the low-FPS conditions. Read-only setting-change observation saw common startup changes to sync-to-present and the 59 Hz present rate. The public settings event does not identify the writer.

The in-coroutine warmup snapshot additionally observed that no-developer conditions entered timeline PLAY and changed main to 60 Hz, whereas the two debugpy-listening conditions were already non-PLAY with main returned to 120 Hz at the same checkpoint. This is a real lifecycle correlation, but it does not explain the lower FPS by itself and is not attributed to a private Kit/debugpy implementation without profiler evidence.

## Visible-window confirmation

The two short UI runs were kept outside the formal population. Normal baseline measured `31.182 FPS`; derived normal without the developer bundle measured `55.458 FPS`. The same separation persists when the application window is visible, so hidden panels are not required to reproduce the loss.

HUD FPS was not programmatically available in `--no-window` runs. The reported FPS is the existing visible viewport `ViewportAPI.frame_info` render counter; the displayed frame time is `1000 / FPS`. Display-present FPS, GPU render time, raw renderer frame intervals, and per-extension callback times remain unmeasured and are not inferred.

## Regression qualification

The final Release build and Phase 0 RTX gate passed. Production normal and benchmark Phase 3 runs also passed with Candidate Performance and the production V3 default inherited. Dry and wet authority SHA-256 values matched between the two app roots, both mass-balance errors were `0`, Flow active-block peaks were `298 / 328`, and fatal-token and dump counts were zero. The standard suite passed all `78 / 78` tests in eight processes (`334.3 s`, including `192.3 s` collapse coverage).

## Decision and recommended next Phase

Observed fact: the original normal/benchmark gap follows the developer bundle and narrows to under 1 FPS without it. Focused evidence identifies the default `debugpy.listen()` path as the minimum reproducing factor. No 30 Hz rate-setting explanation was found.

Recommended change, not performed here: remove `omni.kit.developer.bundle` from the production normal app and offer a separate explicit developer/debug preset. That Phase must preserve an intentional interactive debugging route and rerun normal startup, visible UI, Phase 0, Phase 3, and the standard suite before changing the production dependency.

## Evidence

- `docs/devlog/assets/phasev3tq/app_path_fps_samples.json`: formal, focused, visible, scheduler samples; extension IDs and startup order
- `docs/devlog/assets/phasev3tq/app_path_fps_report.json`: aggregated result and classification
- `docs/devlog/assets/phasev3tq/app_path_fps_report.svg`: human-readable comparison
- `docs/devlog/assets/phasev3tq/regression_report.json`: final Release, RTX, production Phase 3, and standard-suite qualification
- `scripts/prepare_phasev3tq_app_variants.py`: reproducible derived `.kit` construction
- `scripts/run_phasev3tq_app_path_fps.ps1`: process isolation, crash safety, GPU telemetry, and hash gates
- `scripts/analyze_phasev3tq_app_path_fps.py`: deterministic report generation
