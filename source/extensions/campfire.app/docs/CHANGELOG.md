# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).


## [0.1.0] - 2026-08-04
- Added deterministic Phase 0 scene generation and headless capture.
- Added Phase 1 NVIDIA Flow scene, metrics, and readback validation.
- Added Phase 2 dynamic rigid logs, persistent IDs, controls, emitter following, and fixed-step validation.
- Added Phase 3 wood thermal cells, moisture evaporation, pyrolysis, char, mass accounting, persistence, and Flow fuel output.
- Added Phase 4 placement-aware air supply, oxygen-limited heat feedback, dense-stack/log-cabin comparison, and headless validation.
- Added Phase 5 cross-section support loss, joint release, mass/collider updates, PhysX collapse, reignition, and headless validation.
- Added Phase 6A fixed NIST plywood reference data, equivalent-coupon calibration search, USD/SVG result views, and headless validation.
- Added Phase 6B no-refit OSB external-material holdout evaluation and a separate browser-readable residual report.
- Added Phase 6C fixed SAMP.1/2-to-SAMP.3 plywood replicate holdout evaluation and a separate browser-readable report.
- Added Phase 6D nominal 12.7 mm five-ply planar specimen model, mass-derived effective density, through-thickness conduction, and layer-temperature report.
- Added Phase 6E first-order Arrhenius pyrolysis, fixed SI-unit literature pairs, 48-candidate calibration, and a browser-readable rate curve.
- Added Phase 6F competing gas/tar/char first-order pathways, explicit product mass and yield accounting, and a constrained 16-candidate common-scale search.
- Added Phase 6G sourced plywood/OSB conductivity and heat-capacity profiles, preserved mass-derived coupon density, and explicit unresolved adhesive-interface metadata without invented geometry.
- Added Phase 6H USDA-FPL normalized dry-wood cp(T), clamped to its published 280-420 K range with constant-model backward compatibility and explicit negative validation results.
- Added Phase 6I bounded secondary tar-to-gas diagnostics using the NIST Model III coefficients and a fixed one-second residence scenario without altering total volatile release or solid heat balance.
- Added Phase 6J experiment-bounded 0.9/1.0/2.2-second secondary-tar residence sensitivity, isolated from parameter selection, with a browser-readable yield report.
