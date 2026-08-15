# Phase 6HD operation counter and lifecycle contract

Status: frozen before runtime. Base commit: `aa78bae`. Contract SHA-256:
`579A01C4F18C324624513865A6786AEF05FD27328149B4E24111E96D551C8C13`.

Phase 6HC remains a canonical-report completeness safe stop. No Phase 6HC
artifact, classification, or documentation is changed or reused.

## Single counter schema

`phase6hd_operation_schema.py` is the sole owner of the counter tuple, integer-
zero factory, runtime report producer, JSON writer, reader, normalizer,
condition expectations, and parent validator. Its canonical keys are:

1. `readback`
2. `array_metadata`
3. `schema_volume_conversion`
4. `schema_metadata`
5. `schema_temporary_save`
6. `schema_typed_read`
7. `velocity_save`
8. `velocity_sampling`
9. `velocity_collector`
10. `temperature_conversion`
11. `temperature_metadata`
12. `temperature_save`
13. `temperature_typed_read`
14. `temperature_sampling`
15. `temperature_collector`

The factory always emits every key with a value whose exact Python type is
`int` and whose initial value is zero. Serialized artifacts contain canonical
keys only. The adapter for the frozen HB implementation exists only inside the
runtime counter mapping. Unknown keys are rejected as
`call_count_unknown:<key>`; missing required keys as
`forbidden_call_missing:<key>`; bool/null/string/float as
`call_count_type_invalid:<key>`; and nonzero operations not allowed by the
condition as `forbidden_call_nonzero:<key>`.

## Exact producer-to-consumer route

The no-Kit fixture invokes `new_counter_values()` and `new_runtime_report()`,
updates the report only through the shared counter/checkpoint helpers, writes it
with `write_operation_report()`, then gives the resulting
`post_readback_isolation.json` without normalization or field injection to
`validate_operation_files()`, the same entry point called by the parent runner.
Negative cases mutate the already serialized producer output. Deleting every
individual key must break the complete route.

## Runtime scope

After the fixture passes, Phase 6HD uses a fresh root and independent processes
for unchanged A--F: readback/release; all-slot bounded metadata; non-temperature
slots 1--5 schema work; velocity save/sample/profile without collector; four
collector use; and temperature alias hold/release. Every condition runs once;
the first non-normal canonical operation, lifecycle, resource, cleanup, or
residual result stops later conditions.

Temperature conversion, metadata/content, save/typed read, sampling, and
collector work remain prohibited. Existing 16/17 GiB and child limits, 8 GiB
machine floors, one-Kit rule, attempt-local allowlist, unknown-file refusal,
release-after-close, and residual-zero requirements remain unchanged. Formal
comparison, video, production, defaults, Point policy, V3, and P4 are excluded.
