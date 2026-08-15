# Phase 6HN: bounded process-role projection and Flow proxy boundary

## Frozen history

Phase 6HM remains the immutable `d1dc873`
`safe_stop_pre_kit_fixture_harness_failure`. Its 4,081,422-byte Phase 6FZ
aggregate was sent directly to a 1 MiB bounded reader and raised
`bounded_json_oversize`. Phase 6HN does not edit, rerun, reclassify, or use the
Phase 6HM artifact as a runtime sample. That failure is not Flow, Kit resource,
lifecycle, or CollisionProxy evidence.

## Bounded projection contract

The historical Phase 6FZ aggregate is read-only producer input. It is never an
input to the shared bounded consumer. The producer streams the nine resource
JSONL traces and emits only:

- attempt ID, condition, final classification, and exit state;
- guarded PowerShell root and direct Kit-child PID/creation-time identities;
- a representative identity, path set, and identity count for runner, Kit,
  diagnostic, and unknown-child roles;
- per-sample PID/creation-time deduplication and PID-reuse protection results;
- cleanup outcome and residual count.

Full samples, stdout/stderr, Kit logs, GPU time series, and other telemetry are
not embedded. Schema
`campfire.phase6hn.phase6fz-process-role-projection.v1` fixes nine attempts and
a 131,072-byte maximum, leaving an eightfold margin under the unchanged 1 MiB
shared reader. Contract SHA-256 is
`EE1655ECF097EBE5578FDDA0BB96A405E4E405C900F6CE2DC0C752C4DB84737F`.

## No-Kit result

The actual producer wrote a 36,005-byte projection from all nine Phase 6FZ
attempts and the actual bounded consumer accepted it. All 34 fixture gates
passed. They include unique and complete attempt coverage, PowerShell root as
`runner`, direct child Kit as `kit`, separate diagnostic/unknown-child roles,
PID/creation-time deduplication, PID-reuse protection, exit propagation,
direct file streaming, and residual zero.

Missing or duplicate attempts, oversize output, invalid types, contradictory
or unknown role labels, direct Kit root, Kit-path mismatch, and missing guard
summary each produced a distinct fail-closed result. The mock fixture launched
no Kit process.

## Formal one-process boundary and safe stop

After preflight passed again in a new empty root, the qualified Phase 6FZ
topology launched one Kit process:

```text
C:\Python38\python.exe
  -> Phase 6FU resource guard
       -> powershell.exe run_phase6hn_flow_proxy_case.ps1
            -> kit.exe
```

The roles and direct parent relationship were observed without duplicate
identities. However, Kit did not become app-ready. At about 0.49 seconds its
log recorded permission failures opening two extension-registry lock files,
then extension dependency resolution failed (`omni.anim.curve.core` was not
available) and the executed probe could not import `campfire`. No Phase 6HN
marker or operation report was produced. The PowerShell shutdown monitor could
not verify the already-unqueryable Kit identity and reached its 360-second
absolute bound; the outer guard then returned nonzero.

This is a formal safe stop at the Kit app-ready/dependency environment
boundary. It is not evidence that the production hierarchy and one
`FlowCollisionProxy` coexist or fail to coexist. No stage, proxy Prim, 30-frame
viewport update, public Flow interface access, stage close, or shutdown marker
was measured. There was no retry or replacement.

## Safety evidence

Observed peak Private Bytes were runner 96,821,248, Kit 164,438,016,
diagnostic 16,203,776, child 6,246,400, and unique tree 277,323,776 bytes.
Headroom was 16,227.180 MiB below the 16 GiB Kit limit and 17,143.523 MiB below
the 17 GiB tree limit. Minimum available physical memory was 91,477,635,072
bytes and minimum estimated commit headroom was 111,169,638,400 bytes.

The two raw `Traceback` pattern matches are extension-registry permission
errors, not confirmed native crashes. Native exception, dump, automatic
upload, device loss/TDR, and actual CDB attach counts are zero. Exact guard
cleanup found all observed identities absent; process and NanoVDB residuals are
zero. Production app, source app, production scene, wood authority, V3, and
latest-demo hashes remained unchanged.

## Regression and stop boundary

Focused Phase 6HN tests passed 8/8, Python compilation passed, Release build
passed in 7.74 seconds, and the standard eight-process suite passed 78/78 in
354.6 seconds. Static devlog validation passed. Phase 0 RTX and Phase 3 were
not added because diagnostic-only files changed and production source, USD
generation, renderer configuration, wood authority, and Flow input remained
unchanged.

The bounded projection and no-Kit process-role interface are qualified. The
one-proxy production-hierarchy coexistence boundary remains unqualified and
unmeasured. A future separately approved Phase must first prove an app-ready
exact-command environment without changing the resource topology or proxy
scope; dynamic transforms, occlusion, PhysX sharing, 20-log performance,
Point policy, production integration, and NanoVDB work remain out of scope.

