# Phase 6DV — stage-open crash classification

## 結論

Phase 6DUの円筒Mesh条件は再実行していない。保存済みのPhase 6DT除外dumpとPhase 6DU dumpは、どちらもWindows `0xC0000005`、`omni.fabric.plugin.dll+0xD6960`でアドレス`0x20`を読む違反だった。低信頼backtraceの先頭もFabric scene delegate、UsdRT delegate、RTX Hydraまで一致する。このため、円筒topology単独の故障と分類する根拠はない。

一方、Phase 6DTで正常だったBox Mesh stageをPhase 6DUと同じisolated app、launcher設定、renderer起動順でOpenUSDだけに読み込むcontrolは、stage監査とprobe上の`shutdown_complete`に到達したものの、renderer plugin shutdown後もKit processが7分以上終了しなかった。既知正常条件が正常なOS exitを満たさなかったため、Hydra接続、stage差分ablation、円筒Flow readbackへは進まず安全停止した。Phase 6DUは再開不可である。

## 保存dumpの比較

dump本体、Crash Reporter metadata、Kit logは`artifacts/`に保持し、Gitへ追加しない。自動uploadは無効のままで、Phase 6DVから新しいdumpもupload試行も発生していない。

| 項目 | Phase 6DT除外run | Phase 6DU失敗run |
|---|---|---|
| Windows exception | `0xC0000005` | `0xC0000005` |
| access | read `0x20` | read `0x20` |
| instruction | `omni.fabric.plugin.dll+0xD6960` | `omni.fabric.plugin.dll+0xD6960` |
| durable marker | `opening_prebuilt_stage` | `opening_prebuilt_stage` |
| Kit / Flow | 110.2 / 110.0.0 | 110.2 / 110.0.0 |
| driver / GPU | 591.86 / RTX 3090 | 591.86 / RTX 3090 |
| dump SHA-256 | `645006F8...23D51B4` | `BA2043E0...FEB6734` |

WinDbg、CDB、matching private symbolはローカル環境に存在しなかった。代わりに公開MINIDUMP形式のExceptionStreamとModuleListStreamをread-onlyで解析した。例外thread ID、命令アドレス、module base、access種別は取得できたが、native localsと正確な関数stackは未確認である。Crash Reporter logの`omni.fabric.plugin.dll+0xCE5B0`は低信頼symbol labelであり、fault位置にはExceptionStreamの`+0xD6960`を使う。

## lifecycle分類

新しいprobeはstage接続前に次をdurable JSONへ逐次保存する。

1. renderer readiness開始／完了
2. offline stage準備
3. pure `Usd.Stage.Open`開始／完了
4. USD context `open_stage_async`進入／復帰
5. stage event、stage cache query
6. viewport接続
7. 最初のrenderer update開始／完了
8. 最初のviewport frame開始／完了
9. stage close、shutdown

今回の正式な停止点は3までである。最初のcold controlは外側の330秒上限と競合してrunner evidenceが欠けたため除外した。待機上限を延ばしたcontrolと、8 viewport frameのrenderer readinessを先に完了させたcontrolは、いずれもpure OpenUSD監査と全plugin shutdownに到達したが、OS processは終了せず手動で隔離終了した。fatal token、dump、uploadは0、production app hashは前後一致だった。この残留はstage parse failureではないが、同じlauncherの正常性を満たさない。

## 正規化したstage差分

| 境界 | Phase 6DT known-good | Phase 6DU failed | 状態 |
|---|---|---|---|
| shape | Box、8頂点、6 face | 閉じた12分割Cylinder、26頂点、36 face | 未分離 |
| extent | world座標、`Z=0.875..1.125` | local座標、`Z=-0.16..0.16` | offline妥当 |
| hierarchy | root直下Mesh | `/World/Log`配下proxy | 未分離 |
| collision API | Collision + MeshCollision | Collision + MeshCollision | 同じ |
| approximation | `convexDecomposition` | `convexHull` | 未分離 |
| render/material | 不可視proxy、元Cubeはcollision無効 | 不可視proxy＋可視RenderSurface | 未分離 |
| analytic sibling | collision無効Cube | collision APIなしCylinder | 重複collisionなし、runtime未分離 |
| visibility / purpose | invisible / default | invisible / default | 同等 |
| authoring | Phase 6DSをflattenしてoffline patch | fresh stageをoffline構築 | どちらも接続前に完了 |

