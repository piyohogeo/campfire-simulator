# Phase 6EC: static rotated Cylinder Flow collision

## 目的と単一変数

Phase 6DYで合格した低詳細・閉じたCylinder Mesh CollisionProxyを既知正常stageとし、静的な回転だけを加えたときにFlow collisionの遮蔽位置がworld transformへ追従するかを確認する。Production統合、RenderSurface、PhysX共用、dynamic transform、20本性能は対象外である。

基準stageはSHA-256 `BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9`である。26頂点・36面・120 index、local geometry SHA-256 `662163A7...76FF0`、`PhysicsCollisionAPI`＋`PhysicsMeshCollisionAPI`、`convexDecomposition`を固定する。正式順序はA axis-aligned collision ON、B Y 40° collision ON、C同じY 40° collision OFFで、各条件を別processにする。

40°は約45°の判定しやすさを保ちつつ、既存Emitterと回転後proxyの表面間隔を`0.111532 m`、実測velocity cell `0.05 m`の`2.2306 cell`に保つため選んだ。45°では2 cellを下回るため採用しない。回転は中心`(0, 0, 1.035) m`を保存する単一`xformOp:transform`で、right-handed、unit scaleである。

## 実装境界

`prepare_phase6ec_static_rotated_cylinder.py`はaxis controlをバイト同一copyし、回転stageには中心保存Y40 transformだけを追加する。Formal stageはRenderSurface、RigidBody、analytic colliderの有効化を含まない。可視位置合わせ用stageは同じproxyへ既存materialをbindするが、数値gateから除外する。

`probe_phase6dt_flow_collision_reference.py`にはPhase 6EC modeを追加し、既存のpublic NanoVDB readbackを使用する。ROIはworld pointをcollision proxyの逆world transformへ戻してCylinder local volumeを判定する。さらに、回転後volumeだけに含まれる`rotated_only`、元のaxis volumeだけに含まれる`axis_only`、重なりを別集計し、遮蔽が古い座標へ残る場合を区別する。Private APIは使わない。

RunnerはPhase 6EB policyを変更せず使用する。Unknown shutdown、dump、fatal、upload、device lost、TDR、PID identity不一致で即時停止し、同じ条件を自動再実行しない。既知NGX residualが2回連続した場合も再調査triggerとして停止する。`normal_exit`だけを性能sampleとして受理する。

## 2026-08-11 safe stop

Offline準備は14/14 gateに合格した。Y40 stageのSHA-256は`CE66FF32158BE1513748CB653217A66727D9867DB0BDE715C28BBF587E7359CB`、world extentは`[-0.792286, -0.16, 0.333924]`〜`[0.792286, 0.16, 1.736076] m`である。Emitterはproxy外部にあり、表面間隔は`0.111532 m`だった。

最初のAはpublic probeとしては完了した。`status=ok`、最終marker `shutdown_complete`、active blocks 26、Emitter fuel `0.800000012`、OS exit code 0、residual processなし、fatal/dump/upload 0だった。local Cylinder coreの4 sample最大はtemperature `0.563477`、fuel `0`、burn `0.0173950`、smoke `0.533691`、velocity `0 m/s`である。Scalarは拡散・燃焼場なのでゼロを一律gateにせず、将来のB/Cでは同一回転のOFF比を用いる。Velocity coreはゼロだった。

しかしPhase 6EB classifier入力の`windows_exception_present`がtrueとなり、結果は`functional_status=fail`、`lifecycle_status=unknown_shutdown_failure`、理由`safety:no_windows_exception`となった。該当logを逐次照合すると、唯一のmatchはGPU inventoryの次の行だった。

```text
Sub System Id : 0xC75C1462
```

これは観測上PCI subsystem identifierであり、exception codeのlogではない。一方、Phase 6EBの現在の一般的な`0xC[0-9A-F]{7}`検出に一致する。Phase 6ECはPhase 6EA／6EB安全化コードと分類規則を変更しない境界なので、このrunをnormalへ読み替えずunknownのまま安全停止した。Aの再実行、B/C、映像processは開始していない。

## 判定と再開条件

現時点では静的回転collisionは未評価であり、合格とも不成立とも言えない。準備stage、transform、Emitter clearanceは合格したが、Flow readback比較はAだけである。Phase 6DRの貫通疑惑に対する説明もPhase 6DYまでの「軸平行Mesh proxyなら遮蔽する」から更新しない。

Phase 6EDでPhase 6EBのWindows exception evidenceを明示的exception文脈と16進hardware IDに分離し、上記`Sub System Id`行を含むnegative fixtureと実例外positive fixtureは31/31で合格した。保存Aのread-only offline再分類もnormal exitになった。ただしPhase 6ECはまだ再実行していない。次は新artifact rootでAから開始し、現在artifactのAは回転比較の正式母集団へ再利用しない。

最初の再開root 2ではAの4 sampleと`shutdown_complete`まで到達したが、inline case-runner PowerShellが7 GiB超へ増加したためB/C前に安全停止した。これはFlow遮蔽の合否ではない。root 2は再利用せず、各case runnerをPhase 6EA guarded helperの別process、直接stdout/stderr、720秒、512 MiBへ隔離してから、さらに新しいrootでAから開始する。Phase 6ED exception policyは変更していない。

今回、production app、Flow既定、V3、Resident session、wood authority、Emitter schemaは変更していない。Production app SHA-256は前後とも`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`である。画面上の合格結果がないため動画とlatest demo pointerは変更しない。

回帰はPhase 6EC contract 7/7、Phase 6EA resource safety 7/7（10.5秒、128 MiB sparse hash peak private bytes 75,849,728）、Phase 6EA静的契約6/6、Phase 6EB契約24/24、Release build 6.94秒、標準suite 8 process・78/78件・303.1秒に合格した。Phase 0は17.4秒で合格しRTX readyは14.176秒。Phase 3はdry/wet mass balance error 0、authority SHA-256 `0dec57...be10`／`148585...20c9`、Flow active blocks final 252／peak 405、peak fuel input 1.0だった。日誌静的検査は341 local reference、JSON 181、SVG 147、欠落・parse failure・replacement character・duplicate ID 0。接続可能なBrowser instanceがなかったため実レンダリング確認はできず、静的検査で代替した。全run後のKit/CDB残留は0だった。
