# Phase 6EQ PointEmitter self-Collider tolerance

## 目的と非変更境界

Phase 6EPの正式18 processとmedia/lifecycle safe stopをread-onlyの既存証拠として保持し、PointEmitterの評価球が自分のCollisionProxyへ重なる場合と、他の薪へ重なる場合を分離する既定OFF probeを追加した。production app、Point配列の順序・長さ・revision、layout、wood authority、Flow設定、26頂点・36面CollisionProxy、Sphere既定は変更しない。Phase 6EP成果物の再分類、上書き、sample再利用、無断再実行も行わない。

公開Flow 110.0.0 APIからPoint Emitterの正確なsupport mask/radiusは取得できない。したがってPhase 6EPと同じvelocity voxel 1個、半径`0.05 m`の球をengineering evaluation supportとして使う。これはFlow内部実装の主張ではない。距離は実際にauthorする閉Meshへ測り、各Pointにself/other signed distance、center-inside、support intersection、disable理由、元と有効化後のfuel/temperature/smokeを保存する。

## 事前凍結contract

`campfire.phase6eq.self-collider-tolerance-contract.v1`、SHA-256 `B9D3169C54ADA5EEB62B712E02C00438C4FBFCE9914CCABE0EFE2FADEC0E1DAF`をruntime前に固定した。

- `strict_all`: self/other support intersectionを禁止。代表offset `+0.075 m`。
- `allow_self_support`: self support intersectionは許すがself center-insideは禁止。other support intersectionは禁止。代表offset `+0.025 m`。
- `allow_self_center`: self center-insideも許す。other support intersectionは禁止。代表offset `-0.0125 m`。
- `collision_off`: filter/collisionを無効にした正例。offset `0 m`。
- sweep: `-0.0125, 0, 0.0125, 0.025, 0.05, 0.075 m`。
- formal: lower/upperとproduction-four、4 policy、3 run、計24 process。frame `30/60/90/120/150/180/200`。
- active other support intersectionは0、weighted supply retentionは診断用下限50%。旧Phase 6EPの75%をproduction採用gateへ昇格しない。
- other-Collider deep maximumはvelocity `1e-4 m/s`、temperature `1e-4`、smoke `1e-5`。Collision OFF velocity正例は`0.1 m/s`以上、ON/OFF比は1%以下。
- normal OS exit、fatal/dump/upload/residual 0を各processで要求し、不合格時はretryも後続開始もしない。

## offset sweepとPoint分類

18/18のlower/upper runtime sweepはnormal exitした。strictは`+0.075 m`で、self-support許容は`+0.025 m`で、self-center許容は`-0.0125 m`でそれぞれPointとfuel/temperature/smokeを100%保持し、active other support intersectionは0だった。内側offsetでもself-center許容なら外部Flow場とactive blockが成立することは観測したが、formal遮蔽品質まではこのsweepだけで判断しない。

production-fourのoffline実Mesh分類では、事前選択した代表offsetの結果は次のとおりだった。

| rule | offset | active points | weighted fuel/temp/smoke | disabled by other support |
| --- | ---: | ---: | ---: | ---: |
| strict all | +0.075 m | 1088 / 1440 | 75.56% | 352 |
| allow self support | +0.025 m | 804 / 1440 | 55.83% | 636 |
| allow self center | -0.0125 m | 932 / 1440 | 64.72% | 508 |

同じ低offsetではself許容によりstrictの0%から供給可能になる一方、選択済みの外向きstrict `+0.075 m`を超える保持率にはならなかった。自己Collider規則ではなく、他薪とのsupport intersectionがproduction-fourの支配的な無効化理由である。全候補で有効Pointのother support intersectionは0である。

## formal safe stop

formalの最初のCollision OFF controlは合格した。続く`run 1 / lower_upper / strict_all`はPoint/weighted supply 100%、active other support intersection 0、active blocks 129、external ignition frame 30、velocity deep maximum 0、functional pass、`shutdown_complete`、normal OS exitだった。しかしother-Collider deep temperature最大`1.0`、smoke最大`1.4052734375`が凍結済みhard gateを超えたため安全停止した。OFF controlはdeep velocity `7.9117117 m/s`、temperature `1.0`、smoke `1.4892578125`だった。

完了したCollision ONではvelocityは全7 frameでdeep 0だが、temperatureとsmokeは全frameでdeepに残った。これは「速度遮蔽が成立した」事実と「scalarが他薪深部でhard-zeroではない」事実を分ける必要があることを示す。Flow内部occupancyやscalar transportの機構は公開証拠なしに断定しない。temperatureの基準値・scalarの拡散/取込み・ROI解釈のどれが支配的かも未確定であり、結果後にこのcontractを緩和しない。

formal完了は2/24、正式母集団の受理は0/24である。同条件のretry、残る22条件、visual population、encode、再生確認を開始していない。したがって自己Collider許容規則、offset、見た目の浮き、反対側からの炎、3-run再現性にproduction推奨は出さない。比較動画も存在せず、latest-demo pointerは不変である。

## lifecycle・resource・次の境界

実行済み20 processはすべてguard status `ok`、cleanup残留0。失敗conditionもnormal OS exitし、runner/diagnostic/Kit/tree peakは96.1 MB/16.8 MB/13.13 GB/13.27 GB、available physical/commit headroom最小は85.64/104.26 GB。fatal、dump、automatic upload、device lost、TDRは0だった。production app SHA-256は`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`で、Phase 6EP public report SHA-256も`104F4E1921408CCBE6E6BBC2C5AE01C7FD9ADF99F44AB395E0C696ED9876DA06`のまま変わらない。

次に必要なのは、velocity occlusionとは別に、temperature/smokeのcontrol-relativeかつ空間分解した基準を事前定義する独立Phaseである。ambient/reference値、実Mesh deep分布、反対側far ROI、時間積分供給を区別し、その新contractが承認されるまではPhase 6EQを再開しない。self-overlap許容をproductionへ統合せず、Point schema、production defaults、Flow、CollisionProxyを変更しない。

回帰はRelease build 8.92秒、Phase 6EA/6EB/6EL/6EP/6EQ focused contracts 72/72、標準8 process 78/78（346.2秒）が合格した。日誌静的検査は387参照、245 ID、197 JSON、163 SVG、2 ZIPで欠落・解析失敗・duplicate IDなし。ブラウザ実レンダリング確認はこのセッションに接続可能なbrowserが0件だったため未実施で、静的検査を代替証拠とする。
