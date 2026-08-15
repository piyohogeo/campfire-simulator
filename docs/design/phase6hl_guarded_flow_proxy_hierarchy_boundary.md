# Phase 6HL — deterministic guard interpreter and one-proxy hierarchy boundary

Phase 6HK remains frozen at commit `bfc7a0a` as
`safe_stop_pre_kit_harness_failure`. Its artifact root, contract, thresholds,
and classification are neither modified nor reused. Phase 6HL uses a new
contract and root and changes only the harness interpreter boundary before
running the identical diagnostic one-proxy condition.

## Read-only interpreter audit

The successful Phase 6FU qualification and Phase 6FZ 9/9 population launch
`phase6fu_resource_guard.py` through the first `Get-Command python.exe`, which
on this qualified machine resolves to `C:\Python38\python.exe`. It is CPython
3.8.3; `sys.executable` resolves to the same absolute path; psutil 5.9.8 is at
`C:\Python38\Lib\site-packages\psutil\__init__.py`. The Phase 6FZ parent is
PowerShell, the guard is system Python, the guarded case runner is PowerShell,
and Kit `--exec` uses `_build/windows-x86_64/release/kit/kit.exe` and its
embedded Python 3.12 environment.

Phase 6HK instead formed its guard command from `sys.executable`. Codex had
started that runner with `tools/packman/python.bat`, so the propagated
interpreter was
`C:\packman-repo\python\3.12.13-nv3-windows-x86_64\python.exe`. That
environment intentionally isolates user packages and has no psutil. Phase 6HL
does not install or alter anything there. The new contract records the exact
system interpreter and executable/module hashes; there is no PATH lookup or
fallback during execution.

## Frozen preflight and runtime scope

The no-Kit preflight runs a bounded import probe and the actual Phase 6FU guard
command. It proves exact selected path and `sys.executable`, psutil path/version,
guard import and callable `main`, exact target-argument forwarding (including
spaces), direct file streaming, bounded summary creation, child PID/create
time/path/parent identity, explicit cleanup, and residual zero. Packman Python,
missing psutil, interpreter mismatch, guard import failure, missing summary, and
argument mismatch are distinct fail-closed fixtures. A failed preflight starts
no Kit process.

Only a passing preflight permits one fresh Kit process. The runtime wrapper
pins the Phase 6HK probe SHA-256 and changes only its Phase identity from 6HK to
6HL, preserving the exact production Phase 2 hierarchy, one invisible
`/World/Logs/Log_00/FlowCollisionProxy`, 26/36/120 closed Mesh topology,
collision schemas, convex decomposition, stopped timeline, 30 renderer frames,
Flow-interface check, release-after-close order, and zero readback operations.
Flow occlusion, dynamic transforms, PhysX Mesh sharing, Point policy,
PointEmitter coexistence, 20-log cost, production readiness/defaults, V3, P5,
and latest-demo changes remain out of scope.

## Result

Contract SHA-256
`E890157C17C4392C88E429D5AD8C8451CB57A6AA66E045E211E89D13A05E6D04`
was frozen in a new empty artifact root. The persisted preflight passed all
nine cases: exact system interpreter, Packman rejection, missing psutil,
`sys.executable` mismatch, guard import failure, summary absence, command
binding mismatch, the actual guard command, and no fallback. The exact fixture
streamed output to files, preserved a path and argument containing spaces,
recorded child PID/create time/path/parent, produced a bounded guard summary,
and left guard/child residual zero. Packman Python was not modified.

The single formal launch then stopped after 1.629 seconds, before the Phase 6HL
probe or any stage marker. Unlike the successful Phase 6FZ path, this runner
gave Kit directly to the guard instead of guarding a small PowerShell case
runner. The frozen legacy role function labels the guarded root `runner` before
checking its executable name; the root was the Kit executable but its
1,845,035,008-byte Private Bytes therefore hit the 512 MiB runner limit. The
reported Kit-role peak is consequently zero and must not be read as a Kit
measurement. Unique-tree peak was 1,866,956,800 bytes; available physical and
commit-headroom minima were 91,069,804,544 and 110,720,606,208 bytes.

Phase 6HL is a resource-role harness safe stop. Kit launches are 1, accepted
runtime samples are 0, and there was no proxy authoring, stage connection,
renderer frame, Flow-interface acquisition, stage close, or durable
`shutdown_complete`. The guard returned nonzero, but exact observed-process
cleanup and final Kit/CDB/NanoVDB residual checks are zero. This is not evidence
for or against the hierarchy proxy. No retry or replacement was attempted;
Phase 6HK remains frozen and unchanged. A future separately approved Phase
must make a small guarded runner the root (or otherwise qualify role-aware
limits) before using a new contract and artifact root.

Regression passed the 10/10 focused suite, Python compilation, Release build
in 7.62 seconds, the standard 8-process 78/78 suite in 321.7 seconds, and static
devlog validation. Production app SHA-256 remains
`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A` and
latest-demo SHA-256 remains
`1C6FB249EAE8DF09E804680C7D0459BA8631D4ECFF4903944FFA4701E94E6285`.
Phase 0 RTX and Phase 3 were not rerun because this Phase changes only
diagnostic scripts/contracts/documents; production sources, USD generation,
render settings, wood authority, and Flow inputs are byte-for-byte unchanged.
