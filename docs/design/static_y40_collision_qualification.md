# Phase 6EF: static Y40 Mesh CollisionProxy qualification

## 事前固定した判定契約

Phase 6EFは、Phase 6ECの不合格記録を変更せず、Phase 6EEで判明したROI誤差を除いた判定方法だけを正式化するproduction-neutralなqualificationである。Flowへ実際に渡す26頂点・36面・120 indexの閉じた低詳細Meshを内外判定と符号付き距離の主基準とし、理想Cylinderは副指標に限定する。Flow 110.0.0の公開`IFlowUsd`から内部collision occupancy maskは取得できないため、本Phaseの幾何ラベルをFlow内部maskとは呼ばない。

velocity NanoVDB固有の0.05 m voxelを使い、実Mesh内側0～1 voxelをboundary band、1 voxelより深い領域をdeep interiorとする。boundary bandは完全ゼロgateから除外するが、voxel数、mean、p50、p95、maximum、`1e-12`／`1e-6`／`1e-5`／`0.1 m/s`超過数を全run・全frameで報告する。中心軸近傍はdeep interiorかつ半径0.5 velocity voxel以内として独立判定する。

正式runを見る前に、machine-readable contract `scripts/phase6ef_static_y40_qualification_contract.json`へ次を固定した。

- A axis ONとB Y40 ONのdeep interior・中心軸maximumは、全run・frameで既存閾値`1e-5 m/s`以下。
- C Y40 OFFの同領域maximumは、全run・frameで`0.1 m/s`以上。
- B/Cのdeep maximum比は全対応sampleで`0.01`以下。
- stale-transform判定では、Cのaxis-only maximumが`0.1 m/s`以上で比較可能であること、およびB/C axis-only比が`0.1`以上であることを要求する。場が届かず比較不能なら合格にしない。
- active blockは正、source fuelは`0.8 ± 1e-6`、条件差は予定したtransformとcollision switchだけ、lifecycleはfunctional passかつ`normal_exit`のみとする。fatal、dump、upload、residualは0を要求する。

実行順はrun 1 `A→B→C`、run 2 `B→C→A`、run 3 `C→A→B`に固定し、9 processすべてのframe 60/120/180/200で合格を要求する。正式run後に閾値を変更しない。

## 非変更範囲

production app、Flow既定、V3、Resident session、wood authority、Emitter schema、CollisionProxy geometry、Flow解像度は変更しない。Phase 6ECの旧ROI gateと不合格履歴も変更・再解釈しない。合格しても対象は固定環境の静的Y40°だけであり、任意軸回転、dynamic transform、RenderSurface、PhysX共用、20本production性能は未qualifiedのままとする。

## 実測結果

正式順序を変えた3 run・9 processはすべてfunctional pass、`normal_exit`、exit 0で終了し、fatal、dump、automatic upload attempt、residualは0だった。36個のvelocity sampleはすべて事前gateに合格した。active block finalはA/B/Cで各runとも26/24/58、source fuelは全条件`0.8000000119`である。

全run・frameにおける最悪値は、A deep/center `0 / 0 m/s`、B deep/center `8.352523e-6 / 8.352523e-6 m/s`だった。C positive controlの最小deep/centerはともに`7.767152 m/s`で、B/C deep maximum比の最悪値は`1.075365e-6`だった。C axis-onlyの最小maximumは`0.650298 m/s`、B/C axis-only比の最小値は`4.03873`であり、回転前位置が同様に遮蔽されたstale-transform像とは整合しない。

boundary bandはgateから隠していない。全sample中の最大p95／maximumはA `0.014721 / 2.831104 m/s`、B `0.104128 / 3.162397 m/s`、C `1.726794 / 9.406457 m/s`だった。したがって「Collider内部が数学的に完全ゼロ」または「Flow内部maskが判明した」とは結論しない。固定環境では、意味のある残留が実Mesh表面1 velocity voxel以内に限定され、deep interiorと中心軸が既存閾値以下であることをqualification根拠とする。

診断保存はvelocityのみ36 NPZ、合計`4,236,585 bytes`、stream-built archive `4,243,855 bytes`（SHA-256 `C4F55372...A07B9A0C`）だった。Kit内collectorの最大RSS増分は`703,864,832 bytes`であり、PowerShellへ配列を返していない。production app SHA-256は前後とも`94162F82...F02A`で一致した。

## 判断

`Flow 110.0.0、現行固定解像度、26頂点閉Mesh、static Y40°`をqualifiedとする。Phase 6ECの旧gateと不合格履歴は変更しない。次は任意軸の静的回転を一変数で検証できるが、dynamic transform、RenderSurface、PhysX共用、20本production性能はまだ進めない。

Release buildは5.97秒、Phase 0 RTXはexit 0。Phase 3はdry/wet mass-balance error 0、authority SHA-256 `0dec57f3...e84be10`／`148585f8...d2b20c9`、Flow active blocks final/peak 281/312、peak fuel 1.0だった。Phase 6EC～6EFとPhase 6EA/6EB/6EDのtargeted契約は67/67、標準suiteは8 process・78/78件・303.2秒（collapse 176.8秒）で合格した。Kit/CDB残留、Phase 6EF fatal、dump、automatic upload attemptは0である。日誌の実レンダリング確認は接続可能なBrowserがないため実施できず、local reference、JSON、SVG、ZIP CRC、UTF-8、duplicate IDの静的検査で代替した。
