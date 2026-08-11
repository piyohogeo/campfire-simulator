# Phase 6EE: rotated CollisionProxy velocity distribution

## Scope

Phase 6ECでY40° Collision ONの従来core ROIに残った最大速度約0.719 m/sを、productionへ接続せず空間分布として切り分ける。Phase 6DYの合格済み26頂点・36面・120 indexの閉じた低詳細Mesh、Phase 6ECのstage、Emitter、frame 60/120/180/200、Flow設定を変更せず、A axis ON、B Y40 ON、C Y40 OFFを各別processで測定する。Phase 6ECの`1e-5 m/s` gateは変更せず、本Phaseだけで回転collisionをqualifiedにしない。

共有したのは既存の`run_phase6dt_flow_collision_case.ps1`、Phase 6EA guarded helper、Phase 6EB/6ED shutdown classifierである。新しいlifecycle処理は作らず、case runnerの任意診断flagがONの場合だけ、既存の公開`get_latest_nanovdb_readback()`からCollider近傍をNPZへ保存する。production app、Flow既定値、V3、Resident、wood authority、Emitter schemaは変更しない。

## Public API boundary

固定Flow 110.0.0の実行時`IFlowUsd`で公開される19 memberを列挙した。`get_latest_nanovdb_readback`、`buffer_to_volume`、位置sample、RGBA変換、active-block取得等はあるが、Flow自身がcollisionとして占有したvoxel maskを返す公開memberはない。ローカルSDK／stub検索にもcollision mask／occupancy readbackは見つからなかった。

したがって本報告の`mesh_inside`、距離、深さ、face classは、実際にFlowへ渡した閉じた低ポリMeshからこちらで計算した**幾何学的ラベル**であり、Flow内部occupancy maskではない。private APIは使用していない。理想的な真円Cylinder SDFは副指標だけに使い、主判定はtriangulateした実Meshへの最短距離と、外向きface planeによるconvex内外判定を使う。

## Data contract

各native NanoVDB gridはそれぞれのmapとvoxel sizeを保持し、同一topologyとは仮定しない。Colliderと外側3 cell haloだけを抽出し、condition/frame/channelごとの圧縮NPZへ次を保存した。

- integer index、world/local座標
- velocity XYZと大きさ、またはscalar値
- 実Meshの内外、符号付き最短距離、voxel単位距離、最寄りface class
- 解析的Cylinder SDFと分類不一致
- 同じ格子で最寄り外側cellまでのEuclidean距離と6近傍step深さ
- 元のaxis-aligned Mesh位置に対する副ラベル
- condition、frame、channel固有voxel size

Temperature、fuel、burn、smoke、velocityに加え、公開readbackに存在したdivergenceも保存した。A/B/C各24 NPZ、計72 NPZは17,373,364 bytesのstream-built ZIPに格納し、SHA-256は`7E198D02...5A369458`。PowerShellへ配列を返さず、Kit process RSSのcapture開始比peak増加はA 476,114,944、B 810,377,216、C 907,304,960 bytesだった。全Flow domainをJSONへ展開していない。

## Observations

Velocity cell sizeは0.05 m。4 sampleを合算した実Mesh深さ帯の結果は次のとおり。

| Condition / band | voxel records | mean m/s | p95 m/s | max m/s | `>1e-5` |
|---|---:|---:|---:|---:|---:|
| A axis ON, 0–0.5 cell | 1540 | 0.0496323 | 0.113185 | 2.83110 | 512 |
| A axis ON, 0.5–1 cell | 1092 | 0.00081649 | 0.00475114 | 0.118177 | 128 |
| A axis ON, 1–2 cells | 1352 | 0 | 0 | 0 | 0 |
| A axis ON, 2+ cells | 496 | 0 | 0 | 0 | 0 |
| B Y40 ON, 0–0.5 cell | 1368 | 0.0801772 | 0.225535 | 3.16240 | 540 |
| B Y40 ON, 0.5–1 cell | 1080 | 0.00924393 | 0.0144429 | 0.675930 | 156 |
| B Y40 ON, 1–2 cells | 1428 | 0.00000279878 | 0.00000756228 | 0.00000835252 | 0 |
| B Y40 ON, 2+ cells | 536 | 0.00000307654 | 0.00000791688 | 0.00000835252 | 0 |
| B Y40 ON, axis近傍 | 144 | 0.00000299748 | 0.00000791688 | 0.00000835252 | 0 |
| C Y40 OFF, 2+ cells | 536 | 0.898531 | 6.78215 | 8.92828 | 536 |
| C Y40 OFF, axis近傍 | 144 | 1.02838 | 7.37207 | 8.35711 | 144 |

