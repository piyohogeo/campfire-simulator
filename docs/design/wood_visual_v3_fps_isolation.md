# Phase V3T-I visible viewport FPS isolation

## Decision boundary

Phase V3T-I is a production-neutral measurement phase based on commit `a014058`. It changes no production setting or default. Wood authority, Flow inputs, Point/Sphere emitters, collision, rigid layout, checkpoint, and serialization remain unchanged.

The accepted path observes only the existing visible viewport through public `ViewportAPI.frame_info` / `fps`. It creates no additional RenderProduct or HydraTexture and performs no capture or encoding in the measured population. Every run is rejected immediately if its log contains even one `IRenderSettings::getRenderSettings failed getting a stage-id` message.

## Frame-limit inventory

The fixed Kit 110.2 runtime reported:

| Setting | Effective value |
|---|---:|
| main loop rate limit | enabled, 120 Hz |
| rendering loop rate limit | enabled, 120 Hz |
| present loop rate limit | enabled, 59 Hz |
| main/rendering/present syncToPresent | true |
| `/app/vsync` | false |
| `/renderer/vsync` | false |
| viewport default tick rate | 120 Hz |
| simulation minimum frame rate | 30 Hz |

Thus the 59 Hz present loop limits the 640x360 result, but it cannot explain the roughly 32 FPS result at 1280x720 or the roughly 24 FPS Flow result. The empty stage reaches about 72 visible frames/s because this counter is a render counter, not display-present FPS.

The RTX 3090 reported an enforced 210 W limit versus a 350 W default limit: exactly 60%. No power-setting command was issued, and no 100% comparison belongs to this phase.

## Method

The first full preflight detected that the command-line Flow OFF value was restored to the application default during extension startup. The Emitter was disabled and active blocks were absent, but that was not accepted as an exact Flow OFF setting. The probe was changed to reapply the public `/rtx/flow/enabled` setting after startup and again after warmup. Both the pre-measurement and post-measurement values must match the condition or the run is rejected.

All formal conditions used a fixed camera, 20 logs where applicable, one RTX 3090, 30 seconds of warmup, 30 seconds of measurement, and three separate Kit processes with rotated order. `nvidia-smi` sampled GPU utilization, graphics/SM/memory clocks, VRAM, power, temperature, power limit, P-state, and active throttle-reason mask every 250 ms. The runner never changes the power limit.

Short preflight was sufficient to reject reflection, indirect lighting, realtime OptiX denoiser, and Editor UI visibility as dominant factors. Formal repetition was restricted to the six classification conditions.

## Results

| Condition | Visible FPS mean | HUD FPS mean | Kit updates/s | Timeline sim/wall | GPU util | Mean power | Max VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|
| empty stage, RTX RT 2.0 | 71.969 | 71.970 | 71.957 | 1.000 | 3.18% | 134.34 W | 4255 MiB |
| 20 logs, Flow OFF, V3 OFF, 1280x720 | 31.807 | 31.822 | 33.418 | 0.557 | 85.16% | 209.14 W | 4969 MiB |
| same, 640x360 | 59.978 | 59.968 | 59.967 | 0.999 | 46.14% | 208.70 W | 4466 MiB |
| same, 1920x1080 | 27.150 | 27.145 | 30.781 | 0.513 | 100.00% | 209.41 W | 5241 MiB |
| Flow simulation only | 24.080 | 24.080 | 28.032 | 0.467 | 100.00% | 209.29 W | 6716 MiB |
| Flow simulation + volume | 24.101 | 24.091 | 27.922 | 0.465 | 100.00% | 209.21 W | 6702 MiB |

The strict Flow-OFF auxiliary preflight measured 32.499 FPS with reflection disabled, 32.536 FPS with indirect diffuse disabled, 32.465 FPS with the realtime OptiX denoiser enabled, and 32.637 FPS with Editor UI hidden. These one-run values are screening results, not formal three-run estimates.

All 18 formal processes completed with zero stage-ID errors. All formal GPU-heavy conditions were at or near the 210 W enforced limit. `PerfCap Reason` is retained as the raw NVIDIA active-bit mask in the sample JSON; it is not translated into an unsupported causal claim.

## Classification

Observed facts:

- Reducing the pixel count from 1280x720 to 640x360 improves visible throughput by 88.6% and reaches the 59 Hz present-loop boundary.
- Increasing to 1920x1080 lowers throughput by 14.6% and holds GPU utilization at 100%.
- Empty RTX is much faster than the 20-log stage, so a global 30 FPS cap is not the cause.
- Reflection, indirect diffuse, denoiser, and UI toggles do not materially change the preflight result.
- Flow simulation-only and Flow simulation plus volume differ by only 0.021 FPS in the formal aggregate.

Strong inference:

- Under the unchanged 60% power limit, the current stage is primarily pixel/GPU limited.
- Flow activation adds substantial GPU work, but the additional volume-render Prims are not the dominant difference in this fixed scene. The result does not separate solver kernels from other Flow GPU work.

Unconfirmed:

- Per-pass ray-tracing, denoiser, and Flow GPU time. A GPU profiler was not run because the public viewport and telemetry measurements already classified the dominant scaling and profiler overhead would require a separate population.
- Display-present FPS and compositor timing.
- Raw visible render-frame completion timestamps, frame latency, p95/p99, and 1% low. Kit 110.2 exposes a monotonic counter and smoothed HUD FPS for the existing viewport, not a safe public raw completion timestamp. Poll intervals are not substituted for render-frame intervals.
- Performance at a 100% power limit.

## Reproduction and evidence

```powershell
.\scripts\run_phasev3ti_settings.ps1
.\scripts\run_phasev3ti_fps_isolation.ps1 -Mode Preflight -WarmupSeconds 20 -MeasureSeconds 10
.\scripts\run_phasev3ti_fps_isolation.ps1 -Mode Formal -Runs 3 -WarmupSeconds 30 -MeasureSeconds 30 -Conditions empty_rtx,current_flow_off,resolution_640x360,resolution_1920x1080,flow_simulation_only,flow_volume
```

The accepted raw samples, settings inventory, aggregate JSON, and SVG are in `docs/devlog/assets/phasev3ti/`. No profiler trace, image, or video is part of the performance population.
