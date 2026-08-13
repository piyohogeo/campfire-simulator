# Phase 6FG — paired single-readback qualification

## Frozen history and scope

Phase 6FD, 6FE, and 6FF remain formal safe stops under their own contracts. Phase 6FG does not reinterpret their same-sample, whole-window slope, or rolling-persistence failures and does not reuse their samples in its formal population. Their artifacts are read-only design evidence.

This phase changes diagnostic policy and runner labeling only. Production code, defaults, the corrected four-log fixture, Point payload, Flow settings, CollisionProxy, authority state, V3, and the 14 GiB Kit / 16 GiB unique-tree ceilings remain unchanged. Repeated readback, multiple-frame field retention, other-channel conversion, field persistence, forced GC, private release APIs, production integration, and video are excluded.

The pre-runtime machine contract is `scripts/phase6fg_paired_readback_contract.json`, SHA-256 `54FD6185ADD41B9333506ACC55BF3472F7BBA4F0D726679071F1126572541EED`.

## Three-layer decision model

The formal hard gate contains only absolute safety and evidence-integrity conditions: resource ceilings and system headroom, a bounded diagnostic process, zero fatal/access-violation/dump/upload evidence, exact cleanup, complete stage-close and shutdown markers, normal OS exit, representative Point Emitter startup, unchanged stage/payload/production hashes, and the declared single-operation counts.

All waveform metrics remain recorded, including whole/half/final and rolling slopes, rolling threshold exceedances, peak, terminal residual, recovery amount/time, projected drift, Working Set, GPU dedicated memory, Private Bytes per active block, and occupancy correlation. They are telemetry and warnings, not formal pass/fail predicates. Phase 6FF's evaluator is reused only to preserve the same numerical observability; its `gate_pass` is not authoritative in Phase 6FG. The resulting distribution is versioned with fixture, active-block range, Kit-log hash, bounded shader/cache token counts, and available GPU telemetry. It is not a permanent production baseline.

Operation-specific evidence comes from adjacent synchronous markers. Process-level peak and terminal differences are context only, especially when active-block scales differ. A performs no readback. B performs one public readback and releases all list/channel aliases. C performs one public readback, exactly one `numpy.asarray(fuel)`, and the existing ordered release. C must report the established same-object zero-copy classification and zero weak-reference residual.

## Formal population

Nine independent processes are frozen in a balanced positional order: `ABC`, `BCA`, `CAB`. Each condition therefore occurs once in each sequence position and three times total. Every process uses the same stage, startup order, frame 120 operation boundary, sample frames, and 24-second running-Flow observation. Cache/shader evidence is recorded from each bounded Kit log, without claiming more than the public log establishes.

Before Kit runtime, synthetic fixtures must show that transient recovery can remain a warning while absolute ceiling and lifecycle failures fail closed. A first cache increase followed by a settled plateau must be accepted as a future repetition pattern, while a material per-iteration staircase must be rejected. This does not authorize a runtime repetition test in Phase 6FG.

Runtime results will be appended without changing this contract. If any absolute, lifecycle, startup, identity, cleanup, or operation gate fails, the active condition stops without retry and later conditions do not start. Only all nine passing processes qualify one readback and one fuel alias lifetime. Repeated readback remains a separate, explicitly approved phase.
