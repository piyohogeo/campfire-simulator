# Phase 6EP PointEmitter–CollisionProxy coexistence

## 目的と非変更範囲

Phase 6ENでqualifiedとなった静的な閉Mesh CollisionProxyと、既定OFFの単一Flow PointEmitterを共存させるためのproduction-neutral診断である。Point sourceが自分自身または別の薪のCollisionProxy内部へ入らず、上側の遮蔽物へ直接sourceを注入せず、fuel・temperature・smoke供給と可視炎を実用範囲で維持できる配置規則を選ぶ。production app、production既定値、wood authority、Resident snapshot/revision、Point sidecar schema、Flow publication、V3、CollisionProxy geometryは変更しない。

## 公開API監査と保守的support

Flow 110.0.0の`FlowEmitterPoint` Primについて、`radius`、`support`、`smooth`、`alloc`、`level`、`substep`を含む公開属性をruntimeで列挙した。`allocateMask`、`level`、`levelCount`、`numSubSteps`、`pointAllocateMasks`は取得できたが、各PointがFlow rasterizationへ影響する正確なsupport半径を表す公開属性は確認できなかった。別のPoint raster cell sizeも公開schemaでは確認できない。このため、公開APIで得た正確な値とは主張せず、実測velocity NanoVDBの1 voxel、すなわち`0.05 m`を各Pointの保守的な評価球半径に固定した。density cell `0.025 m`では2 cellに相当する。

各Pointは、Flowへ実際に渡す26頂点・36面・120 indexの閉Meshすべてに対してsigned distanceを計算する。中心だけでなく、`signed distance - 0.05 m`をsupport clearanceとして判定する。不適合点は配列から削除せず、position、owner順、surface identity、payload長、revisionを保持したままfuel・temperature・smokeを0にする。このdiagnostic revisionをwood/Resident authorityへ混入させない。

## 凍結contract

- schema: `campfire.phase6ep.point-collision-coexistence-contract.v1`
- SHA-256: `8DAD6E540EEFAA397FEEDE2313BFA531541AC976328924EA198BA2F4CD5B09C9`
- Point layout: Phase 6CBと同じ薪1本360点。owner log順、その中でsurface identity順
- source: active 1点あたりfuel `0.8`、temperature `2.0`、smoke `0.08`
- Flow: density cell `0.025 m`、velocity voxel `0.05 m`、frame 60/120/180/200
- offset sweep: `0 / 0.25 / 0.5 / 1.0 / 1.5` velocity voxel、すなわち`0 / 0.0125 / 0.025 / 0.05 / 0.075 m`
- candidate supply gate: 元payloadの`75%`以上
- Collision ON deep/center hard maximum: `1e-4 m/s`
- Collision OFF deep/center positive control: `0.1 m/s`以上
- deep ON/OFF ratio: `0.01`以下
- formal scenarios: 単一薪、近接2本、下側Point source＋上側遮蔽薪、productionに近い4本
- controls: Collision OFFはraw/unshifted、Collision ON filter/offset OFFもraw/unshifted、candidateだけfilter ON＋選択offset
- formal population: 6条件×3独立run=18 process

root 4まではpreflightであり正式母集団ではない。特にroot 4はfiltering-OFF controlへ0.075 m offsetを残していたため、active conditionの正常shutdownを待ってmatrix親を停止し、明示的にinvalidとした。修正contractはcontrolをoffset `0`へ固定し、新しいroot 5でsweepと正式母集団を最初から実行する。

## 実測結果

root 5のformal 18 processはすべてfunctional pass、`shutdown_complete`、normal OS exit、4 velocity sample、active blocks、revision 1、fatal/dump/upload/residual 0を満たした。正式母集団へ過去rootのsampleを再利用していない。

