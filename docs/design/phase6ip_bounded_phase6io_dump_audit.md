# Phase 6IP — bounded read-only audit of the frozen Phase 6IO exception

Phase 6IO remains frozen as recorded at `c7fef78`. The Phase 6IP analysis did
not launch Kit, did not run Stage/Layer/Flow work, and did not start A/B/C. It copied the
frozen evidence into a new analysis root, verified every selected source before
and after the audit, streamed the archive extraction, and ran the installed x64
CDB exactly once with local module paths only. CDB exited normally in 9.25 s;
there was no timeout, forced debugger cleanup, upload, or original-file change.

After the audit was complete, `repo.bat build` was run for regression checking.
Its dependency-precache step internally launched three short Kit extension
precache processes. They did not open the frozen Phase 6IO process, dump,
Stage, Layer, or Flow, and the Release build passed, but they violate the
Phase-wide no-Kit-launch constraint. Phase 6IP is therefore recorded as
`safe_stop_post_analysis_kit_launch_contract_deviation`; the bounded dump
findings below remain valid evidence, not a fully contract-qualified Phase.

## Integrity and bounded execution

The primary archive is 1,631,923 bytes with SHA-256
`7C77B77414BABE3267483DEFC134FB5EF97BBD8DA9C7843F398B6A3A5FF98B28`.
The extracted user minidump is 9,257,417 bytes with SHA-256
`13C32AAF5421495AEE76DE27ACA07C6F45D6F981D86DDE7B3E458EE8BEEA5A34`.
It contains x64 registers, stacks, and partial memory. The dump time is
2026-08-16 02:04:23 UTC, target PID is 9100, process uptime is 24 s, and 151
threads are represented. The fixture passed 10/10 before analysis. CDB used
30 s no-output and 120 s absolute limits and wrote stdout/stderr directly to
bounded files. Its stderr was empty. No remote symbol server was configured.

The TOML, Python stack, crash text, Kit log, markers, reports, and the frozen
Phase 6IK bounded audit were also hashed and copied. All 11 selected originals
matched their contract before and after CDB. Full inventory and hashes are in
the machine report and `artifacts/phase6ip_phase6io_dump_audit_20260816`.

## Localized exception

CDB confirms that the stored exception is `0x80000003` at
`carb.crashreporter-breakpad.plugin.dll+0x44f34` (module base
`0x00007ff8fa600000`). The instruction is byte `CC`, `int 3`. Nearby code calls
a location named relative to the exported `crashIntentionallyDueTo` symbol
before executing the breakpoint. This is strong evidence that the recorded
exception is an intentional crash-reporter breakpoint, not a random execution
of invalid memory. It does not by itself establish why termination began.

The stored exception context selects CDB thread 16, OS TID `0xD9F4` (55796).
The reporter text instead calls TID 53692 (`0xD1BC`) the crash thread; the
all-thread dump captures that thread in `NtGetContextThread`. Both facts are
retained. The reporter value is not substituted for the debugger exception
context.

The representative native unwind is:

```text
carb.crashreporter-breakpad.plugin+0x44f34  (int 3)
carb.crashreporter-breakpad.plugin+0x2d889
carb.crashreporter-breakpad.plugin+0x1c7bd
ucrtbase!raise
ucrtbase!abort
ucrtbase!terminate
VCRUNTIME140!CxxThrowException
omni.usd!omni::usd::audio::waitForCapture+0xc65f
omni.usd!omni::usd::UsdManager::getFoundationPlugins+0xf23
omni.usd!omni::usd::UsdContext::useFabricSceneDelegate+0x8e13
carb.tasking.plugin+0x230bb
```

The `omni.usd` names are nearest export symbols; private symbols are absent, so
they localize the module and shutdown/tasking family but cannot prove the exact
private routine or original C++ exception type. There is terminate/abort
evidence, but no direct assert or fail-fast signature.

## Shutdown timing and resource rise

`shutdown_complete` was durable at UTC epoch 1786845856.8067493. The dump time
places the exception about 6.19 s later; the parent observed process exit at
9.90 s. Between the 2.02 s and 5.03 s samples, CPU time rose by 24.125 s and
Private Bytes rose by 1,282,002,944 bytes.

The Kit log adds an important bounded sequence: at roughly 4.95 s after the
shutdown marker, `omni.rtx` reports three semaphore-release failures, detects a
GPU crash, and writes `kit-0.nv-gpudmp`; Breakpad then reports termination and
writes the minidump. The CPU/memory rise therefore aligns with RTX teardown,
GPU-dump capture, and crash-report construction. It is not evidence that any
Stage, Flow, or A/B/C operation ran. A user minidump cannot assign those
allocations to an exact owner.

## Comparison with Phase 6IK

| Evidence | Phase 6IK | Phase 6IO |
|---|---|---|
| Exception | `0xC0000005` write AV | `0x80000003` breakpoint |
| Recorded module | `omni_usd` | `carb.crashreporter-breakpad.plugin` |
| Location | `UsdContext::addHydraEngine+0x288` | `+0x44f34`, `int 3` |
| Shutdown delay | 4.938714 s | about 6.193251 s |
| Stack family | Hydra/USD context | reporter → terminate/abort → USD audio/context/tasking |
| RTX evidence | not established by the frozen audit | semaphore failure and GPU-dump sequence in Kit log |

Classification is `related_candidate` with medium-low confidence. Both are
post-`shutdown_complete` and touch the USD/context teardown family, but the
stored exception module, instruction, and immediate mechanism are different.
They are neither proven identical nor proven unrelated.

## Result and next boundary

- `artifact_integrity = qualified`
- `dump_parse = partial` because this is a user minidump and `ntdll` symbols do
  not match; explicit exception context and stacks were still available.
- `exception_localization = localized` for the stored breakpoint.
- `phase6ik_relation = related_candidate`
- `production_relevance = indeterminate`
- `cleanup = qualified`

The read-only analysis axes above pass independently, but the Phase-wide Kit
launch contract does not. No further Kit-based regression was run.

Phase 6IO is not reclassified. A/B/C is not ready to resume from this evidence
alone. Natural exit code 0 remains required for lifecycle qualification;
operation evidence after durable completion may remain a separate partial axis,
but it cannot substitute for production lifecycle success. If separately
approved, the smallest next observation is a bounded few-process Stage-free
post-shutdown population with the unchanged monitor, retaining full crash
evidence only for the first signature. No fix, repetition, or A/B/C launch was
performed in Phase 6IP.

The focused no-Kit archive fixture passed 10/10 twice, Python compilation and
JSON validation passed, and static devlog validation passed (`refs=602`,
`ids=345`, `json=298`, `svg=177`, `zip=2`). The Release build passed but caused
the three-precache-launch deviation above. The standard suite, Phase 0 RTX, and
Phase 3 were not run afterward: they would add further Kit launches, and no
production source, USD authoring, renderer input, wood authority, Point policy,
or physics parameter changed.
