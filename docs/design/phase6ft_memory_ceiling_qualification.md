# Phase 6FT release-after-close memory ceiling qualification

## Frozen boundary

Phase 6FS is frozen at commit `0c2b582`. Its three independent S93 readback/capture-free processes used `release-after-close`, exited normally, and left no observed descendant. Their Kit peaks were 14,941,323,264, 14,880,235,520, and 14,887,927,808 bytes; the smallest margin to the old 14 GiB hard ceiling was only 86.844 MiB. This is sufficient to make the lifecycle order a diagnostic candidate, not to change production or to adopt 16 GiB. Phase 6FT does not reclassify Phase 6FR/6FS and does not restart Phase 6FO.

## Pre-runtime contract

The authoritative contract is `scripts/phase6ft_memory_ceiling_qualification_contract.json` with its SHA-256 sidecar. It freezes nine new independent processes in balanced order:

- M0: Phase 6FN-equivalent S93 baseline, allocation level 0, frames 60/96;
- M1: Phase 6FO-equivalent diagnostic state, allocation level 7, frames 60/96;
- M2: the same Phase 6FO-equivalent state through frame 179, immediately before Phase 6FO's planned first readback at frame 180.

Each condition runs three times in `M0/M1/M2`, `M1/M2/M0`, and `M2/M0/M1` order. All use the corrected four-log fixture, S93 `allow_self_center`, 1,344 of 1,440 Points, payload SHA-256 `0D3B074B7BE3E482E8702A126A11619D87F587C4848C80D4A3162A11B876C389`, identical source sums, public readback zero, capture zero, and no video. Existing Phase 6FP allocation levels are reused; no separate collector or lifecycle implementation is introduced.

The fixed candidate lifecycle is timeline stop, eight renderer updates, explicit retention of stage/viewport/Flow/provider/Emitter/collector references, `close_stage_async()`, USD detach, four post-close updates, ordered release, extension shutdown, Kit shutdown, and normal OS exit. It remains diagnostic-only and does not change production shutdown order. Stack-first bounded CDB remains armed only for a natural timeout.

## Separated resource limits

The old 14 GiB Kit value is a soft evaluation threshold in this qualification. Crossing is recorded but is not itself a kill condition, because doing so would censor the normal distribution under test. The provisional absolute Kit stop is 16 GiB. Candidate qualification requires the largest normal peak to be no more than 15.5 GiB, preserving at least 512 MiB to that stop.

The provisional unique-tree stop is 17 GiB. Phase 6FS observed at most 163,930,112 bytes of tree-over-Kit overhead. A 17 GiB tree stop therefore gives a full 1 GiB above the Kit stop and still leaves 909,811,712 bytes after that observed overhead, exceeding the fixed 512 MiB margin. Runner and diagnostic child remain separately bounded at 512 MiB. Physical-memory and commit-headroom floors remain 8 GiB, and stage close remains 180 seconds. None of these limits is unbounded.

Kit 16 GiB, tree 17 GiB, runner/diagnostic 512 MiB, either machine floor, stage-close timeout, fatal/dump/upload/device-lost/TDR, marker corruption, CDB/detach/cleanup failure, or residual process stops the population without replacement. Only the frozen single startup-prerequisite replacement is allowed.

## Telemetry and boundedness

Resource rows are streamed to JSONL and GPU telemetry to a bounded file. Kit process and unique-tree Private Bytes are distinct measures; shared mappings are not inferred or corrected by subtracting guessed values. GPU shared memory is reported only if the existing public telemetry exposes it. With readback zero, public NanoVDB field shape and logical bytes are unavailable and are recorded as such; diagnostic allocation-plan bodies remain a separate zero-byte fact.

Single slopes are not hard gates. The predeclared persistent-accumulation gate needs ten final Kit samples that never decrease, rise by at least 512 MiB, and occur without growth between the final physics active-block markers. Other slopes, recovery, cache/shader log activity, condition medians, active-block relations, and stage-close correlation are diagnostic telemetry. This prevents normal short waveform noise from being promoted into a post-hoc limit while still rejecting a large unexplained terminal staircase.

The old 14 GiB ceiling is classified as too strict if at least two normal runs cross it or the largest normal peak leaves less than 256 MiB below it. The 16 GiB candidate qualifies only if all nine representative processes finish normally, the largest peak leaves at least 512 MiB, all separated limits/floors pass, no persistent unexplained accumulation is found, and all lifecycle and exact-cleanup gates pass. A successful result only permits reporting that a separately approved Phase 6FO restart could use the new contract; Phase 6FT itself does not run S93/S100 scalar/flux comparison, video, P4, or production integration.

## Runtime result

Pending. Results will be appended without changing the frozen decision rules.
