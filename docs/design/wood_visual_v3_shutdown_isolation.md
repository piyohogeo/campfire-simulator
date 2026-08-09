# Phase V3T-G: DynamicTextureProvider shutdown crash isolation

## Decision

The Phase V3T-F access violation was not reproduced in 78 independent Kit processes. This is an observed non-reproduction, not proof that the GPU-source lifetime is safe and not identification of an internal root cause. The production GPU transport remains absent, V3 remains default OFF, and the CPU-source V3 path remains unchanged.

The isolated result does not satisfy the re-adoption gate. That gate still requires one selected final sequence to complete at least 20 independent normal exits spanning stage replacement, Provider recreation, extension disable, and normal Kit quit. Phase V3T-G intentionally stops at cause classification and makes no production integration.

## Fixed boundary

- Kit 110.2, Flow 110.0.0, RTX 3090, one GPU.
- 20 logs, fixed 1280×720 viewport, Flow and RTX active.
- Two fixed `DynamicTextureProvider` instances for 120×60 RGBA8 base and emission atlases: 57,600 bytes and two API calls per publication.
- 20 requested-frame warmup steps and 120 publications per process.
- Providers, dynamic URIs, material bindings, USD Prims, and asset paths are created before the measured update loop and never replaced inside it.
- Every process starts only after the runner verifies that no earlier isolated `kit.exe` remains.
- CPU pointers are passed only to `set_raw_bytes_data`; GPU pointers come only from probe-owned persistent Warp allocations passed to the public `set_bytes_data_from_gpu` API.

## Compared resource conditions

The mandatory reproduction controls ran ten times each with rotated order: CPU-source reference/A and GPU ring3/A. Provider-only, Warp-only, fully synchronized single GPU source, ring3 with allocations retained, ring3 with Providers retained, and stage-first ring3 ran three times each. Retained-resource modes are diagnostics only and are never production candidates.

Shutdown A matches the V3T-F ordering: stop, Provider destroy, GPU synchronization/release, then normal Kit quit. B–E change only drains and stage/Provider/GPU release ordering. A ran ten GPU processes; B, C, D, and E each ran ten. Stage/Hydra detachment is represented by public `close_stage_async()` completion followed by bounded Kit update drains; the fixed SDK exposes no stronger public "Hydra detached" fence, so that label is not used as a guaranteed renderer-internal fact.

## Durable evidence

Each boundary writes a small JSONL marker and immediately flushes and `fsync`s it. The parent process records the Windows exit code, elapsed time from shutdown start, last durable marker, marker count, crash-keyword excerpts, GPU-memory range from 250 ms `nvidia-smi`, and whether CUDA illegal-address, device-lost, or invalid-pointer text appeared. Native process exit and Kit crash logging are authoritative; a Python exception is not treated as evidence of native shutdown success or failure.

All 78 processes exited `0x00000000`. There were no timeout, `0xC0000005`, CUDA illegal-address, device-lost, or invalid-pointer outcomes. Every process recorded the explicit extension-disable `on_shutdown` begin/end markers before normal Kit quit. CPU/A was 10/10 normal; ring3/A was 10/10 normal; ring3 B–E were each 10/10 normal; every three-run resource condition was 3/3 normal.

## Classification

### Observed facts

- Phase V3T-F's one access violation did not recur in this 78-process matrix.
- Resource retention and stage-order variants therefore have identical observed crash counts: zero.
- No condition provides a positive discriminator for Provider, Warp/CUDA, USD/Hydra, or Flow ownership.

### Strong inference

There is no strong cause inference because the failure did not reproduce. In particular, zero crashes in retained-allocation modes cannot show that a Provider source-consumption fence was the cause, and zero crashes in CPU controls cannot exclude Kit/USD/Hydra lifecycle timing.

### Unconfirmed

- Whether the V3T-F `UsdGeomCylinder::ComputeExtent` / `unregisterViewOverrideToHydraEngines` stack was causal or secondary.
- When `DynamicTextureProvider` has finished consuming a GPU source pointer; the public API still exposes no completion fence.
- Whether a longer run, interactive editor lifecycle, stage replacement plus Provider recreation, or a different scheduling interleave can reproduce the crash.

## Reproduction

```powershell
.\scripts\run_phasev3tg_shutdown_matrix.ps1
```

The analyzer preserves all process summaries and durable markers in `shutdown_samples.json`, the condition aggregate in `shutdown_report.json`, and non-normal crash excerpts in `crash_log_index.json`. The production module, app defaults, V3T-C consumer, Phase 6DQ, wood authority, Flow input, Point payload, rigid layout, collision, checkpoint, serialization, revision, and rollback contracts are not modified.

