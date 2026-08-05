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
- Added the Phase 6N 24-slot matched char-depth measurement contract, strict CSV readiness gate, and SVG report.
- Added the Phase 6O synchronized experiment execution plan, 24-run schedule, raw-data templates, external authorization gate, and SVG report.
- Added the Phase 6P offline run-package dry run with safe blank files, exact CSV headers, non-overwrite behavior, import/authorization gates, and SVG report.
- Added the Phase 6Q responsible-laboratory handoff contract with 9 runtime fields, 3 evidence records, 4 review fields, UTC/type checks, a non-authorizing gate, and SVG report.
- Added the Phase 6R CPU wood-model benchmark and hot-path optimizations while preserving equations, grid, timestep, ignition behavior, and mass balance.
- Added Phase 6S repeatable startup, CPU, USD, Flow, capture, and finalization timing segments with strict sample-count validation and an aggregate SVG report.
- Added Phase 6T opt-in timings for eight CPU wood-step segments, authoritative-state SHA-256 checks, repeated-profile aggregation, and phase/fixed-cp hot-path improvements without changing equations, grid, or timestep.
- Added the Phase 6U Python/NumPy/Warp float64 backend boundary benchmark, including AoS conversion, CUDA transfers, synchronization intervals, exact isolated state checks, and a no-roundtrip-GPU decision report.
- Restored the standard Phase 6V coverage path by separating 39 coverage-instrumented checks from one deterministic calibration grid search while retaining all 40 tests and the generated ExtensionActions API documentation check.
- Added the opt-in Phase 6W complete-step NumPy backend for sensible heat and final-state classification, exact 400-step equivalence gates, controlled performance evidence, Phase 3 output hashes, and a debugger-contamination exclusion decision while retaining Python as the default.
- Added the Phase 6X debugger-free benchmark application, runtime debug-extension gate, isolated Phase 3 scene output, alternating paired backend runner, exact output digests, end-to-end evidence retaining Python as the default, and a coverage-preserving 35 + 4 + 2 standard test partition.
- Added Phase 6Y opt-in timings for eight Python wood-step segments in the debugger-free Phase 3 application, three-run invariant validation, candidate selection, and JSON/SVG reporting.
- Added a Phase 6Z conservative performance gate comparing three profiled and three unprofiled runs before and after a sensible-heat loop trial, preserving the original loop when end-to-end timing did not improve.
- Added the Phase 6AA exact zero-area surface-boundary path, alternating three-pair debugger-free adoption gate, authoritative output checks, reproducible JSON/SVG evidence, and a default Python-path end-to-end speedup.
- Added opt-in Phase 6AB state-finalize diagnostics for per-log temperature and mass clamps, phase assignments, and actual phase transitions, with timing excluded from performance evidence.
- Added the Phase 6AC conditional state-clamp path preserving every temperature/mass bound plus NaN and negative-zero behavior, with profiled and alternating-pair adoption evidence.
- Added Phase 6B no-refit OSB external-material holdout evaluation and a separate browser-readable residual report.
- Added Phase 6C fixed SAMP.1/2-to-SAMP.3 plywood replicate holdout evaluation and a separate browser-readable report.
- Added Phase 6D nominal 12.7 mm five-ply planar specimen model, mass-derived effective density, through-thickness conduction, and layer-temperature report.
- Added Phase 6E first-order Arrhenius pyrolysis, fixed SI-unit literature pairs, 48-candidate calibration, and a browser-readable rate curve.
- Added Phase 6F competing gas/tar/char first-order pathways, explicit product mass and yield accounting, and a constrained 16-candidate common-scale search.
- Added Phase 6G sourced plywood/OSB conductivity and heat-capacity profiles, preserved mass-derived coupon density, and explicit unresolved adhesive-interface metadata without invented geometry.
- Added Phase 6H USDA-FPL normalized dry-wood cp(T), clamped to its published 280-420 K range with constant-model backward compatibility and explicit negative validation results.
- Added Phase 6I bounded secondary tar-to-gas diagnostics using the NIST Model III coefficients and a fixed one-second residence scenario without altering total volatile release or solid heat balance.
- Added Phase 6J experiment-bounded 0.9/1.0/2.2-second secondary-tar residence sensitivity, isolated from parameter selection, with a browser-readable yield report.
- Added Phase 6K independent one-dimensional Darcy gas-transport diagnostics, an explicit five-input plywood readiness gate, and a browser-readable no-coupling report.
