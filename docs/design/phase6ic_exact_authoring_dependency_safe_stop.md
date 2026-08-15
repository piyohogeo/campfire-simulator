# Phase 6IC exact authoring dependency and stage-open safe stop

Phase 6IB remains frozen at commit `7ba4958` as
`safe_stop_kit_stage_authoring_import_harness_failure`. Phase 6IC used a new
contract, dependency manifest, preflight root, and runtime root. No Phase 6IB
artifact or runtime sample was reused or reclassified.

## Contract and implementation

The contract SHA-256 is
`E055062BC6B6385C4E02084EA0E91859B71B56E19AFE8AE6A1E8740D84A09D3C`.
The dependency-manifest SHA-256 is
`E0E45DF4ACDF81EAFFB5DFFEDB6C49540A1826509212A7DE904FBB5AA62A38F9`.
Implementation commit `a651588` removes the two implicit repository-local
imports from the runtime boundary. The exact loader validates and loads, in a
declared acyclic order, `phase6hw_stage_builder.py`,
`phase6hu_atomic_report.py`, `phase6ib_stage_authoring.py`, and
`phase6ib_stage_open_source.py`. Each entry fixes its module identity,
repository-relative and absolute source path, SHA-256, required callable set,
and allowed dependency edges. The loader uses absolute file specs and makes no
permanent `sys.path` change.

The real producer-to-consumer no-Kit fixture passed 18/18. The frozen Phase
6HZ exact-loader regression passed 12/12, Point-policy invariant passed 13/13,
and atomic-report regression passed 15/15. Negative evidence covers missing or
mis-hashed sources, root escape/reparse, same-name shadowing, absolute-path or
callable mismatch, undeclared local imports, duplicate identity, and graph
cycle/order errors.

## One actual Kit attempt

Exactly one fresh Kit process was launched; retry and replacement counts are
zero. The attempt durably recorded app-ready, manifest validation, all four
module loads, callable validation, and registered-schema stage generation.
Both OFF and ON diagnostic stages were generated before the parser fixture
started. The first fail-closed boundary was registered attribute validation of
the reopened stage:

`RuntimeError: attribute_value_mismatch:/World/Flow/Emitter.position`

Thus deterministic authoring dependency loading is qualified as a prerequisite,
but the complete generate/parse/open/validate boundary is not qualified. The
failure is not a parser syntax error and is not a Flow simulation, CollisionProxy
occlusion, resource, or native crash result. No timeline play, Flow update,
public Flow interface, NanoVDB readback, active-block sampling, capture, image,
or video operation was performed.

Error cleanup completed stage close and `shutdown_complete`. Kit returned exit
code 1. Exact cleanup found residual process count zero. Kit/tree Private Bytes
peaked at 7,333,801,984 / 7,761,203,200 bytes, leaving 9,845,067,200 /
10,492,407,808 bytes below the 16/17 GiB limits. Available physical memory and
commit headroom minima were 84,112,379,904 and 104,074,579,968 bytes. No fatal,
native exception, dump, CDB capture, automatic upload, device loss, or TDR was
recorded.

## Scope and next boundary

Phase 6IC is `safe_stop_stage_attribute_validation_failure`. It does not
qualify stage-open, OFF/ON visual comparison, or CollisionProxy occlusion.
Production source, production USD path, defaults, Point policy/payload/revision/
ordering, wood authority, V3, public scene, and latest demo hashes are unchanged.
A new approval, contract, and empty root are required to isolate the registered
`float3` comparison semantics for the emitter position and repeat only the
stage-open boundary. OFF/ON remains blocked.

Post-stop verification passed the Release build in 7.82 seconds, focused tests
7/7, Python compilation, the standard eight-process suite with 78/78 tests in
322.2 seconds, and static devlog validation (`576` references, `332` IDs,
`285` JSON files, `177` SVG files, and two ZIP files). Phase 0 RTX and Phase 3
were not repeated because no production, USD publication, rendering, wood
authority, physics input, or Flow input changed.
