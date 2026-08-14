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
