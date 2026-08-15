# Phase 6HD candidate lifecycle isolation safe stop

Phase 6HC remains frozen as a canonical-report completeness safe stop. Its
artifact, classification, and documentation were not changed or reused. Phase
6HD used fresh root `artifacts/phase6hd-candidate-lifecycle-20260815` and frozen
contract SHA-256
`579A01C4F18C324624513865A6786AEF05FD27328149B4E24111E96D551C8C13`.

## Canonical operation evidence

The no-Kit producer-to-consumer fixture passed 54/54. Its positive report came
from the runtime `new_runtime_report()` producer, was written by the runtime
bounded JSON writer, and was passed unmodified through the parent reader,
normalizer, and validator. All 15 canonical counters were explicit integer
zeros before operation increments. Per-key deletion produced
`forbidden_call_missing:<key>`; a forbidden nonzero value produced
`forbidden_call_nonzero:<key>`; bool, null, string, and floating-point values
produced `call_count_type_invalid:<key>`; and unknown keys failed separately.

The canonical keys are `readback`, `array_metadata`,
`schema_volume_conversion`, `schema_metadata`, `schema_temporary_save`,
`schema_typed_read`, `velocity_save`, `velocity_sampling`,
`velocity_collector`, `temperature_conversion`, `temperature_metadata`,
`temperature_save`, `temperature_typed_read`, `temperature_sampling`, and
`temperature_collector`. The runtime producer and parent validator import this
same tuple; legacy Phase 6HB names are accepted only by an explicit in-memory
adapter at the frozen implementation boundary and are never serialized.

## Fresh one-shot ladder

| Condition | Sole added element | Canonical operation | Stage close | `shutdown_complete` | Natural exit | Result |
|---|---|---|---:|---|---|---|
| A | seven-handle readback/type/count/release | pass | 7.9951831 s | yes | code 0 | complete pass |
| B | bounded metadata for all seven arrays | pass | 4.4816666 s | yes | code 0 | complete pass |
| C | slot 1--5 schema volume/metadata/save/typed-read | pass | 8.3625182 s | yes | code 0 | complete pass |
| D | velocity save/sample/profile, no collector | pass | 2.7366648 s | yes | timeout | lifecycle safe stop |
| E | four spatial collectors | not launched | -- | -- | -- | blocked |
| F | temperature alias hold/release only | not launched | -- | -- | -- | blocked |

D recorded one readback, seven array-metadata accesses, five each of schema
volume conversion, metadata, temporary save, and typed read, one velocity save,
and one velocity sampling call. Velocity collector and every temperature
counter remained explicitly zero. `phase6hd_operation_complete`, ordered
release with weak residual zero, stage close, and `shutdown_complete` all
preceded the natural-exit timeout. The operation axis therefore passed while
the lifecycle axis failed only at post-shutdown OS exit. No retry or replacement
was used, and the first non-normal condition blocked E and F.

The maximum Kit/tree peaks were 15,175,520,256 / 15,339,544,576 bytes, leaving
2,004,348,928 / 2,914,066,432 bytes below 16/17 GiB. Maximum runner/diagnostic
peaks were 135,856,128 / 121,831,424 bytes. Minimum physical and commit headroom
were 79,346,601,984 / 98,992,418,816 bytes. Every resource gate passed. Exact
cleanup removed only the observed attempt tree and allowlisted temporary files;
final process and NanoVDB residual counts were zero.

## Continuation boundary

The last fully qualified condition is C and the first non-normal condition is
D. Their sole contract difference is velocity save/sample/profile without a
collector. This is a lifecycle association in one fresh sample, not a proven
root cause and not authorization to change that path. Phase 6HC is not
reclassified. Temperature conversion, metadata/content access, save, typed
read, sampling, and collector operations did not run and are not interpreted as
failures. A separately approved next Phase may isolate the velocity operation's
save, sample, and profile sub-boundaries; no fix, repetition, temperature work,
formal S93/S100/OFF comparison, production change, or video starts here.

Post-stop verification passed the Release build in 6.30 seconds, Phase 6HD
focused fixture 54/54, frozen Phase 6HC evidence fixture 20/20, frozen Phase
6HB ladder fixture 28/28, Python compilation, and static devlog validation
(`refs=527`, `ids=310`, `json=263`, `svg=177`, `zip=2`). The production app
SHA-256 remained
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`;
the latest-demo pointer was unchanged and the final process/NanoVDB audit was
zero.