選択offsetは1.5 velocity voxel、`0.075 m`である。active supplyはsingle 360/360（100%）、near-two 582/720（80.83%）、lower/upper 360/360（100%）、production-four 1088/1440（75.56%）。active Pointの保守的support交差は全candidate・全runで0。production-fourは事前gate 75%に対する余裕が0.56 percentage pointしかないため、production採用余裕とは扱わない。

Collision ON candidateのdeep/center maximumは4 scenario・3 run・全sampleで`0 m/s`。raw/unshifted Collision OFF positive controlはdeep/center `7.9117117 m/s`、lower/upper candidateのdeep ratioは全runで0。active blocks最小はsingle 122、near-two 240、lower/upper 129、production-four 294。source channel合計はactive point数に正確に比例し、たとえばproduction-fourはfuel `870.400013`、temperature `2176`、smoke `87.039998`だった。

Point plan/filter処理のp95はsingle `145.72 ms`、near-two `157.81 ms`、lower/upper `112.31 ms`、production-four `297.32 ms`。Point配列のUSD publication p95は同順に`5.60 / 5.61 / 4.00 / 12.07 ms`。これはoffline diagnostic stage構築時の一回測定であり、production frame costではない。formal resource peakはrunner 96,628,736 bytes、diagnostic 27,447,296 bytes、Kit 13,090,537,472 bytes、unique tree 13,237,260,288 bytesで設定上限内だった。continuous GPU telemetryは、既存の隔離inventory境界を維持するため正式母集団では未取得である。

## 映像/lifecycle safe stop

数値合格後の映像processはformal populationから分離した。Collision OFFは180 frameを取得してnormal OS exitした。2本目のCollision ON・filter/offset OFFは180 frame、4 NanoVDB sample、`shutdown_complete`まで完了したが、Kitが60秒grace内にOS終了しなかった。軽量診断はKit logの排他lockを記録してCDBへ進んだものの、CDBは45秒timeoutしdetach markerがなく、既知NGX 5-token signatureも一致しなかった。このため`unknown_shutdown_failure`としてfail closedにした。guardは観測済みKit/conhost/telemetry PIDをexact identityでcleanupし残留0、fatal/dump/automatic upload/device lost/TDR 0、production SHA不変だった。

同じ条件を自動retryせず、3本目のcandidate映像、encode、実再生確認、日誌video modalへの追加は行っていない。したがってformal numeric sub-gateは18/18合格だが、Phase 6EP全体は映像/lifecycle未完了のsafe stopであり、production候補の採用判断へ進まない。既存latest demo pointerも変更しない。Phase 0/3など後続Kit回帰は、このunknown shutdown後に新しいKit条件を開始しない安全規則を優先して保留する。

## 回帰と公開検査

Release buildは8.20秒で合格した。Phase 6EA～6EPのfocused contractは130/130、標準suiteは8 process・78/78を357.2秒で合格した。日誌の静的検査はローカル参照384、JSON 196、SVG 162、ZIP 2を検査し、欠落、解析失敗、UTF-8 replacement character、duplicate IDは0だった。production app SHA-256はbuild前後とも`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`である。

Phase 0 RTXとPhase 3の専用probeは未実施である。Phase 6EP matrixでは未知終了条件をretryせず、candidate映像も開始していない。exact-identity cleanupと残留0を確認した後、必須の標準suiteだけは独立した既知baselineとして実行した。Phase 6EP映像の再開には同条件の終了診断または再実行に対する明示承認と、新しいvisual artifact rootが必要になる。

## 適用限界

これは既定OFFの隔離PointEmitterに対する固定姿勢・固定配置の数値結果である。Flow内部の正確なPoint support maskを取得したものではない。visual lift、炎の横方向偏り、上側遮蔽の人間による比較は未qualifiedである。dynamic transform、20本性能、RenderSurface/PhysX共用、production Point publication、Point sidecar schema変更、Sphere既定の置換も未qualifiedであり、このPhaseでは進めない。再開する場合は、unknown visual shutdownの診断または同条件を再実行する明示承認と、新しいvisual artifact rootが必要である。
