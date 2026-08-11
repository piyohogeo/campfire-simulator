# Phase 6DT — NVIDIA Flow collision reference audit

## 結論

Flow 110.0.0同梱の`data/tests/PhysicsCollision.usda`は、Collision用Emitterではなく、`UsdPhysics.CollisionAPI`を付けた静的MeshをPhysXからFlowへ自動連携する参照sceneだった。同じKit 110.2／Flow 110.0.0環境で、Collision ONはOFFに対して障害物内部と上方のFlow場を強く抑制した。したがって「同梱サンプルも遮蔽しない」「Flow 110.0.0にCollision機能がない」という分類ではない。

Phase 6DSに不足していた最小の安全な成立境界は、`UsdGeom.Mesh + PhysicsCollisionAPI + PhysicsMeshCollisionAPI + convex approximation`だった。同寸法のCubeへ公式schema一式を追加しても場は変わらず、同寸法Meshへ上記USD schemaだけを適用すると遮蔽が成立した。productionは変更していない。

## NVIDIA同梱参照

- 所在: `_build/windows-x86_64/release/extscache/omni.flowusd-110.0.0+110.0.0.wx64.r.cp312.u7f4/data/tests/PhysicsCollision.usda`
- Flow: `110.0.0`
- SHA-256: `EA91AD057A03B783691CB68CE525657CB66CC55AC271D064A5173AF901D1C9A9`
- 正規テスト: `omni.flowusd/tests/test_golden_images_rt2.py`が200 frame進め、同梱golden imageと比較する。
- stage: Y-up、`metersPerUnit=0.01`、PhysicsSceneなし、Torusは静的Mesh、RigidBodyなし。
- Torus schema: `PhysicsCollisionAPI`、`PhysxCollisionAPI`、`PhysxTriangleMeshCollisionAPI`、`PhysicsMeshCollisionAPI`、`PhysxConvexDecompositionCollisionAPI`。
- `physics:approximation=convexDecomposition`、`physics:collisionEnabled=true`。
- Flow sourceは通常の`FlowEmitterSphere`であり、Collision用の`isPhysicsCollision`やtarget velocityによる速度拘束Emitterではない。空のcustom relationship `physicsCollisionPrim`は存在するがtargetはない。
- FlowSimulateはlayer 2、density cell 0.5 stage unit、60 steps/s、`forceSimulate=false`、`physicsCollisionEnabled=true`、`physicsConvexCollision=true`。
- Emitterは`allocationScale=1`、`applyPostPressure=false`、velocity/fuel/temperature couple rate `2/2/10`、`physicsVelocityScale=0`、target velocity 0。

正規Editor appとCampfire隔離appの双方で同じstageを実行した。全sampleのROI平均とactive block数は完全一致したため、今回の差はapp compositionやextension load状態ではない。Flow、PhysX cooking/stage update、Hydra RTX、volumeを含む必要extensionはいずれもロード済みだった。

## 参照sceneのOFF／ON実測

public `get_latest_nanovdb_readback()`、`buffer_to_volume()`、`omni.volume`、同梱`nanovdb` accessorだけを使い、frame 60/120/180/200のbelow／inside core／above／above farを測定した。表は全4時点のvoxel meanについてON/OFF比を示す。

| Channel | inside core | above | above far |
|---|---:|---:|---:|
| temperature | 0.167659 | 0.003147 | 0 |
| smoke | 0.183929 | 0.000915 | 0 |
| burn | 0.175701 | 0.004636 | 0 |
| velocity magnitude | 0.090952 | 0.006754 | 0.0000196 |

active blockはON `265`、OFF `1044`だった。映像でもOFFはTorus内部から上へ炎が通り、ONは下面で広がって内部・上方へほぼ到達しない。数値と映像は一致する。

## Phase 6DSとの差分監査

最初に一項目ずつ移した結果は次のとおり。

