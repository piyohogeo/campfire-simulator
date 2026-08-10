# Phase 6DS — Flow collision occlusion probe

## Decision

Flow 110.0.0の公開PhysX collision連携は、この最小sceneの軸平行・静止Boxを数値的に遮蔽しなかった。`physicsCollisionEnabled=true`と`physicsConvexCollision=true`はstage接続後も実効値として取得できたが、Box内部coreおよびBox上方far ROIのtemperature、smoke、burn、velocityはCollision OFFとほぼ同じだった。したがってCylinder、斜め配置、動的Transform、Phase 6DR実配置には進まない。

これはproduction修正ではない。Phase V3T-R、V3T-M、wood authority、Flow入力、Emitter schema、物理式、checkpoint、rollback、serialization、production既定値は変更していない。

## Scene and method

- Kit 110.2、Flow 110.0.0、Z-up、SI単位。
- Flow graph全体、Box、Emitter、PhysicsScene、camera、materialをoffline stageへ構築してからKit contextへ接続した。live stage上のPrim削除・再定義はない。
- Flow density cellは`0.025 m`。公開velocity NanoVDBの実効voxel sizeは全12 runで`0.0500000007 m`だった。
- Boxは`2.0 × 2.0 × 0.25 m`、静的、軸平行、不透明、`UsdPhysics.CollisionAPI`適用、RigidBodyなし。厚さは実効velocity cell約`5.0`個分。
- Sphere Emitterは中心`(0, 0, 0.55) m`、半径`0.10 m`。Box下面との解析的最小距離は`0.225 m`、velocity cell約`4.5`個分で、全Emitter sampleはBox外部である。
- Collision OFF、ON aligned、ON +0.5 velocity cell、ON +1 velocity cellを別processで各3 run。shiftはそれぞれ`0 / 0 / 0.025 / 0.050 m`。
- 各runはframe 60、90、120、150、180でtemperature、fuel、burn、smoke、velocity、divergenceを公開`get_latest_nanovdb_readback()`から取得した。`buffer_to_volume()`、公開`omni.volume`、同梱`nanovdb` world/index transformとread accessorだけを使った。velocityはベクトルの大きさとして集計した。
- ROIはbelow、inside、inside_core、above、above_far。inside_coreとabove_farはBox表面から少なくとも1実効velocity cell離し、境界1セルのにじみと障害物全体の通過を分けた。

## Numeric result

下表は全3 run・全5時点におけるvoxel meanの平均とCollision OFF比である。

| Condition | Channel | inside_core mean / OFF | above_far mean / OFF |
|---|---|---:|---:|
| OFF | temperature | 0.041275 / 1.000 | 0.042915 / 1.000 |
| ON aligned | temperature | 0.041624 / 1.008 | 0.042969 / 1.001 |
| ON +0.5 cell | temperature | 0.041976 / 1.017 | 0.042622 / 0.993 |
| ON +1 cell | temperature | 0.041976 / 1.017 | 0.042622 / 0.993 |
| OFF | smoke | 0.022800 / 1.000 | 0.015977 / 1.000 |
| ON aligned | smoke | 0.022829 / 1.001 | 0.016151 / 1.011 |
| ON +0.5 cell | smoke | 0.022336 / 0.980 | 0.016219 / 1.015 |
| ON +1 cell | smoke | 0.022336 / 0.980 | 0.016219 / 1.015 |
| OFF | burn | 0.0007169 / 1.000 | 0.0004571 / 1.000 |
| ON aligned | burn | 0.0007199 / 1.004 | 0.0004554 / 0.996 |
| ON +0.5 cell | burn | 0.0007166 / 1.000 | 0.0004584 / 1.003 |
| ON +1 cell | burn | 0.0007166 / 1.000 | 0.0004584 / 1.003 |
| OFF | velocity magnitude | 0.527500 / 1.000 | 0.783277 / 1.000 |
| ON aligned | velocity magnitude | 0.525143 / 0.996 | 0.783214 / 1.000 |
| ON +0.5 cell | velocity magnitude | 0.510414 / 0.968 | 0.789489 / 1.008 |
| ON +1 cell | velocity magnitude | 0.510414 / 0.968 | 0.789489 / 1.008 |

fuelはabove_farで絶対値が`10^-9`程度と小さく比率が不安定だが、alignedはinside_core `0.998×`、above_far `1.009×`だった。0.5-cellと1-cellの全aggregate値は一致し、位置をずらすほど遮蔽量が変わる段階応答はない。active blockは全sampleで非ゼロだった。

ゼロ漏れを合否閾値にはしていない。測定成立だけをgateにし、測定後の分類を「Collision ONでもOFFと同程度に上側へ到達する」とした。

## Visual result

同じfront cameraと同じframe 90/120/150/180を左右に並べた8秒の診断動画では、OFFとaligned ONの双方でvolumeが不透明Box内部から上側へ連続して見える。最終front/side captureでも同じであり、「数値上は遮蔽されるが映像だけ貫通」ではない。8 source frameは全て異なるSHA-256で、RTX初期化途中の静止画ではない。動画は性能母集団外で、開発日誌のlatest demo pointerは変更しない。

## Interpretation boundary

観測事実は、USD属性が要求値であること、公開readback内のROI値、rendered volumeの連続である。現在の最有力説明は、Phase 6DRの疑わしい貫通もray-marchだけの錯視ではなく、現在の公開PhysX/Flow integrationでFlow場が薪Colliderに拘束されていないこと。ただし、ColliderがFlowへ取り込まれない境界、必要な未author schema、stage/lifecycle順、Flow側制約適用のどれが原因かは未確認である。

公開証拠がないため、Flow内部がconvexを保持する、明示voxel maskを保持する、といった実装詳細は主張しない。Eulerian格子上で何らかのsampling/constraintが行われるという一般的推定と、今回の実測を分離する。

次の独立候補は、NVIDIA同梱`PhysicsCollision.usda`との差分をstage接続前に一項目ずつ監査すること。軸平行Boxで遮蔽を再現できるまではCylinder、斜め薪、移動Colliderへ進まない。

## Safety

12/12 processが正常終了し、fatal `0`、native crash `0`、dump `0`、automatic upload attempt `0`、全run `shutdown_complete`、crash registry変更`0`だった。timeline stop、renderer drain、stage close、Flow interface releaseの順序を使用した。production app SHA-256は各run前後で一致した。

Machine-readable evidence is stored in `docs/devlog/assets/phase6/flow_collision_occlusion_raw.json` and `flow_collision_occlusion_report.json`. The final Release build succeeded in `8.75 s`. Because this Phase changes no shared production code, Phase 0 RTX and the full standard suite were not rerun under the requested conditional regression boundary.
