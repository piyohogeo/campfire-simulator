# Phase 6DW GPU configuration / renderer lifecycle baseline

## Purpose and boundary

Phase 6DW establishes a new read-only baseline after the workstation changed from RTX 3090 + Intel integrated graphics to RTX 3090 + RTX 2070. It classifies adapter selection, cache sensitivity, and renderer/Flow teardown without rerunning the failed Phase 6DU cylindrical Mesh condition.

This phase does not change the production app, V3, Resident session, wood authority, emitters, colliders, Flow 110.0.0, or any production default. Raw `dxdiag`, process lists, Kit logs, and crash material remain ignored local artifacts because they may contain personal or machine-specific information.

## Current hardware and time boundary

Windows 11 build 22631 reports DirectX 12 and WDDM 3.1. NVIDIA driver 591.86 exposes:

| NVIDIA index | Adapter | PCI bus ID | Device ID | VRAM | Display active |
|---:|---|---|---|---:|---|
| 0 | RTX 3090 | `00000000:01:00.0` | `0x220410DE` | 24576 MiB | enabled |
| 1 | RTX 2070 | `00000000:08:00.0` | `0x1F0210DE` | 8192 MiB | enabled |

PnP records the RTX 2070 first installation at 2026-08-11 08:17:20 JST and Windows boot at 08:19:33 JST. The earliest saved Phase 6DT artifact is 08:35:17, Phase 6DU is 09:36:55, and Phase 6DV is 09:53:05. Therefore all three phases ran after the RTX 2070 installation and reboot. There is no comparable pre-change run in these artifacts, so the hardware change cannot be causally confirmed or ruled out from historical timing alone.

The saved Kit logs for all three historical phases enumerate both adapters and select RTX 3090 / CUDA device 0 wherever a renderer device is logged. Their selection therefore matches the current baseline; the current conclusion does not rely only on today's `nvidia-smi` order.

Windows maps active display paths to both GPUs. The Kit logs identify the primary present target as `DISPLAY2` / ViewSonic on the RTX 3090. The exact physical cable identity was not independently inspected, but cross-adapter presentation was not observed for the tested Kit processes.

## Probe construction

Every condition runs in a separate Kit process with crash upload disabled, dump preservation requested, a finite timeout, and durable lifecycle markers. Renderer-free cases use the shipped empty app. RTX cases use the shipped viewport app with public `omni.usd`, RTX Hydra, UsdRT delegate, and viewport extensions. Flow conditions add the installed `omni.flowusd` 110.0.0 path. Stages are fully prepared before connection.

The seven conditions are:

1. Kit startup without a stage.
2. Empty stage through pure OpenUSD.
3. Empty stage connected to Hydra/RTX through first viewport frame and shutdown.
4. Phase 6DT known-good Box through pure OpenUSD.
5. The same Box through Hydra/RTX.
6. Flow extension loaded without simulation.
7. Known-good minimal Flow simulation.

The formal matrix first uses the existing cache and then a newly created empty isolated cache. Existing cache files are never deleted or rewritten by the runner. The Phase 6DU `mesh_hull` failure is not used.

## Results

| Condition | Existing cache | Empty isolated cache | Exit / fatal / dump / upload |
|---|---:|---:|---|
| Kit only | 0.441 s | 0.442 s | 0 / 0 / 0 / 0 |
| OpenUSD empty | 0.925 s | 0.942 s | 0 / 0 / 0 / 0 |
| RTX empty | 15.362 s | 31.393 s | 0 / 0 / 0 / 0 |
| Box OpenUSD | 0.967 s | 0.959 s | 0 / 0 / 0 / 0 |
| Box RTX | 13.137 s | 34.155 s | 0 / 0 / 0 / 0 |
| Flow load | 5.720 s | 3.716 s | 0 / 0 / 0 / 0 |
| Flow simulation | 26.369 s | 45.183 s | 0 / 0 / 0 / 0 |

All 14 formal processes exited with code 0. Renderer cases reached first renderer update and viewport frame; stage cases reached stage close and renderer drain; applicable logs contain renderer plugin shutdown. There were no fatal tokens, crash dumps, automatic upload attempts, CUDA illegal addresses, device-lost events, or TDR evidence.

Every renderer process selected `NVIDIA GeForce RTX 3090` and CUDA device index 0. Hydra reported device mask 1 and assigned the viewport to device 0; the Flow process reported graph CUDA ordinal 0. Flow 110.0.0 did not emit a separate public Flow-device selector, so that last component is recorded as shared-process evidence rather than a distinct Flow API guarantee. No startup selected the RTX 2070, and enumeration order did not change. The isolated cache increased cold RTX/Flow startup time but did not change the selected device or shutdown result.

The installed runtime contains the public setting `/renderer/activeGpu`; the same setting appears in the shipped `omni.app.mini.kit`. One isolated Box RTX control explicitly set GPU 0 and selected the same RTX 3090/CUDA 0, exiting normally in 13.411 s. Production defaults were not changed, and an RTX 2070 explicit-selection experiment was unnecessary.

## Classification

### Observed

- The current two-GPU system consistently selects RTX 3090 for Kit RTX and Hydra-backed rendering, while the Flow process uses graph CUDA ordinal 0.
- Kit presents to a primary display path on the RTX 3090 in these runs.
- Empty RTX, known-good Box RTX, Flow extension load, and Flow simulation all complete normal OS process shutdown with both cache modes.
- The production app SHA-256 remains `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.

### Strong inference

- The Phase 6DV non-exit is more likely specific to its production-derived Editor launcher/app composition or teardown ordering than a generic consequence of having RTX 3090 and RTX 2070 installed.
- Old renderer cache state is not required to obtain a normal lifecycle. The empty cache adds cold initialization cost but does not repair a failure because the normal cache is already healthy.

### Unconfirmed

- A rare multi-GPU/cache/initialization race could still have contributed to the historical `omni.fabric.plugin.dll+0xD6960` crashes; there is no pre-change control and no function-level symbol attribution.
- Physical cable routing beyond the Windows display-path mapping has not been visually inspected.
- The precise Phase 6DV launcher/lifecycle difference remains to be minimized.

## Phase 6DU restart decision

The previous restart prerequisite—known-good Box through Hydra/RTX to normal OS exit—is now satisfied. Phase 6DU may resume only as a new independent staged ablation, not by blindly repeating the failed cylindrical `mesh_hull` process.

The safe start is the known-good static, axis-aligned, Flow-only Box Mesh. Change one topology or schema dimension per process, require stage-open and normal shutdown first, and only then approach a cylindrical hull. Dynamic transform, analytic overlap, Phase 6DR integration, and 20-log performance remain outside that restart step.

## Regression

- Release build: passed, 6.25 s.
- Standard suite: 8 processes, 78 / 78 tests, 310.6 s.
- Phase 0 RTX: passed with a 1280 × 720 captured frame.
- Normal and benchmark Candidate Performance app startup/settings/shutdown: 2 / 2 passed.
- Known-good minimal Flow probe: passed in both cache modes.
- Devlog static validation: 589 local references, missing 0, UTF-8 replacement characters 0; an actual browser render remained unavailable because no browser binding was connected.

Phase 6DW has no intended visual change, so no new demo video was generated and the existing latest-demo pointer remains unchanged.
