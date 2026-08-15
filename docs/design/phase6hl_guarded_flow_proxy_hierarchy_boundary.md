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
