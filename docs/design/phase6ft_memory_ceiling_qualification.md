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

The population safely stopped at attempt 09. Eight processes completed with representative startup, release-after-close marker integrity, normal OS exit, and zero observed residual at their normal completion. Attempt 09 was the third M1 process; it reached 688/948 active blocks at frames 60/96 with the same payload, stopped the timeline, completed all eight pre-close renderer updates, retained all required references, and then timed out 180.021 seconds after `stage_close_request_before`. It never reached `stage_close_request_after`, USD detach, post-close updates, reference release, extension shutdown, or normal OS exit. This is a readback-zero native lifecycle failure, not a Kit memory-limit failure.

The eight normal Kit peaks were 14,494,695,424–14,986,518,528 bytes (13.499–13.957 GiB), a 491,823,104-byte run range. M0 peaks were 14,800,875,520, 14,986,518,528, and 14,888,665,088 bytes; the two completed M1 peaks were 14,861,185,024 and 14,855,274,496 bytes; M2 peaks were 14,494,695,424, 14,581,649,408, and 14,569,025,536 bytes. M2 reached 1,322 blocks at frame 179 but remained the lowest peak group. M0/M1 overlap and M2's inverse direction give no evidence for a fixed Phase 6FO diagnostic-state allocation. Public field shape/logical bytes remain unavailable because readback was zero; the diagnostic allocation bodies remained zero bytes.

No normal run crossed 14 GiB, but the maximum normal peak left only 45,867,008 bytes (43.742 MiB), below the predeclared 256 MiB minimum for a useful anomaly ceiling. Combined with the frozen Phase 6FO crossing, 14 GiB is too close to normal high-water for this fixture. The eight-run maximum left 2,193,350,656 bytes (2.043 GiB) to 16 GiB, and normal unique-tree, runner, and diagnostic maxima were 15,149,535,232, 122,200,064, and 17,145,856 bytes. Physical and commit minima remained 82,912,354,304 and 102,266,773,504 bytes. GPU dedicated peaks were 7,381,975,040–7,504,658,432 bytes; shared memory was not exposed and was not estimated. No normal trace met the persistent unexplained-accumulation rule.

Normal stage-close times were 2.6753219–23.5761526 seconds. Attempt 09 peaked at 14,873,911,296 Kit and 15,037,014,016 tree bytes, so its timeout was not caused by any frozen resource ceiling. The guard finalized after 513.362 seconds with `observed_descendant_residual`. It did not finalize a CDB artifact, and direct OS enumeration later found the exact recorded runner, Kit, GPU helper, telemetry child, and conhost descendants alive despite the guard report saying absent. PID, creation time, absolute path, and parentage were verified before stopping only that attempt tree; all seven checked PIDs were absent afterward. No dump was created and no crash upload was enabled. Without a stack, module, wait owner, or NGX token evidence is unknown and is not inferred.

Consequently 14 GiB is judged too strict as an anomaly hard stop for this fixture, but it is not replaced here: the predeclared 9/9 lifecycle and cleanup requirements failed. The 16 GiB Kit and 17 GiB tree candidates are **not qualified**, and Phase 6FO remains blocked. The missing evidence is a bounded diagnosis/exact-cleanup path that actually completes for this release-after-close recurrence, followed by a newly authorized complete memory population; the eight normal memory runs remain partial distribution evidence and are not converted into a qualification.

Post-stop regression passed: Release build in 7.03 seconds; Phase 0 RTX with `status=ok`; Phase 3 with dry/wet mass-balance error zero, authoritative hashes present, wood-owned Flow input, and 251/317 final/peak active blocks; focused Phase 6F contracts 161/161; and the standard eight-process suite 78/78 in 322.9 seconds. Devlog validation reported `refs=459`, `ids=276`, `json=228`, `svg=177`, and `zip=2`. The production app SHA-256 remained `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`; production/default files, video, and latest-demo pointer were unchanged. Final Kit/CDB/nvidia-smi residual count was zero.
