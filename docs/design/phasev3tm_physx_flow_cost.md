# Phase V3T-M: PhysX / Flow cost decomposition safe stop

## 結論

Phase V3T-Mは完成ではなく、`partial_safe_stop_not_complete`で停止する。Candidate Performance下のPhysX比較、Flowなし比較、AutoBaseline代表比較は正式母集団として成立した。一方、Flow schemaを含むstageの接続は、構成やrunによって非決定的にnative crashしたため、Simulate、Offscreen、Render、shadow raymarch、active block、volumeの個別コストを正式値として確定していない。

production code、production既定値、wood authority、Flow入力、Emitter、collision、rigid layout、checkpoint、serialization、V3既定OFFは変更していない。

## 測定契約

- Kit 110.2、Flow 110.0.0、RTX 3090、1280×720、RTX Real-Time 2.0。
- 主基準はDLSS Performance、`/rtx/post/aa/op=3`、`/rtx/post/dlss/execMode=0`、`/rtx/rtpt/maxBounces=2`。AOは変更していない。
- 比較用AutoBaselineは`execMode=3`、4 bounce。
- Power Limitは変更せず、実効値210 Wを各runでgateした。
- 既存visible viewportの`ViewportAPI.frame_info`だけを使用し、追加RenderProduct、HydraTexture、capture、encodeを作っていない。
- visible FPSはframe-number差÷wall time、HUD FPSは平滑化値として別記録した。display-present FPS、raw frame p95/p99は取得しておらず、推定していない。
- stageは接続前に完成させ、測定中のPrim生成・削除、material rebind、asset path変更は行っていない。
- 各隔離KitはCrash Reporter uploadを無効化し、`preserveDump=true`、run固有dump directoryを使用した。

## 正式母集団

正常終了だけを含む正式母集団は33 processである。

| 条件 | run | mean visible FPS | mean frame time | 観測 |
|---|---:|---:|---:|---|
| timeline STOP、PhysXなし | 3 | 116.390 | 8.592 ms | present/update同期なしの上限側 |
| timeline PLAY、PhysXなし | 3 | 59.973 | 16.674 ms | 再生だけで約60 FPS境界 |
| PhysX sceneのみ | 3 | 59.974 | 16.674 ms | PLAY基準との差を分離できず |
| kinematic rigid 20本 | 3 | 59.980 | 16.671 ms | transform変化0 |
| sleep候補 rigid 20本 | 3 | 59.977 | 16.672 ms | transform変化0 |
| collisionなしmoving 20本 | 3 | 59.940 | 16.683 ms | 20/20 transform変化 |
| collisionありmoving 20本 | 3 | 59.987 | 16.670 ms | 4 transform変化 |
| collapse 20本 | 3 | 59.998 | 16.667 ms | 10 transform変化 |
| Flow Primなし | 3 | 59.960 | 16.678 ms | Performance |
| 空の`/World/Flow` Xform | 3 | 59.977 | 16.673 ms | Flow schema Primではない |
| Flow Primなし | 3 | 46.933 | 21.308 ms | AutoBaseline代表 |

約60 FPSに張り付く条件間の小差から「PhysXコストは0」とは結論しない。visible counterとrate/present境界の分解能内で追加低下を検出できなかった、という限定的な観測である。PerformanceとAutoBaselineの差は同じFlowなしsceneでも約13.0 FPSあり、DLSS/presetによる見かけ上の改善を実処理削減と混同できない。

contact callbackは診断stageで0 pointだった。moving/collapseのtransform変化は確認したが、collision correctnessの合格根拠にはせず、既存Phase 2回帰を使用する。

## native crashとfail-fast

Phase V3T-Mに関連して保全した8個のdumpはすべて次の署名だった。

- exception `0xC0000005`
- read target `0x20`
- `omni.fabric.plugin.dll+0xD6960`
- durable lifecycle markerの最終位置は`stage_connection_begin`
- upload試行0、空Crash Reporter URLによる送信skip

今回新たに再現した条件には、全Flow subtree inactive、全active＋Emitter OFF、active-block-only、Offscreen-only、full Flow volumeが含まれる。full Flow volumeは単独probeでは正常終了した後、formal runで同じ署名により落ちた。したがって単発の正常終了を安全性の証明にできない。

当初probeに残っていたFlow processでの`/physics/fabricEnabled=false` live変更は除去し、PhysX専用設定をPhysX processの起動引数へ移した。これによりfull volume単独probeは一度正常化したが、後のformal runで再発したため、設定順序だけが唯一の原因とは断定しない。観測上はFabric/Hydraのstage接続・renderer初期化raceが強い候補だが、private symbolによる正規unwindがなく未確認である。

dump、Kit log、解析raw JSONは機密情報を含む可能性があるGit管理外artifactである。管理対象には保存先、サイズ、SHA-256、例外、module＋offsetだけを残す。

## 判断

- Candidate Performanceは暫定標準のまま維持する。
- V3T-Mは完成扱いにしない。
- Flow partial topologyとV3T-M独自のFlow volume再測定を保留し、自動再実行しない。
- Phase V3T-Lの正常なproduction相当Flow＋volume 3 run（47.858 FPS / 20.90 ms）と、Phase V3T-MBの実燃焼回帰は有効な既存基準として維持する。
- Flow component分解を再開する条件は、固定Flow/Kitでstage接続raceを回避できる公開された初期化契約、matching symbolを用いた原因特定、または隔離した新Flow版での再現性改善である。
- production対策を推測で入れず、Flow stageの起動順序やroot-layer settingsをlive変更しない。

## 最終回帰

- Release build: 合格、8.38秒。
- Phase 0 RTX: exit 0。
- Phase 2 collision: 合格。
- 標準suite: 8/8 process、77/77 test、355.6秒。
- Candidate Performance V3実燃焼: status ok、dry/wet authority SHA-256保存、両mass-balance error 0、Resident revision 1200整合、Flow active block final/peak `231 / 303`、V3 processed revision 1200、failure 0。
- shutdown: current V3 runは正常終了しnative backendはinactiveへcloseした。production teardownを変更していないため、Phase V3T-Jのordered teardown 24/24を既存shutdown log gateとして維持した。

機械可読値は`docs/devlog/assets/phasev3tm/physx_flow_cost_report.json`、全正式sampleは`physx_flow_cost_samples.json`に保存する。raw dumpは含まれない。
