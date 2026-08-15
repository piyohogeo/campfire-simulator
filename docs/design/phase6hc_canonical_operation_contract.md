# Phase 6HC canonical operation evidence contract

Status: frozen before runtime. Base commit: `e077fe5`. Contract SHA-256:
`A0BADE57DABDF480CFE86D2F3F7E99F2F808B47C71E28E30BE5C17DB9F551067`.

Phase 6HB remains a harness safe stop. Its artifact, formal classification,
documentation, and A sample are not modified, upgraded, or reused.

## Evidence ownership

The canonical operation artifact is the attempt-local
`post_readback_isolation.json` with exact schema
`campfire.phase6hc.operation-report.v1`. It must identify the fixed condition,
attempt ID, and mode; record `operation_result=pass`, an explicit true
`operation_complete`, the canonical final checkpoint, completed reference
release, weak residual zero, and zero calls for every prohibited temperature
operation.

`resource_markers.jsonl` is the resource/lifecycle stream. A missing duplicate
operation-complete marker there is neutral. If an operation marker is present,
it is checked against the canonical report. Matching evidence is accepted;
conflicting completion/failure is rejected. Resource-only completion never
substitutes for a missing or invalid canonical report. Legacy schema or marker
names are not implicitly normalized.

The no-Kit fixture uses the exact two filenames and parent normalization entry
point. It covers normal Phase-6HB-A-shaped evidence, missing completion/file,
invalid JSON, schema/condition/attempt mismatches, resource-only completion,
matching dual evidence, conflicting dual evidence, incomplete release,
forbidden calls, resource/cleanup failure, legacy-only evidence, and weak
residual.

## Runtime ladder

After the fixture passes, Phase 6HC uses a new root and fresh processes for the
unchanged Phase 6HB sequence: A readback/release; B all-slot bounded array
metadata; C non-temperature slots 1--5 schema work; D velocity save/sample/
profile without collectors; E four collector use; F temperature alias hold/
release only. Each runs once. The first non-normal canonical operation,
lifecycle, resource, cleanup, or residual result stops the ladder.

Temperature conversion, metadata/content access, save/reload, sampling, and
collector work remain prohibited. The 16/17 GiB limits, 512 MiB runner and
diagnostic limits, 8 GiB machine floors, one-Kit rule, exact attempt-local file
cleanup, unknown-file refusal, release-after-close, and residual-zero gate are
unchanged. Formal S93/S100/OFF, video, production, defaults, Point policy, V3,
and P4 remain excluded.