| 候補 | 結果 | 分類 |
|---|---|---|
| `PhysxCollisionAPI`だけ追加 | inside/farはbaseline比1.03/1.00前後 | 不要・不十分 |
| `forceSimulate=false`だけ | far temperature 0.903、他channelは0.95～1.14 | 不要・不十分 |
| Flow layer 2だけ | 主要ROI 0.99～1.03 | 不要・不十分 |
| `physicsConvexCollision=false`だけ | 主要ROI 0.97～1.12 | 不要・不十分 |
| 空`physicsCollisionPrim` relationshipだけ | 明確な遮蔽なし | 不要 |
| 公式schema一式をCubeへ追加 | 全channel・全ROIがbaselineと完全一致 | type境界を解決しない |
| 同寸法Mesh、collision schemaなし | baselineと完全一致 | negative control |
| 同寸法Mesh、USD最小schema、convexHull | inside scalar 0、above/far scalar 0 | 成立 |
| 同寸法Mesh、USD最小schema、convexDecomposition | inside scalar 0、above/far scalar 0 | 成立、3独立run一致 |
| 公式PhysX schemaを含むMesh | USD最小schemaと完全一致 | 追加PhysX schemaは静的Boxでは不要 |
| 成立MeshでFlow側Collision OFF | far temperature 0.997、smoke 1.032、velocity 0.986 | negative control成立 |

`approximation=none`はbelowを含む全sample fieldが0となり、Emitterまで消える退化条件だった。正常な遮蔽とは扱わない。Collider側`physics:collisionEnabled=false`は、この固定環境ではFlow遮蔽を停止しなかった。Flow側の`physicsCollisionEnabled=false`は場を非遮蔽へ戻した。Flow 110.0.0は適用schemaを取り込み条件として扱っている可能性が高いが、内部実装や保持形式は公開証拠がないため断定しない。

`Mesh + PhysicsCollisionAPI`だけのablationはstage open前のRTX/Hydra/Fabric初期化中にnative `0xC0000005`となった。同条件は自動再実行せず、正式母集団から除外した。dumpはGit外の`artifacts/phase6dt-reference-audit-2/phase6ds_mesh_collision_only/run-1/sensitive-crash-dumps/`に保全し、自動upload attemptは0だった。この単発startup crashをschema削除の因果とは扱わず、この一点だけは未判定とする。

## Phase 6DRへの更新された説明

Phase 6DRの現行薪Colliderは`UsdGeom.Cylinder`へ`PhysicsCollisionAPI`だけを適用している。Phase 6DSのCubeと同じprimitive-onlyクラスであり、公式参照が使うFlow取り込み可能なMesh collision表現ではない。したがって炎の薪貫通の最有力説明は、Flowが使えるcooked Mesh collision境界が薪に存在しないことになった。ray-marchだけの錯視、Flow機能そのものの欠如、app差ではない。

これはproductionへMesh proxyを直ちに入れる判断ではない。次の独立Phaseでは、まず静的なCylinder相当Mesh proxyで遮蔽、rotation、Emitterとの距離、cooking時間、20本の更新・メモリ負荷を確認する。静的Cylinderが成立してから、動的TransformとPhysX/Flow更新lifecycleを測る。既存のanalytic Cylinder collider、wood authority、Flow入力、Emitter、V3、checkpoint、rollback、serializationはその承認まで変更しない。

## Safety and evidence

Release buildは`7.25 s`で合格した。共有productionコードとapp構成を変更していないため、Phase 0 RTXと標準suite全体は再実行していない。代わりにFlow sceneのCollider契約を直接覆う`campfire.app.tests.test_scene.TestScene.test_flow_scene_has_emitter_simulation_and_colliders`を隔離Kit processで実行し、`1 / 1`件、test time `0.078 s`で合格した。

正式19 processはexit 0、fatal 0、native crash 0、dump 0、自動upload attempt 0、すべて`shutdown_complete`だった。除外診断1件だけがnative crashとなり、dumpをローカル保全した。全正式runでproduction app SHA-256は前後一致した。

machine-readable evidenceは`docs/devlog/assets/phase6/nvidia_flow_collision_reference_raw.json`と`nvidia_flow_collision_reference_report.json`、可視化は`nvidia_flow_collision_reference_report.svg`、比較映像は`nvidia_flow_collision_reference_comparison.mp4`に保存した。開発日誌のlatest demo pointerは変更していない。
