# Phase V3T-H visible-viewport FPS boundary

## Decision

Phase V3T-H measures average render throughput from the existing visible viewport only. It does not create a second `HydraTexture` or `RenderProduct`, and it does not report render-frame p95/p99, 1% low, or display-present FPS. Production modules and defaults remain unchanged. GPU ring3 is excluded because Phase V3T-G did not establish the required repeated final lifecycle safety gate.

## Rejected first measurement path

The first probe copied the active viewport `RenderProduct` into the session layer and attached a dedicated public `HydraTexture`. All nine formal Kit logs contained:

```text
[Error] [omni.rtx] IRenderSettings::getRenderSettings failed getting a stage-id
```

The count reached 14,067 lines before the runner was stopped. Normal process exit was therefore not a valid render-path gate. Those results and all earlier V3T-H smokes were moved under `artifacts/phasev3th-invalid-renderproduct-stage-id-20260810/` and are never read by the accepted analyzer. The copied-RenderProduct approach was removed.

The runner now follows each Kit log while the process is active and stops immediately on the first stage-ID error. It scans again after exit, rejects any run with one or more occurrences, and also rejects Traceback, CUDA illegal address, device lost, invalid pointer, and ImageProvider argument failures. A zero process exit code alone is insufficient.

## Public API audit

Before the corrected FPS run, `omni.stats.IStats.get_scopes()` and `get_stats_nested()` enumerated all public scopes and nodes in the fixed Kit runtime. The inventory contains 13 scopes and 274 nodes:

- DDL
- GPU CUDA Memory v2: GPU0
- GPU Memory
- GPU Memory : GPU0
- GPU Memory v2: GPU0
- GPU Pipelines
- Host CUDA Memory v2: GPU0
- Host Memory v2: GPU0
- RTX Material
- RTX Scene
- TextureStreaming
- UJITSO
- UJITSORequestQueue

No node name referred to FPS or frame timing, and no numeric series matched either the visible HUD FPS or `1000 / FPS` within 0.05. Thus `omni.stats` does not expose the visible viewport FPS in this runtime.

The bundled `omni.kit.viewport.window` 110.0.0 source shows that the upper-right HUD reads public `ViewportAPI.fps`, rounds it to two decimals, and displays frame time as `1000 / FPS`. `ViewportAPI.fps` itself reads `ViewportAPI.frame_info["fps"]`. The same public `frame_info` dictionary exposes a monotonic visible `frame_number`.

## Accepted metric contract

- Average visible render FPS is `(final frame_number - initial frame_number) / measured wall seconds`.
- The HUD value is sampled from public `ViewportAPI.fps` into a fixed memory buffer and reported only as an overlay-level mean/min/max observation.
- The displayed HUD frame time is a reciprocal of its FPS value, not a raw frame duration.
- Poll timestamps are Kit-update observation times. They are not render-completion timestamps.
- The fixed runtime exposes no public raw completion timestamp or event mapped safely to the existing visible viewport. Therefore render-frame p50/p95/p99/max, 1% low, publication/non-publication frame intervals, and 16.67/33.33/50/100 ms render-frame counts are explicitly unmeasured.
- Display compositor/present timing is also unmeasured, so the result is not called display-present FPS.

## Fixed measurement

- Kit 110.2, Flow 110.0.0, RTX 3090, one GPU.
- 20 logs, fixed camera, 1280×720, fixed RTX settings and Flow block limit.
- 30-second warmup and 60-second population per formal process.
- Three independent runs with rotated condition order.
- Flow OFF / V3 OFF; Flow ON / V3 OFF; Flow ON / V3 CPU-source.
- V3 publication cadence 5 Hz; 903 measured publications in total.
- Three alternating visible-FPS-read ON/OFF pairs for observer overhead.
- `nvidia-smi` at 250 ms for whole-process GPU utilization and memory; these values are not provider-owned memory.
- No capture, encode, profiler, per-frame file write, Prim creation/deletion, material rebinding, asset-path change, extra HydraTexture, or extra RenderProduct in the measured population.

