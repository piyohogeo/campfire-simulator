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

## Runtime safe stop

Synthetic calibration passed all five required distinctions: transient recovery did not become a hard failure, absolute ceiling and incomplete lifecycle failed closed, first-cache-then-plateau passed, and iteration-by-iteration staircase accumulation failed. The formal root then started from an empty population in the frozen `ABC / BCA / CAB` order.

Sequence 1 completed A, B, and C normally. Sequence 2 completed B and C normally, then stopped at A. Thus five conditions passed and the sixth active condition supplied partial evidence; sequence 3 was never started. Every completed A/B/C process had representative startup and exact source/stage identities. Waveform warnings ranged from four to five per process but, as designed, did not alter the formal decision.

The two passing B runs measured adjacent readback increments of `306,528,256` and `339,447,808 bytes`. The two passing C runs each measured `302,247,936 bytes` at readback. Both C runs returned a `41,398,016-byte` fuel array and classified `numpy.asarray(fuel)` as the same Python object and a zero-copy alias; its adjacent Private Bytes delta was `0 bytes`, source-alias release was `-33,619,968 bytes`, converted-alias release was `0 bytes`, and observable weak-reference residual was zero. B/C settling-end residuals were all negative relative to the pre-readback marker (`-691,097,600`, `-708,386,816`, `-768,876,544`, and `-774,885,376 bytes`). These are valid partial operation observations, not a qualification, because the nine-process population did not complete.

The active failure was sequence 2 A, a no-readback control. It reached representative startup, completed the 24-second observation, stopped the timeline, drained the renderer, and released Flow/provider references. `close_stage_async()` then reached the frozen 180-second timeout at `stage_close_request_before`. The extension shutdown callback later reached its end marker, but normal OS exit was not confirmed. Bounded CDB attached and captured the module list and began all-thread native stacks; its first captured thread was in `omni_usd!UsdManager::destroyContext` through extension/plugin shutdown. CDB itself reached its 45-second timeout before a detach marker. The accepted five-token NGX signature did not match, no lock owner was established, and the outcome remains an unknown shutdown failure rather than a known external residual. No full dump was created.

The outer guard found the exact Kit/conhost/telemetry descendants, terminated only those recorded identities, and confirmed an empty remaining set. Across all six analyzed processes, Kit peak was `14,907,940,864 bytes` (`13.884 GiB`), leaving `124,444,672 bytes` (`118.68 MiB`) below 14 GiB; tree peak was `15,070,949,376 bytes` (`14.038 GiB`). System physical and commit floors retained over 79 GiB and 97 GiB respectively. Fatal, access violation, dump, and automatic-upload counts were zero. Production SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`.

Release build, Phase 0 RTX, Phase 3, focused Phase 6F `56/56`, and the standard eight-process suite `78/78` passed. Phase 3 retained dry/wet mass-balance error zero, authority hashes, active blocks final/peak `235/371`, and peak fuel `1.0`. Phase 6FG therefore ends as a lifecycle safe stop: static waveform gates are successfully removed from the new decision, but one readback, one fuel alias lifetime, and repeated readback remain unqualified. The next step requires a separately approved resolution or qualification of the low-frequency USD-context stage-close failure before restarting a fresh balanced population.
