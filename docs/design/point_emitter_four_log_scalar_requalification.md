# Phase 6ER corrected four-log geometry and scalar requalification

## Scope and preserved history

Phase 6ER is a production-neutral diagnostic Phase. Phase 6EQ remains a frozen formal safe stop: its artifacts, contract, failed scalar gates, and unstarted 22 conditions are unchanged and are not reclassified. The production application, defaults, Point ordering and schema, wood authority, Flow settings, and 26-vertex CollisionProxy geometry are also unchanged.

## Geometry audit

The legacy `production_four` diagnostic fixture placed both upper logs at yaw 90 degrees, making their world long axes parallel to Y, but separated their centers by only 0.22 m along Y. With a 0.72 m proxy length this produces 0.50 m of centerline overlap. The authored closed Mesh audit measured a minimum signed distance of -0.1014222118 m and found 480 surface Point centers inside another log.

This is a fixture defect, not the production layout. The production Phase 2 scene uses lower centers `(0, +/-0.34, 0.18)` and upper centers `(+/-0.34, 0, 0.50)`, with the parallel logs separated perpendicular to their long axes.

The corrected diagnostic fixture preserves 4 logs, 360 Points per log, and the same 26-vertex/36-face/120-index proxy. It applies the production orientation pattern at the diagnostic scale: lower centers `(0, +/-0.223125, 0.45)`, upper centers `(+/-0.223125, 0, 0.66)`. Offline exact-Mesh checks report:

- other-log surface Point centers inside: 0;
- sampled volume-overlap pairs: 0;
- parallel-pair surface gap: 0.23625 m;
- crossed lower/upper contacts: within the predeclared 1e-6 m contact tolerance;
- corrected geometry SHA-256: `70F7920B6DEB13D4AC05B290C4CB38CAF2ED8B1C99C880AB13A0EBB901F335BF`.

The 1e-6 m tolerance only covers numerical contact. It does not excuse the legacy 0.50 m axial overlap.

## Point classification

The public Flow 110.0.0 API does not expose the exact Point Emitter support radius. Phase 6ER therefore retains 0.05 m, one velocity voxel, only as an engineering support-sphere assumption. Actual Mesh center inclusion and assumed support-sphere intersection remain separate fields.

At the predeclared representative offsets, all active Points have zero other-log support intersections:

| Policy | Offset | Point and weighted supply retention |
| --- | ---: | ---: |
| strict | +0.075 m | 80.00% |
| allow-self-support | +0.025 m | 86.67% |
| allow-self-center | -0.0125 m | 93.33% |

The corrected geometry materially improves the Phase 6EQ fixture result, but retention alone is not a production-adoption gate.

## Scalar calibration and frozen contract

Seven isolated calibration processes completed with normal OS exit: emitterless Collision ON, normal source OFF/ON, temperature-only OFF/ON, and smoke-only OFF/ON. In the emitterless blocker, authored-Mesh boundary, deep, and center temperature/smoke were all zero. Thus the value 1.0 observed in Phase 6EQ is not an ambient baseline in this probe.

Normal-source Collision ON/OFF deep scalar-sum ratios were 0.0775832 for temperature and 0.0571012 for smoke. Based on calibration, the separate Phase 6ER contract froze baseline-relative deep and center ratios, plus opposite-side and far-above ROI ratios, before the formal run. Scalar hard gates apply only to the `lower_upper` fixture because its upper blocker is emitterless. In corrected `production_four`, every log emits, so source ownership and leakage cannot be separated with those scalar ROIs; those values are diagnostic only.

## Formal safe stop

The fresh formal root completed four of 24 planned processes: lower/upper Collision OFF, strict, allow-self-support, and allow-self-center for run 1. All four reached functional pass, `shutdown_complete`, normal OS exit, and complete samples, with fatal, dump, upload, device-lost, TDR, and residual counts of zero.

The first paired strict gate then failed the frozen contract:

| Metric | ON/OFF ratio | Gate | Result |
| --- | ---: | ---: | --- |
| temperature deep sum | 0.07004 | <= 0.15 | pass |
| smoke deep sum | 0.05318 | <= 0.15 | pass |
| temperature center sum | 0.01874 | <= 0.15 | pass |
| smoke center sum | 0.00579 | <= 0.15 | pass |
| temperature opposite-side sum | 1.23189 | <= 0.85 | fail |
| temperature far-above sum | 0.86660 | <= 0.70 | fail |
| smoke opposite-side sum | 1.16482 | <= 0.85 | fail |
| smoke far-above sum | 0.57928 | <= 0.70 | pass |

Deep velocity was 7.9117117 m/s OFF and 0 m/s ON. The authored Mesh therefore suppressed the deep field, but a small downstream ROI can contain more redirected scalar than its Collision-OFF counterpart. That observation does not prove scalar penetration. The present far/opposite metric cannot distinguish through-Mesh transport from legitimate around-obstacle transport.

The run stopped immediately without retry, later conditions, visual capture, or video. Accepted complete population is 0/24, and no self-Collider policy is recommended for production.

## Next boundary

A future separately approved Phase should freeze a control-volume or directional-flux metric that can distinguish entry through the blocker from scalar redirected around it. It must retain deep-Mesh velocity/scalar evidence, use emitterless baselines, and keep Phase 6ER and Phase 6EQ unchanged. No latest-demo update is warranted for this failed internal qualification.
