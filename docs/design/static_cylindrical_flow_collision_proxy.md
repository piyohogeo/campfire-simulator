# Phase 6DU — static cylindrical Flow collision proxy qualification

## 結論

Phase 6DUは、最初の`convexHull` preflightでnative `0xC0000005`とdumpを検出したため、安全条件どおり同条件を再実行せず停止した。crashは完全なstageをoffline authorした後、`opening_prebuilt_stage`でHydra／RTXへ接続する境界で発生し、Flow timeline、public NanoVDB readback、viewport captureには到達していない。したがって静的Cylinder Meshの遮蔽、回転、解析的Cylinderとの共存、Flow専用分離は未qualifiedである。

この結果は「Cylinder Meshでは遮蔽しない」という測定ではない。Flow場が生成される前の単発native crashであり、形状、collision schema、Fabric、Hydra、RTX初期化のどれが原因かは未確認である。productionコード、production `.kit`、既定値、latest demoは変更していない。

## Offline形状契約

preflight stageは接続前に全Primとschemaを構築した。Cylinder相当Meshの条件は次のとおり。

- 半径`0.16 m`、長さ`1.8 m`、local axis X、12 circumferential segments。
- 側面12 quad、両端各12 triangle。中心点を含む`26 vertices / 36 faces / 120 indices`。
- 全頂点はfinite、最小face面積`0.006400 m²`、degenerate face 0。
- unique edge 60、全edgeがちょうど2 faceに共有され、open／non-manifold edge 0。
- 側面と端面のoutward windingが全faceで成立。
- extent実測は概ね`[-0.9,-0.16,-0.16]..[0.9,0.16,0.16] m`で要求値と一致。
- `AnalyticCollider`、`RenderSurface`、`FlowCollisionProxy`は同じ`/World/Log` transformを共有し、world matrixは完全一致。
- Emitter中心のlocal Cylinder signed distanceは`0.290 m`、Emitter半径を引いたsurface gapは`0.190 m`。Phase 6DS実効velocity cell `0.050 m`を基準に3.8 cellであり、2 cell条件を満たす。
- proxyは不可視、RenderSurfaceは表示専用clone。今回のpreflightではproxyだけへ`CollisionAPI + MeshCollisionAPI + convexHull`を適用した。

local Cylinder ROIとして`below`、`inside`、`inside_core`、`inside_side_center`、`inside_end`、`above`、`above_far`、`side_outside`をauthor時に確定した。ただしcrashがstage open中だったためvoxel値は存在せず、OFF比は算出していない。

## Native crash境界

- condition: `mesh_hull` run 1。再試行なし。
- Windows exit: signed `-1073741819`、hex `0xC0000005`。
- 最終durable marker: `opening_prebuilt_stage`。
- dump: `artifacts/phase6du-static-cylinder-1/mesh_hull/run-1/sensitive-crash-dumps/953fdc43-2f84-4274-8521-a0756be3cda9.dmp.zip`。
- dump size: `1,516,001 bytes`、SHA-256 `BA2043E0F9BE79A1B957ABDBD283BA73826B7D3D3E395B350251DB432FEB6734`。
- 低confidence stack境界: `omni.fabric.plugin.dll+0xCE5B0` → `usdrt.hydra.fabric_scene_delegate.plugin.dll` → `omni.hydra.usdrt_delegate.plugin.dll` → `rtx.hydra.dll`。
- automatic upload attempt 0、crash関連registry不変、production app SHA-256前後一致。

この署名はPhase 6DTで除外したstage-open crashと同じFabric／Hydra／RTXクラスに見えるが、symbolが不足した単発stackだけで同一原因とは断定しない。dump本体とlogは機密情報を含み得るGit外artifactとして保持する。

## 要求された判断

1. **静的Cylinder相当MeshはFlowを遮蔽できたか**: 未判定。Flow sample前に停止した。
2. **回転後も遮蔽できたか**: 0／37／53度および3D回転は未実行。
3. **convexHullとconvexDecompositionのどちらが適切か**: 未判定。単純凸形状なので`convexHull`をpreflight候補にしたが、runtime結果は得られなかった。
4. **既存解析的Cylinderと安全に共存できるか**: 未判定。共存processとPhysX scene queryには到達していない。
5. **Flow専用proxyとして分離できるか**: 未確立。`physics:collisionEnabled=false`、collision group、filtering、stage reloadは停止条件により未実行。
6. **V3 RenderSurfaceを再利用すべきか**: この証拠では採用しない。12分割Meshのraw配列payload概算は1個約`960 bytes`で、専用proxyとの単純なraw重複は約`1,920 bytes`。USD／PhysX cooked memoryは未計測である。将来変形するRenderSurfaceの再利用は、表示topologyとcollision cooking authorityを結合するため、runtime qualificationなしでは専用proxyより危険が大きい。
7. **dynamic Transform／Phase 6DR実配置へ進めるか**: 進めない。まずstage-open native crashの再現条件を独立Phaseで安全に分類し、静的axis-aligned Meshの数値遮蔽を取得する必要がある。

## 非実行matrixと停止理由

要求されたprimitive、schemaなしMesh、`convexHull`、`convexDecomposition`、Flow Collision OFFの各3 runは、最初の成立候補preflightでdumpが出たため正式母集団を開始していない。accepted processは0、Flow ROI sampleは0、比較画像／動画は0である。無効なrunを映像や数値の正式成果へ混入させない。

回転、共存、PhysX scene query、proxyのPhysX除外、RenderSurface clone比較、stage reload、dynamic Transform、running refresh、20本、production統合もすべて未実行である。これらを自動的に続行するとユーザー指定の停止条件へ反する。

## 実装と再現経路

- `scripts/probe_phase6du_static_cylindrical_collision.py`: stage-before-connect authoring、shape gate、local Cylinder ROI、public readback、safe teardown。
- `scripts/run_phase6du_static_cylinder_case.ps1`: 独立Kit process、production hash、crash upload無効化、dump保全、fatal fail-fast。
- `scripts/analyze_phase6du_static_cylinder.py`: Git外crash evidenceをsanitizeし、machine-readable safe-stop reportとSVGを生成。
- Phase 6DS probeのstage authoring helperは、`/phase6ds/output`が設定された従来runnerだけが自動起動するようguardを加えた。Phase 6DSの実行契約やproduction codeは変更していない。

## 次の再開条件

同じ`mesh_hull`条件を自動再実行しない。再開するなら、保全済みdumpとPhase 6DTの除外dumpを比較し、stage接続時のFabric／Hydra／RTX初期化raceか、stage内容依存かをproduction-neutralな別Phaseで分類する。設定適用時期やlauncherを変える実験も一度に一境界とし、正常なstatic Mesh preflightを得た後だけPhase 6DU matrixへ戻る。

Release buildは`6.78 s`で合格し、既存Flow scene collider契約のtargeted Kit testは`1 / 1`件、`0.093 s`で合格した。productionコードとapp compositionを変更していないため、Phase 0 RTXと標準suite全体は再実行していない。