The corrected one-condition preflight completed with exit 0, zero fatal log markers, zero stage-ID errors, visible frame 159→370 in 10.002 seconds, and no added RenderProduct. Only after this gate did the complete 15-process matrix run from scratch.

## Results

| Condition | Average visible render FPS | HUD FPS mean | Kit updates/s | Timeline sim/wall | Flow blocks final | GPU util mean | Max memory |
|---|---:|---:|---:|---:|---:|---:|---:|
| Flow OFF / V3 OFF | 33.0106 | 32.8655 | 40.2080 | 0.6701 | 0.0 | 76.45% | 5618 MiB |
| Flow ON / V3 OFF | 22.3432 | 22.2761 | 36.0002 | 0.6000 | 185.7 | 81.44% | 6770 MiB |
| Flow ON / V3 CPU-source | 23.1000 | 23.1252 | 23.9322 | 0.3989 | 180.3 | 74.52% | 6743 MiB |

All 15 processes exited normally with zero stage-ID errors and zero fatal markers. Flow reduces average visible throughput by about 32.3% relative to Flow OFF. The V3 CPU-source aggregate FPS is 3.4% above Flow ON / V3 OFF, but the OFF runs vary from 21.63 to 23.66 FPS and the condition order is small; this is not evidence that V3 improves rendering.

The V3 CPU-source publication remains a severe owner-thread boundary: the per-run Provider setter p95 mean is 76.905 ms and full publication p95 mean is 79.024 ms. Kit updates fall to 23.93/s and timeline progress to 0.399× wall time. This is consistent with publication stalls, but raw render-frame pacing is unavailable and is not inferred from these update measurements.

Visible-FPS polling ON minus OFF changed Kit update rate by +0.477, -0.132, and +0.265 updates/s across the three alternating pairs (mean +0.203). There is no measured slowdown attributable to the read, but three pairs do not establish zero overhead.

## Observed, inferred, and unknown

Observed: the corrected visible-only path has zero stage-ID errors; `omni.stats` has no matching FPS node; the HUD source and visible frame counter agree closely at the average level; Flow lowers throughput; CPU-source V3 publication stalls the owner thread.

Strong inference: the condition differences bound average visible render throughput and application responsiveness. They do not establish display-present cadence or render-frame tail latency.

Unknown: raw visible render-completion timestamps, display present timing, renderer scheduling, GPU fence boundaries, and the exact frame-pacing impact of individual V3 publications.

## Reproduction

```powershell
.\scripts\run_phasev3th_stats_inventory.ps1 -OutputDir artifacts\phasev3th-stats-inventory-smoke
.\scripts\run_phasev3th_render_fps.ps1 -OutputDir artifacts\phasev3th-visible-smoke -SmokeCondition flow_on_v3_off -WarmupSeconds 15 -MeasureSeconds 10
.\scripts\run_phasev3th_render_fps.ps1 -OutputDir artifacts\phasev3th
```

The machine-readable inventory, all accepted samples, aggregate report, and SVG are stored under `docs/devlog/assets/phasev3th/`. V3 remains default OFF and CPU-source; the GPU production candidate remains absent.

## Final regression

The corrected measurement was followed by release build, Phase 0 RTX, the complete standard suite, the six-run V3T-C OFF/ON matrix, and Phase 6DQ. The build completed in 9.41 seconds; Phase 0 produced the fixed 1280×720 output after RTX became ready; all eight standard processes and 77/77 tests passed in 394.0 seconds. V3T-C completed 6/6 processes with identical authority and metrics hashes, zero mass-balance error, consistent Resident revisions, active Flow, zero visual errors, and zero pending RTX reflections. Phase 6DQ passed 11/11 gates at rigid revision 710. Its generated evidence varied by two nondeterministic Flow/unique-frame counters, so the committed Phase 6DQ report was restored byte-for-byte and was not mixed into V3T-H.

The first standard-suite invocation was aborted by an external 3.9-second stdout timeout and is excluded; its residual Kit process was stopped before the complete suite was restarted. The final regression record is `docs/devlog/assets/phasev3th/regression_report.json`. No GPU-production candidate symbol is present in `source/`.