Boxを起点に、`box_hull`、`cylinder_decomposition`、`cylinder_hull`、hierarchy、RenderSurface、analytic siblingを一項目ずつ加える再現可能なrunnerは用意した。ただし既知正常controlが正常exitしなかったため、これらを実行していない。失敗済みのPhase 6DU `mesh_hull`条件も再実行していない。

## 原因分類

観測事実：

- 2件のnative crash signatureはmodule offset、access kind、target addressまで一致する。
- 2件は構造の異なるBoxとCylinder stageで、どちらもUSD contextがHydra engineを追加する境界にいた。
- Phase 6DTの完全なMesh schema Boxは過去3 runでFlow readbackと正常shutdownに成功している。
- 同じBoxは新しいsame-launcher controlでpure OpenUSDには読み込めた。
- same-launcher controlはstage接続前にもかかわらず、cold renderer shutdown後の正常OS exitを得られなかった。

強い推定：

- 現在の証拠は、円筒topology欠陥よりFabric/Hydra engine追加またはrenderer初期化・寿命境界を示す。
- 新しいprocess残留はOpenUSD stage破損ではなく、cold renderer/harness終了境界である。

未確認：

- `+0xD6960`内部の関数、native object、所有関係。
- topology、`convexHull`、transform階層、RenderSurface、analytic siblingの最初のdiscriminator。
- renderer readiness、USD context scheduling、teardown、固定build上のFabric raceのどれが根本原因か。
- 円筒Flow遮蔽、rotation、PhysX共有、dynamic transform、20本cost。

## Phase 6DU再開条件

現時点では再開しない。次の順で条件を満たす必要がある。

1. 同じlauncherでknown-good BoxがHydra接続、最初のrenderer frame、stage close、正常OS exitまで一貫して通る。
2. 可能ならKit build `698af100`に対応するWinDbg/CDB symbol、または2件のdump hashとmodule offsetを添えたNVIDIA側解析を得る。
3. control合格後に限り、Box `convexHull`、Cylinder `convexDecomposition`、Cylinder `convexHull`、hierarchy、RenderSurface、analytic siblingを別processで順に実行する。
4. stage-openが安定してから、static、axis-aligned、Flow-only、単一proxy、analytic重複なしの1条件だけでtimelineとpublic readbackへ進む。

長期設計はPhase 6DUの方針を維持する。RenderSurfaceは高詳細表示、CollisionProxyは閉じた低詳細凸Meshまたは少数凸分割とし、条件が成立した場合にのみPhysXとFlowで共有する。解析的Cylinderを恒久要件にはせず、比較、回帰、fallbackとして扱う。今回production colliderは変更していない。

## 成果物

- `scripts/analyze_phase6dv_stage_open_crashes.py`
- `scripts/probe_phase6dv_stage_open_boundary.py`
- `scripts/run_phase6dv_stage_open_case.ps1`
- `scripts/analyze_phase6dv_stage_open_boundary.py`
- `docs/devlog/assets/phase6/stage_open_crash_classification_report.json`
- `docs/devlog/assets/phase6/stage_open_crash_classification_report.svg`

production code、production `.kit`、Flow 110.0.0、V3既定、Resident session、wood authority、Emitter、collision契約は変更していない。有効な映像差がないため新動画を作らず、latest demo pointerも変更しない。

Release buildは`6.01 s`で合格した。Flow scene collider契約のtargeted Kit testは`1 / 1`件、test time `0.073 s`で合格した。UTF-8 HTML、Phase順序、asset参照、JSON、SVG XMLの静的日誌検査も合格した。接続可能なbrowser bindingがなかったため実ブラウザ描画だけは未確認である。共有productionコードとapp compositionを変更していないため、Phase 0 RTXと標準suite全体は再実行していない。
