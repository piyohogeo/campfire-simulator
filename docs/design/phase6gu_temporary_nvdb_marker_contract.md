# Phase 6GU resource-marker and temporary NanoVDB contract

Phase 6GT remains frozen as a harness-failure safe stop. Its single runtime
sample is neither retried nor reused. Phase 6GU is a new one-process boundary
with contract SHA-256
`2BA943427299FCEA854A30D7E17BA359931ACC7779D6FB3B9312E1D0F96027A7`.

## Marker boundary

The actual diagnostic `_append_resource_marker()` implementation is now a
No-Kit-safe shared function. Reserved payload keys are the union of its
`inspect.signature()` parameter names and the fields it creates itself:
`schema`, `timestamp_utc`, `perf_counter_ns`, `pid`, `marker`,
`process_memory`, and `python_memory`. A collision is rejected with the exact
key name before the helper is called. Equal duplicate inputs are canonicalized
once; conflicting duplicates fail closed. A valid event is expanded exactly
once as one canonical dictionary.

The temporary path event field is `temporary_file_path`. Payload field `path`
is forbidden because it is owned by the marker helper. The implementation
change is confined to diagnostic probes and the shared marker boundary; it
does not change the production application or stage.

## Pre-runtime gates

The actual helper is imported and called without Kit. The Python fixture must
pass 20 cases and the Python-child-to-PowerShell-parent fixture must pass five
cases. They cover signature and automatic-field collisions, exact one-row
JSONL persistence, artifact-root containment, pre-existing files, the 256 MiB
limit, exact single-file cleanup, neighboring-file preservation, one static
save call, zero content read/hash/reload, and terminal safe-stop state.

Only after these gates and the Release build pass may one new S93 process run.
It inherits Phase 6GT's fixed frame-180 readback, slot-0 temperature
conversion, six public accessors, one `save_volume()` call with
`kNanoVDBCodecNone`, ten-second poll, 256 MiB file limit, exact deletion,
16/17 GiB resource limits, release-after-close, and 180-second stage-close
limit. There is no retry or replacement.

Operation and lifecycle are reported separately. Temporary-NanoVDB saving is
qualified only if save return, nonempty bounded file, deletion, ordered
reference release, stage close, and natural zero OS exit all pass. No file
content, hash, reload, typed metadata, other channel, sampling, collector,
flux, image, video, or formal comparison is authorized.

## Runtime result: safe stop

The pre-runtime gates passed (actual-helper Python 20/20, parent E2E 5/5,
Phase 6GS regression 14/14, Phase 6GT regression 23/23, and Release build).
Exactly one new process was launched. It stopped before readback because the
startup telemetry row intentionally carried its own `perf_counter_ns`, which
the newly generalized helper correctly classified as an automatically owned
reserved key. The durable raw error was
`ValueError: reserved marker payload key collision: perf_counter_ns`.

This is a newly exposed harness-contract mismatch, not save API evidence.
Readback, conversion, all six accessors, `SaveVolumeParameters`, and
`save_volume()` had zero calls in this process. No NanoVDB file was created,
read, hashed, reloaded, or retained. The new contract also names a
`phase6gu_...nvdb` file while the inherited probe still resolves its legacy
`phase6gt_...nvdb` filename; because saving was not reached this caused no file
operation, but it must be resolved before any future save attempt.

Stage close completed in 5.920864 seconds and the final durable marker was
`shutdown_complete`. Kit exited 1 because of the probe exception, so operation
and lifecycle both fail. Exact identity cleanup left zero Kit/CDB residual and
zero temporary file. Kit/tree peaks were 12,493,996,032 / 12,658,114,560
bytes, leaving 4,685,873,152 / 5,595,496,448 bytes below the frozen limits.
There was no retry, replacement, CDB, dump, automatic upload, later operation,
or formal population. Phase 6GU is frozen as a safe stop; typed metadata and
all later work remain blocked pending a separately approved contract/root.

Final regression passed the Release build, Phase 0 RTX, Phase 3 with zero
dry/wet mass-balance error, wood-owned Flow input, active blocks final/peak
273/313, focused Phase 6G 71/71, the Phase 6GU fixtures 20/20 and 5/5, and the
standard 8/8-process suite with 78 tests. Devlog validation passed 508
references, 301 IDs, 253 JSON files, 177 SVG files, and two ZIP files.
Production and latest-demo hashes remained unchanged; final Kit/CDB and
temporary-NanoVDB residual counts were zero.
