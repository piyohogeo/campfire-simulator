# Resident rigid layout in the normal application

Status: Phase 6DQ qualifies one explicit default-off setting through the normal extension initialization path. Point and rigid layout remain default OFF, and Sphere remains the production default.

`/exts/campfire.app/residentPointRigidLayoutEnabled` is read only as part of the Resident Point startup configuration. When both Point and rigid layout are explicitly enabled, the extension resolves `rigid_frame_v1`, extracts one right-handed frame per log, builds the native 720-point layout, pre-authors the matching Point schema, and composes the existing application owner before connecting the stage to Kit. With the rigid setting absent or false, the existing `legacy_cardinal_axes_v1` path is unchanged.

Configuration validation runs before any offline stage is created. Rigid selection without the Point opt-in, qualification settings without Point, multiple primary qualifications, invalid dynamic-translation dependencies, and any mix of rigid selection with the legacy qualification scenarios fail closed. The previously qualified legacy timeline plus dynamic translation plus unchanged-layout skip combination remains valid.

The real Flow 110.0.0 normal-application run passed 11/11 gates with 720 points, revision 710 across all consumers, zero Point resyncs, zero layout replacements, 391 peak active blocks, 58 unique images across 60 captured frames, and clean owner shutdown. The standard eight-process suite passed 77/77 tests in 379.5 seconds after a successful release build and Phase 0 launch.

This phase does not enable Point or rigid layout by default, migrate an active session, change the snapshot schema, or change wood authority, collision, rollback, Flow, V3T-C, or visual presets. The next isolated gate is a normal-app scenario with an arbitrary pre-authored log rotation followed by stopped transform refresh and stage recovery.
