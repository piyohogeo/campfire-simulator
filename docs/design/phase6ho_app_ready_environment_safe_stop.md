# Phase 6HO: exact app-ready deployment boundary

## Frozen history and scope

Phase 6HN remains frozen at `8278141` as a Kit app-ready/dependency-environment
safe stop. Its artifact, classification, thresholds, and zero accepted runtime
samples were not edited, reclassified, or reused as Phase 6HO measurements.
Phase 6HO changes diagnostic harness code only. Production, defaults, Point
policy, wood authority, V3, Flow input, and the latest demo are unchanged.

The frozen contract is
`campfire.phase6ho.app-ready-and-proxy-contract.v1`, SHA-256
`91D9DD198579FEF7D4189436B72DA151022D6D9492641A2EE34F13ACE6EB0F65`.
It permits the one-proxy boundary only after an exact app-ready smoke passes.

## Read-only environment audit

The confirmed Phase 6HN/Phase 6FZ difference is deployment-path spelling.
Phase 6HN applied `Path.resolve()` to build-tree reparse points before launch:

- build `kit/kit.exe` became the Packman kernel path;
- build `apps/campfire.simulator.kit` became the source app path;
- the resulting mixed roots omitted the build `exts`/`extscache` deployment
  context needed by local `campfire.app` and `omni.anim.curve.core`.

Healthy Phase 6FZ commands retained absolute lexical paths beneath
`_build/windows-x86_64/release`. Phase 6HO therefore freezes lexical build
spelling through the PowerShell runner while still recording resolved physical
identities for audit. It does not delete registry locks, change ACLs, rebuild
extension caches, or isolate user data.

Both previously reported registry lock files still exist as zero-byte files
owned by the interactive user. The user has FullControl; the sandbox group has
ReadAndExecute. A read-only exclusive-open check found no current competing
holder. This does not erase the Phase 6HN log's confirmed write-denied result;
it only establishes that no holder was observable during the Phase 6HO audit.

## No-Kit fixture

The final fresh preflight root
`artifacts/phase6ho-app-ready-preflight-20260815-3` passed 12/12 cases with zero
Kit launches. It verifies lexical Kit/app/extension paths, the exact formal
command, working directory, expected extension roots, app-ready/lock negative
states, rejection of resolved-away Kit/app paths, and the actual Phase 6FU
guard-command binding. A prior preflight root and a prior smoke-preparation root
that exposed fixture/keyword-binding defects remain preserved and are not
runtime evidence.

## Exact app-ready smoke and safe stop

One new process was launched from
`artifacts/phase6ho-app-ready-smoke-20260815-2`; there was no retry or
replacement. The lexical command restored the local deployment topology:

- `omni.anim.curve.core-1.6.0` registered and started from build `extscache`;
- `campfire.app-0.1.0` registered and started from build `exts`;
- dependency solving completed, Kit reached `app ready`, the extension manager
  was acquired, and `campfire`/`campfire.app` imports succeeded.

The smoke nevertheless failed closed at `campfire_module_path_mismatch`.
The validator required the imported module file's fully resolved path to stay
under the physical build extension root. The build extension's nested
`campfire` directory is itself an intentional junction to
`source/extensions/campfire.app/campfire`, so resolving the imported file
crosses that junction even though Kit's extension manager correctly reports
the build `exts/campfire.app` root. This is an over-strict diagnostic path gate,
not a dependency-solver or production-module import failure. The contract was
not changed after observing the result.

The probe wrote `smoke_failed` and `shutdown_complete`; Kit completed shutdown
and exited with code 1 as requested by the failed probe. No stage was created,
no Flow interface was requested, no proxy Prim was authored, and NanoVDB
readback count remained zero. Therefore the production hierarchy plus one
`FlowCollisionProxy` remains unmeasured and unqualified.

## Resource, lifecycle, and invariants

Peak Private Bytes were runner 96,129,024, Kit 7,367,909,376, diagnostic
16,916,480, and other child 62,607,360 bytes; unique-tree peak was
7,813,689,344 bytes. Minimum available physical memory was 86,352,715,776
bytes and minimum commit headroom was 106,030,129,152 bytes. All frozen limits
passed. Exact cleanup handled observed descendants and final residual count is
zero. There was no native exception, dump, automatic upload, device loss/TDR,
or CDB attach. The nonzero exit is an intentional smoke failure and is not a
qualified normal exit.

Production app/source app, production scene, wood authority, V3, and latest
demo SHA-256 values matched before and after the run. No visual operation was
reached, so no video was created.

## Regression and next boundary

Focused Phase 6HO tests passed 6/6, Python compilation passed, Release build
passed in 7.34 seconds, the standard suite passed 8/8 processes and 78/78 tests
in 322.5 seconds, and static devlog validation passed. Phase 0 RTX and Phase 3
were omitted because production source, USD generation, rendering, wood
authority, and Flow input are unchanged and no diagnostic stage was created.

The bounded audit, no-Kit fixture, lexical launch topology, and dependency
resolution evidence are valid. The exact app-ready smoke and one-proxy boundary
are not qualified. A separately approved Phase may change only the module-path
gate to recognize the build extension root plus its declared nested junction,
then run a fresh smoke/root. Only a fully passing smoke may permit the original
one-proxy boundary. Dynamic transforms, occlusion, PhysX sharing, 20-log
performance, Point policy, production integration, and NanoVDB work remain out
of scope.
