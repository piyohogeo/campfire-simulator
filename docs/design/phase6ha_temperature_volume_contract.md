# Phase 6HA temperature-volume contract

Phase 6GZ remains a frozen lifecycle safe stop. Phase 6HA uses a new artifact
root and creates a new S93 stage; no Phase 6GZ runtime sample is reused or
reclassified.

The only new temperature operation is one public `buffer_to_volume()` call at
frame 180 after the existing seven-handle schema preflight and velocity
pipeline. The probe records the returned Python type, then releases the volume,
temperature source, and remaining handles in order. It does not inspect volume
content or metadata, save/reload NanoVDB, sample, collect, aggregate flux, copy
the field, process another channel, or repeat the readback.

An attempt is replaceable only when operation completion, conversion count one,
zero forbidden content access, ordered release, stage close, and durable
`shutdown_complete` are all proven; resource and exact-cleanup gates pass;
there is no Python/native/operation/cleanup failure; and the sole missing
boundary is natural OS exit after `shutdown_complete`. At most one fresh
replacement is allowed. The original remains a lifecycle-only failure. A
second identical exit failure, or any other failure, stops the Phase without
another launch.

The 16/17 GiB limits, 512 MiB runner/diagnostic limits, 8 GiB physical/commit
floors, one-Kit rule, release-after-close, progress-aware CDB, and exact
attempt-tree cleanup remain unchanged. Temperature metadata/save/sampling and
the formal S93/S100/OFF population require later approval.

