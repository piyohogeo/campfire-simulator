# Latest change demo workflow

Status: reusable development-log operation. It does not change production defaults or define a benchmark gate.

Each visually observable phase chooses its own small scenario. The scenario runner owns only the phase event sequence and emits a standard manifest containing ordered frame segments, effective Candidate Performance settings, feature flags, Kit logs, crash-dump directories, and qualification evidence. `scripts/build_devlog_demo.ps1` owns the shared boundary: fresh artifact output, 1280×720 Candidate Performance verification, frame size/count/hash checks, fatal/crash/dump/upload rejection, H.264 encoding, lightweight event overlays, 10–30 second duration, poster copy, and the unverified phase manifest.

The common runner never updates the latest pointer. A person or Codex must play the encoded file, inspect its intended event and continuity, then run `scripts/promote_latest_demo.ps1 -PlaybackVerified`. Promotion rechecks the video hash, marks the phase manifest verified, and atomically replaces only `docs/devlog/assets/latest_demo.json`. A failed, ambiguous, cold-initialization, crashed, or unplayed candidate therefore cannot displace the previous verified demo.

The development log loads the small latest manifest and points its common modal at the phase-owned video. Media is not duplicated as `latest_demo.mp4`. Internal-only phases may leave the latest pointer unchanged and record that no new visual difference warranted a video.

Phase 6DR is the first scenario implementation. It records 30 frames before the lifecycle boundary and reuses the existing 60 post-recovery qualification frames. The resulting overlay identifies the 37-degree starting frame and the stopped 53-degree refresh, resume, and replacement-stage recovery boundary. Point and rigid modes are enabled only by the isolated scenario runner. V3 remains OFF, Sphere remains the production default, and the held V3T-M Flow-topology conditions are not executed.

The first verified output is `docs/devlog/assets/phase6/phase6dr_demo.mp4`: H.264, 1280x720, 30 fps, 11.5 seconds, with 89 unique source images among 90 captured frames. The real Kit qualification passed 15/15 gates at Resident revision 710; all configured fatal tokens, native crash dumps, and automatic-upload attempts were zero. Browser playback reached the 11.5-second end without a media error and showed the intended 37-degree to 53-degree rigid-frame change while Flow remained visibly active. The latest pointer now names this phase-owned file; it does not duplicate the media.

Publication regression passed the Release build in 8.49 seconds, Phase 0 RTX with exit 0, and all eight standard processes with 77/77 tests in 355.5 seconds. The in-app browser verified the latest modal, the Phase-owned modal, an existing older-video modal, Japanese text without replacement characters, and zero console warnings or errors. A static reference audit found all 309 local devlog paths present.
