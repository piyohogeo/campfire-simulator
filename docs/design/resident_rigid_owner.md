# Resident rigid-frame application owner

Status: Phase 6DP qualifies a newly constructed `rigid_frame_v1` session through the existing production owner composition. The normal application does not expose this selection yet, and Point remains default OFF.

The probe uses the real native backend, `UsdResidentSnapshotAdapter`, `ResidentPointSidecar`, `ResidentApplicationSession`, `ResidentStageRecoveryOrchestrator`, Kit stage context, and timeline. No duplicate lifecycle or test-only owner is introduced.

The initial offline stage is authored at 37 degrees with the rigid Token before connection. Revision 1 publishes through the existing snapshot schema. While stopped, the log moves to 53 degrees and a new origin; `refresh_layout()` commits layout revision 2. Repeating the same refresh performs no layout replacement. A replacement while running is rejected, as is an attempted rigid-to-legacy migration.

The current stage is exported and reopened, then the real Kit context performs close, attach, and four update drains. The owner rebuilds matching rigid consumers at committed revision 2 and publishes revision 3 after recovery. Final shutdown closes the native backend, adapter, and sidecar, and a repeated close is harmless.

The 11/11 gate result does not enable the normal-app path. The next independent change may expose one explicit default-off setting that selects rigid layout before offline stage authoring. That change must retain legacy as fallback, reject contradictory qualification modes, and be exercised through the normal extension initialization path before adoption.

Wood authority, physical equations, wood JSON, `ResidentPublishedSnapshot`, checkpoint v1, Flow 110.0.0, Sphere/Point schemas, collision, V3T-C, and all production defaults remain unchanged. Live representation migration remains out of scope.
