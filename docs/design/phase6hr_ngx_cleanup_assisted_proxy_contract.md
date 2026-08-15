# Phase 6HR exact NGX cleanup-assisted lifecycle contract

Phase 6HQ at `faa7903` is immutable. Its artifact, contract, guard/parent
`cleanup_failure`, and absence of a proxy run are not modified, reclassified,
or reused as Phase 6HR runtime evidence.

Phase 6HR keeps the Phase 6HQ single canonical evaluator architecture and adds
one narrowly bounded lifecycle outcome. The guard produces canonical evidence;
both the guard final gate and parent consumer recompute the same evaluator over
the persisted evidence. Classification, reason, allowed helper identities, and
killed PID set must agree exactly.

The four terminal classifications are:

- `natural_clean_exit`: no live attempt-owned helper and no cleanup kill;
- `cleanup_assisted_telemetry_exit`: one exact attempt-owned Omniverse
  telemetry transmitter;
- `cleanup_assisted_ngx_exit`: one exact `nvngx_update.exe` direct Kit child
  and one exact System32 `conhost.exe` direct updater child, with at most one
  separately qualified telemetry transmitter;
- `cleanup_failure`: every other structure or any incomplete safety evidence.

Every assisted identity must match PID, creation time, canonical path, attempt,
and continuously observed parent. It must have an exact live psutil/Win32
pre-termination check, a recorded termination time, and exact absence through
both query sources afterwards. The updater path must match the frozen NVIDIA
display-driver DriverStore package expression; the conhost path is exactly
`C:\Windows\System32\conhost.exe`. The bounded Python identity path exposes no
signer query, so Authenticode is explicitly recorded as unavailable rather than
inferred; an explicit mismatch is rejected.

Resource limits remain runner/diagnostic 512 MiB, Kit 16 GiB, unique tree
17 GiB, and physical/commit floors 8 GiB. Retry, replacement, root reuse,
readback, production changes, Point-policy changes, V3 changes, dynamic
transforms, occlusion, PhysX sharing, and video are excluded.

The no-Kit producer-to-consumer fixture uses the actual evidence builder,
atomic JSON writer, bounded reader, and shared consumer. It covers natural,
telemetry, NGX, combined, grace-exit, and exact-cleanup positives plus missing,
duplicate, contradictory, path, identity, parent, cardinality, residual,
marker, and resource negatives. Only a fully qualified fixture authorizes one
fresh app-ready smoke. Only an accepted fresh smoke authorizes one fresh
diagnostic one-proxy boundary.
