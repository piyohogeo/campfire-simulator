# Phase 6EO Box Mesh collision occlusion recheck

## Purpose and scope

Phase 6DSの初期動画で遮蔽しなかった解析的Box経路を、Phase 6DT〜6ENで成立したFlow向けの閉じたMesh CollisionProxyへ置き換えて再検証する。これはproduction統合ではなく、`Flow 110.0.0`、固定解像度、静的Box、Sphere sourceという隔離条件の診断である。production app、既定値、wood authority、Emitter schema、V3、Resident sessionは変更しない。

## Frozen contract

- schema: `campfire.phase6eo.box-mesh-occlusion-contract.v1`
- SHA-256: `F3A0CE0003F2BDFC6A6B59A61D517700C0961C0417B12EFADA9902EA63ABA1F8`
- Box: 8 vertices / 6 faces / 24 indices、中心Z=1.00 m、寸法2.00 × 2.00 × 0.25 m
- CollisionProxy: `UsdPhysics.CollisionAPI` + `UsdPhysics.MeshCollisionAPI`、`convexDecomposition`
- source: Sphere中心Z=0.55 m、半径0.10 m、表面clearance 0.225 m（4.5 velocity voxel）、fuel 0.8
- Flow: density cell 0.025 m、velocity voxel 0.05 m、frame 60/120/180/200
- 条件差: `physicsCollisionEnabled`だけ。OFFはpositive control、ONはMesh遮蔽。
- 内外判定: 実際にFlowへ渡したBox Meshへのsigned distance。表面から1 velocity voxel以内をboundary band、1 voxelより深い領域をdeep interiorとする。
- hard gate: ON deep/center maximum `<=1e-4 m/s`、OFF deep/center maximum `>=0.1 m/s`、deep ON/OFF ratio `<=0.01`。
- above-far gate: ON/OFF mean ratioはvelocity/temperature/smokeそれぞれ`<=0.1`。OFF側には正の場が必要。

## Observed results

OFF/ONはいずれもfunctional pass、`shutdown_complete`、normal OS exitとなった。active blocksはOFF 62、ON 24、source fuelは双方`0.8000000119`である。fatal、dump、automatic upload attempt、device lost、TDR、cleanup residualは0だった。

OFFのdeep maximumはframe 60/120/180/200で`7.9795 / 7.7708 / 7.7226 / 7.5317 m/s`、center maximumは`6.4927 / 7.3552 / 7.7226 / 6.4603 m/s`だった。ONのdeep/center maximumは全frameで`0 m/s`、worst deep ratioも0である。ON boundary bandには最大`0.3530 m/s`が残るため、境界値を隠さず、hard-zero対象からだけ分離している。

Box上方far ROIのON/OFF mean ratioはvelocity `0.0061183`、temperature 0、smoke 0だった。OFFの最大meanはvelocity `0.92225 m/s`、temperature `0.057685`、smoke `0.022542`でpositive controlが成立した。したがって、数値上はBox深部と上方への継続通過が遮蔽される。

## Visual evidence and limits

同一camera/timelineの180 frameを15 fps、12秒で記録した。OFFではBox上面へ炎・煙が抜け、ONでは上方の炎・煙が消える。Boxが大きく不透明なため、横方向へ迂回した弱いvolumeは動画では目立ちにくい。この動画は「上方遮蔽」の視覚証拠であり、横流量の定量証拠はNanoVDB ROIで補う。

この結果は静的Box MeshとSphere sourceに限定される。PointEmitterのsupport範囲、自身・他薪Colliderとの重なり、dynamic transform、production薪配置、20本性能は未qualifiedである。次は別PhaseとしてPointEmitter–CollisionProxy共存を事前凍結したoffset sweepで評価する。

## Reproduction

```powershell
python -m unittest -v scripts.test_phase6eo_box_occlusion
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase6eo_box_occlusion.ps1
```

正式成果物は`artifacts/phase6eo-box-occlusion-4/`。開発日誌へは集計JSON/SVG、OFF/ON/comparison MP4とposterだけを複製する。過去の失敗root 1〜3は正式母集団へ再利用しない。