従来の約0.719 m/sは実Meshで1 cellより深い位置には再現しなかった。Bの1 cell以深と中心軸近傍は最大`8.35253e-6 m/s`で、既存gate `1e-5 m/s`以下である。`1e-12`／`1e-6`では深部まで非ゼロで、6近傍の外部から最大約3.05 cellまで連結した。したがって「数学的に完全なゼロ」ではなく、既存gateに対して表面1 cell以内へ限定された結果である。18/26近傍は補助値としてreportに分離した。

実Meshでは外側だが理想Cylinderでは内側となるBのcell recordが352件あり、その最大速度は2.97754 m/s、`>1e-5`は160件だった。これは旧Cylinder volume ROIが低ポリ表面外部を内部として数えた可能性を直接示す。一方、Bの回転Meshで1 cellより深いmeanは約`2.87e-6 m/s`に抑制され、元のaxis位置だけに属する領域は抑制されない。観測上はcollision位置が旧axis位置へ残ったstale transformより、Y40 transformへ追従した説明と整合する。

## Classification and limits

既存`1e-5 m/s` gateに対する主分類は「実Mesh表面から概ね1 cell以内に限定されたboundary/ROI effectが有力」である。低い`1e-6` thresholdでは数cell深部まで連結した微小値があるため、Flow内部occupancyや演算が完全にゼロであるとは主張しない。これは公開APIから得た幾何ラベルとfield readbackの関係であり、内部collision maskの証拠ではない。

Phase 6EC gateは変更せず、回転collisionも未qualifiedのままにする。次の独立Phase候補は、旧Cylinder ROIを実Mesh距離帯へ置き換えたqualificationを先に定義し、その後に必要ならMesh分割数またはvelocity cell sizeを一変数で比較すること。CollisionProxy authoring修正、production統合、任意軸回転、dynamic transformへはまだ進まない。

## Lifecycle and verification

A/B/Cはfunctional pass、normal OS exit、performance sample accepted、fatal/native crash/dump/automatic upload/residual 0。active blocks finalは26/24/58、source fuelは全て0.8。最初のoffline analyzer safe stopは、追加divergenceを含む24ファイルを「必須5 channel×4 frameのちょうど20」と誤判定した集計gateだけが原因で、raw Kit runは再実行していない。gateを必須channel各4件の検査へ修正し、同じNPZをoffline再集計した。

Release buildは6.38秒、Phase 0 RTXはexit 0。Phase 3はdry/wet mass-balance error 0、authority SHA-256 `0dec57f3...e84be10`／`148585f8...d2b20c9`、Flow active blocks final/peak 258/349、peak fuel input 1.0だった。Phase 6EE 7/7を含むPhase 6EC～6EE targeted contractは60/60、標準suiteは8 process・78/78件・310.8秒で合格した。

日誌は521 local reference（318 unique）、JSON 184、SVG 151、missing／parse failure／replacement character／duplicate ID 0。73-entry raw archiveもCRC検査に合格した。接続可能なBrowser instanceがなかったため実レンダリング確認はできず、HTML/SVG/JSON/ZIP静的検査で代替した。Kit/CDB残留、Phase 6EE fatal、dump、automatic upload attemptは0。production app SHA-256は実測・build・回帰後も`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`で一致している。
