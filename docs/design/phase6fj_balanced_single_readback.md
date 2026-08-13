# Phase 6FJ — balanced single-readback qualification

Phase 6FG through Phase 6FI remain frozen. Phase 6FJ starts a new population and combines, without weakening, Phase 6FG's three-layer A/B/C operation decision with Phase 6FI's startup-prerequisite-only replacement rule.

## Pre-runtime contract

The balanced order is `ABC / BCA / CAB`, for nine representative independent processes. Each balanced slot retains its condition and position if startup is nonrepresentative. At most two new unique attempts may replace a preserved `startup_prerequisite_failure` detected before operation; the maximum launch count is eleven. No attempt ID, directory, or artifact is reused.

Absolute-safety and native-lifecycle evidence take priority over startup classification. Operation, identity, call-count, marker, native stage-close/shutdown, resource, fatal, dump, cleanup, diagnostic, and replacement-budget failures are nonreplaceable and stop the population immediately. A replacement is never used for an unfavorable readback, alias, waveform, or lifecycle outcome.

The Phase 6FG base operation contract remains byte-for-byte frozen at SHA-256 `54FD6185ADD41B9333506ACC55BF3472F7BBA4F0D726679071F1126572541EED`. The Phase 6FI replacement contract remains frozen at `A0B68CFC006A4B28205AACB70AB50C075CF40628C7EC29898A19D9A7001A0387`. Phase 6FJ's own contract references both and freezes its population overlay separately.

## Unchanged runtime and decision layers

A performs no readback. B calls public NanoVDB readback once and releases list/channel/handle aliases in the qualified order. C adds exactly one `numpy.asarray(fuel)` and releases source/channel/converted aliases in the existing order. The corrected four-log fixture, `allow_self_center`, -0.0125 m offset, 1,440/1,344 Points, revision 1, source totals, Flow, CollisionProxy, startup order, frame-120 boundary, 24-second running observation, renderer drain, reference release order, 180-second stage close, and all resource limits are inherited unchanged.

Absolute safety, exact operation counts and identities, representative startup, lifecycle completion, normal OS exit, and zero cleanup residual are hard gates. Slopes, rolling exceedances, peaks, terminal residual, recovery, projected drift, normalized memory, Working Set, GPU memory, and occupancy correlation remain warning telemetry only. Adjacent synchronous markers—not process-wide peaks—are the primary operation-cost evidence.

Only native lifecycle failure may invoke the existing bounded 30/45/30-second CDB path. It is nonreplaceable and stops the population. Full dump capture remains disabled without separate approval.

Only nine representative passes, three per condition, qualify one readback and one fuel alias lifetime. Repeated readback remains excluded and requires a later explicit phase.

## Runtime result and fail-closed evidence audit

The new root launched ten independent processes. Attempt 03 preserved a fresh, source-valid 24-block `startup_prerequisite_failure` and consumed one of two replacement slots. Nine later/startup-valid A/B/C processes completed the intended operations, stage close, extension shutdown, normal OS exit, and exact cleanup. Stage close was 2.176–12.161 seconds (median 3.970 seconds); CDB, fatal, dump, automatic upload, and cleanup residual counts were zero.

The six B/C partial observations recorded a 302,206,976–311,742,464-byte immediate readback increase and a 268,693,504–302,338,048-byte next-frame residual. Settling ended 757,747,712–776,646,656 bytes below the pre-readback marker. Every C observation reported a 41,398,016-byte fuel array, zero adjacent `np.asarray()` Private Bytes increase, the same Python object, shared memory, and zero weak-reference residual.

The post-runtime integrity audit found that the probe had not persisted the NumPy data-buffer pointer for either the source or converted object. Python object identity is not a substitute for a data pointer, and the frozen qualification explicitly required identity, pointer, and weak-reference agreement for all three C processes. This is an operation-evidence failure, not a startup prerequisite, so it is nonreplaceable. Attempt 04 is the first point at which the corrected analyzer would have stopped; attempts 05–10 are retained only as partial diagnostic evidence. Phase 6FJ therefore remains a safe stop: single readback, single fuel-alias lifetime, and repeated readback are all unqualified.

The diagnostic probe now records the public NumPy `__array_interface__.data[0]` pointer independently for source and converted arrays, writes both to synchronized markers, and requires positive equal pointers in addition to same-object/shared-memory evidence. Missing or inconsistent pointer evidence is fail-closed. This correction changes no production path, Point payload, Flow setting, CollisionProxy, V3 setting, resource ceiling, or prior Phase artifact.

Final regression passed the Release build in 6.56 seconds, Phase 0 RTX in 18.0 seconds, and Phase 3 in 25.9 seconds. Phase 3 retained dry/wet mass-balance error 0, authority SHA-256 `0dec57f3...e84be10` / `148585f8...fd2b20c9`, Flow active blocks final/peak 235/327, and peak fuel 1.0. Focused Phase 6F/6EA/6EB/6EL contracts passed 137/137, and the standard eight-process suite passed 78/78 in 314.1 seconds. Devlog validation passed 439 references, 266 IDs, 218 JSON, 177 SVG, and two ZIP files. Production app SHA-256 remained `94162F82...ADF02A`; no new dump, device-lost/TDR evidence, or Kit/CDB/GPU-helper residual was found.
