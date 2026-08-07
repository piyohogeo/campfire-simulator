# Shared SoA + Python proxy adoption decision

Status: deferred after Phase 6BW re-evaluation. This is not a rejection of technical feasibility.

## Decision

Keep the existing default-off Resident native lifecycle: Python objects are imported once into a private contiguous SoA, C++ owns the numeric hot path, immutable `ResidentPublishedSnapshot` values cross the consumer boundary, and the SoA is exported once at shutdown for existing serialization.

Do not replace `WoodCellState` with a shared-buffer proxy now. The current 1,200-step lifecycle already performs zero numeric dirty imports after initialization. A proxy would therefore add no current hot-path import saving; its primary benefit would be a new supported mid-run Python editing feature, which the current product path does not require.

## Evidence

- The isolated 20-log proxy spike still passes all 16 lifecycle, ABI, rollback, stale-reference, and equivalence gates. NumPy and C++ share stable contiguous pointers, and numeric proxy edits need no re-import.
- `cell.temperature_k` syntax can be preserved, but scalar proxy read/write p95 is slower than direct dataclass access. The proxy is also not fully compatible with `dataclasses.asdict`, `replace`, stable object identity, or direct structural mutation.
- A 32-field edit lease is inexpensive, but the current Resident run has no supported mid-run edit workload to amortize or justify the additional lifecycle.
- Naive direct SoA JSON serialization remains slower than the existing dataclass serializer. Adoption would require a dedicated native or vectorized bulk serializer before changing the authoritative public representation.
- A read-only `memoryview` remains readable after backend close. Buffer-protocol lifetime cannot be revoked, so production use would have to keep raw writable arrays private and issue only explicit, bounded edit leases.
- Phase 6BN reduced the existing Resident USD publication p95 median to 1.5008 ms with `Sdf.ChangeBlock`. Shared SoA does not reduce USD authoring, Flow ingestion, rasterization, solver, or rendering cost.

## Reopen criteria

Reconsider the proxy only when all of these are true:

1. A concrete, supported mid-run per-cell Python edit workflow is required.
2. That workload demonstrates material import or edit overhead under an application-level benchmark.
3. Writable arrays remain private, native stepping and editing are mutually exclusive, and stale proxies fail closed.
4. A bulk serializer meets or beats the canonical existing JSON path without changing its schema.
5. Native failure, downstream publication failure, shutdown, restart, immutable snapshot, rollback, and consumer revision gates all pass.

The next production-facing task is therefore lifecycle hardening of the existing Resident path, not proxy adoption.
