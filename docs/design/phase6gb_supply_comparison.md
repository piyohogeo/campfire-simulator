# Phase 6GB — explicit geometry binding and supply comparison

## Frozen history and scope

Phase 6GA remains a frozen pre-Kit safe stop. Its conceptual geometry value
`corrected` reached the shared PowerShell runner unchanged, while that runner's
runtime `ValidateSet` accepts `phase6er_corrected`. Phase 6GA therefore produced
no Flow, readback, memory, lifecycle, or visual evidence and is not retried or
reclassified here.

Phase 6GB changes only the diagnostic harness boundary. Production code,
geometry, transforms, the 1,440-Point payload, source sums, Flow settings,
CollisionProxy, V3, thresholds, and defaults remain unchanged.

## Geometry token contract

The SHA-pinned contract stores two distinct fields:

- design concept: `corrected`
- case-runner runtime token: `phase6er_corrected`

The mapping is explicit and fail closed. `corrected` is never passed directly
to `-GeometryVariant`; an unknown runtime token is rejected by PowerShell
parameter binding, and `legacy_phase6ep` is rejected when the expected concept
is `corrected`. The shared case runner independently checks the pair before it
can start Kit.

The no-Kit binding fixture invokes the actual case runner through a full
PowerShell command line and records the final Kit argument vector without
starting Kit. It requires one positive and three negative cases:

1. `corrected -> phase6er_corrected`: accepted;
2. direct runtime token `corrected`: rejected by runtime validation;
3. unknown runtime token: rejected by runtime validation;
4. `corrected -> legacy_phase6ep`: rejected by the mapping boundary.

The fixture report and each stdout/stderr file are bounded. A new `kit.exe`
PID during any case is a fixture failure.

## Frozen physical and safety contract

After the binding fixture, Phase 6FZ app-ready import smoke, progress-aware CDB
fixtures, and the existing offline geometry gate pass, the formal population
starts from an empty artifact root. It is the unchanged balanced nine-process
population:

- S93 collision ON: 1,344/1,440 Points, fuel 1,075.2;
- S100 collision ON: 1,440/1,440 Points, fuel 1,152.0;
- S100 collision OFF: the same 1,440 Points and transform.

Each condition runs three times. Public readback occurs at frames 180, 360, and
540. Authored Mesh boundary/deep regions, baseline-subtracted temperature,
smoke and fuel, and directional control-volume transport remain unchanged.
The hard gates remain: ON deep velocity at most `1e-4 m/s`, OFF deep velocity
at least `0.1 m/s`, S100/OFF suppression at most `0.01`, S100/S93 weighted fuel
at least `1.07`, and deep scalar, opposite transport and floored deep-velocity
ratios at most `1.25`.

Safety remains Kit 16 GiB, unique tree 17 GiB, runner/diagnostic 512 MiB each,
physical and commit floors 8 GiB, release-after-close, durable pre-close
commit, Phase 6FU exact cleanup, Phase 6FW PID-reuse policy, and the Phase 6FZ
progress-aware CDB path. Operation, resource, artifact, identity, or cleanup
failure is nonreplaceable. Only the frozen startup-prerequisite replacement
rule applies.

## GPU and visual boundaries

Existing launch evidence is authoritative for GPU selection: active RTX device
is RTX 3090, CUDA ordinal 0, RTX mask `0x1`, and PhysX device 0. Incidental RTX
2070 activity is neither a warning nor a stop while those selections hold.

Only a numerically qualified population may produce fixed-camera S93/S100/OFF
comparison media. The media is explanatory, not a substitute for numeric
evidence. Clearly visible penetration rejects S100 as a production candidate.
Phase 6GB does not integrate production, change defaults, start P4, or qualify
dynamic/deformed geometry.
