# Flow Emitter動的転送のスケーラビリティ設計メモ

## 結論

現在のSphere Emitter 1個とResident snapshot 19属性の最適化は継続する。Phase 6BNで採用した`Sdf.ChangeBlock`、revision-last、immutable snapshot replay、lifecycle、rollback契約も維持する。一方、Point Emitter／NanoVDB Emitterへ移行すると、通知数だけでなく動的payloadの生成・コピー・取込み・ラスタライズが支配的になり得るため、別の容量軸として扱う。

表面サンプル点ごとにEmitter Primを作る方式は採用しない。Point候補は全薪をまとめた1 Primを第一候補、薪ごとの最大20 Primを分離制御が必要な比較候補とする。production採用は未決であり、本メモとPhase 6BOは既定OFFの技術スパイクだけである。

## 固定SDKで確認したAPI境界

- `omni.usd.schema.flow 110.0.0`の`FlowEmitterPoint`は、1 Primに`pointPositions`、`pointFuels`、`pointTemperatures`、`pointSmokes`の各配列を持つ。同梱`PointCloud/Native.usda`にも同じ構成がある。
- `FlowEmitterNanoVdb`は`nanoVdbFuels`、`nanoVdbTemperatures`、`nanoVdbSmokes`などを`uint[]`のNanoVDB word配列として受け取る。各チャンネルにはasset pathとfirst-element offsetもある。
- 同梱C++ OmniGraphノード`OgnFlowVoxelizePoints`はCPUのpoints/colors配列を`IFlowUsd::voxelizePoints`へ渡し、readback後に4チャンネルをOmniGraphの`uint[]`へ要素単位でコピーする。この候補では、Set回数よりvoxel生成、GPU/CPU readback、4配列コピーが支配する可能性がある。
- 公開Python APIとして確認できたのは`PublicExtension`とFlow command登録だけである。C++実装は`IFlowUsd`を使うが、そのpublic headerは現在のbuild成果物に同梱されていない。FabricからEmitterへ直接動的payloadを渡す公開APIも未確認であり、利用可能性を確認する前に採用を前提としない。
- Kit同梱NumPyから`Vt.*Array.FromNumpy`へ変換後、元NumPy配列を変更してもVt配列は変わらなかった。現在の境界は実測上zero-copyではない。

## 対象規模

1本は24×12×4 = 1,152セルである。表面候補は外周`24×12 = 288`、両端面`2×4×12 = 96`、重複する外周端`2×12 = 24`を差し引き、1本360点となる。20本では7,200点である。

Phase 6BOは360、1,800、3,600、7,200点を測った。全配列更新はposition 12 bytesとfuel/temperature/smoke各4 bytesで24 bytes/点、位置固定後の動的3チャンネルだけなら12 bytes/点である。revisionはEmitter当たり8 bytesとして別計上した。

## Phase 6BO USD-only実測

release Kit Python、`Usd.Stage.CreateInMemory`、120計測＋20 warmupで測った。これは`omni.flowusd`取込みもFlow実行もない転送境界の下限値であり、Phase 6BNの実Flow p95とは直接比較しない。

| 7,200点の構成 | 更新 | Set/フレーム | 論理転送量 | source p95 | NumPy→Vt p95 | USD Set p95 | block exit/notice p95 | 発行p95 | 全体p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Point 1 Prim | 全4配列 | 5 | 172,808 B | 0.6922 ms | 0.1202 ms | 0.0974 ms | 0.0565 ms | 0.1513 ms | 0.9816 ms |
| Point 1 Prim | 動的3配列 | 4 | 86,408 B | 0.0079 ms | 0.0385 ms | 0.0277 ms | 0.0178 ms | 0.0474 ms | 0.1079 ms |
| Point 20 Prim | 全4配列 | 100 | 172,960 B | 0.7005 ms | 0.1789 ms | 0.5031 ms | 0.1237 ms | 0.6075 ms | 1.4477 ms |
| Point 20 Prim | 動的3配列 | 80 | 86,560 B | 0.0100 ms | 0.0859 ms | 0.3346 ms | 0.0920 ms | 0.4408 ms | 0.5471 ms |

1 Point Prim・動的3配列ではSet数は4のまま、NumPy→Vt p95が360 / 1,800 / 3,600 / 7,200点で`0.0051 / 0.0119 / 0.0224 / 0.0385 ms`へ増えた。USD Set p95も`0.0176 / 0.0208 / 0.0285 / 0.0277 ms`だった。小規模ではノイズを含むが、Set回数一定でも配列コピーが点数とともに増えるという分離は確認できた。

全構成で`Sdf.ChangeBlock`により`Usd.Notice.ObjectsChanged`は1更新1回となり、listenerが読んだ全Emitter revisionは一致した。fuel・temperature・smokeは点数と合計値が入力と一致した。プロセスworking setのpeak差は0～376,832 bytesだったが、USD native allocatorを構成別に分離できないため参考値とする。

現在の19属性controlは、Sphere Emitterの6 payload＋revisionと、2本のvisual/diagnostic payload＋各revisionを含む。in-memory USD発行はmean / p95 / max `0.0959 / 0.1445 / 0.2451 ms`だった。ただしPoint側の20本・7,200点payloadと同値の比較ではなく、既存Set回数の基準線である。

## 分離して扱う計測軸

`Sdf.ChangeBlock`が直接改善できるのは通知配送である。以下は別に測る。

1. Resident source配列またはNanoVDBの生成
2. Python/C++/OmniGraph境界の変換とコピー
3. USD属性へのauthoringとSet回数
4. `Usd.Notice.ObjectsChanged`の回数、block exit、consumer callback
5. `omni.flowusd`の取込み
6. Flow Emitter処理とラスタライズ
7. solverと描画
8. CPU/GPU転送bytes、working set、GPU memory

通知集約は2～3や5～8を消さない。NanoVDBではさらに、チャンネル生成、readbackまたは転送、Flow取込みの測定が中心になり、Set回数は二次的になり得る。

## 4構成の比較計画

| 構成 | Prim数 | 主な動的payload | 現在の状態 |
|---|---:|---|---|
| 現在のSphere | 1 emitter | scalar emitter値。現行snapshot全体は19属性 | production方針を継続。Phase 6BNで4 ms gate達成 |
| 全薪Point | 1 | 最大7,200点の3～4配列 | schema確認、USD-only測定済み。Flow未測定 |
| 薪ごとPoint | 最大20 | 各360点の3～4配列 | schema確認、USD-only測定済み。Flow未測定 |
| NanoVDB | 1または少数 | fuel/temperature/smoke等のNanoVDB word配列 | schemaと生成候補を確認。生成・取込み・Flow未測定 |

## 次の推奨実験

productionコードを変えず、別runnerで実Flow matrixを既定OFF実行する。

- Sphere、Point 1 Prim、Point 20 Prim、NanoVDB 1／少数を同じ240 snapshot revisionで順序反転する。
- Pointは360 / 1,800 / 3,600 / 7,200点を維持し、位置を毎回更新するcaseと位置を固定するcaseを分ける。
- NanoVDBはまず`OgnFlowVoxelizePoints`の生成＋readback＋4配列copyを一つの観測区間として測り、可能ならチャンネル別bytesを記録する。公開timerで分解できない区間は「未計測」とし、推定値で埋めない。
- Flow active block、フレーム時間、solver/render、CPU/GPU memory、最終fuel/temperature/smoke、consumer revisionを記録する。公開APIがingestとrasterを分離しない場合はaggregate値として明記する。
- USD経路の容量上限を見つけた後にだけ、固定Flow版のC++、OmniGraph、Fabric、公開native境界を比較する。未公開headerやbinary内部APIには依存しない。

この実験が終わるまでPoint／NanoVDBをproduction採用せず、物理式、JSON schema、既定値、rollback、revision、immutable snapshot契約を変更しない。

再現コマンドは`powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_phase6bo_emitter_transport_scalability.ps1`である。標準回帰は全8 process・47 / 47件を320.0秒で合格した。

## Phase 6BP/BQ 固定Flow runtime境界の途中評価

productionを変更しない既定OFF runnerで、同梱`PointCloud/Native.usda`と実`omni.flowusd`を調べた。Flow stage接続後にPointCloud内部のEmitterを削除・再定義し、core simulationを有効化した試行は`omni.flowusd.plugin.dll`でnative crashした。そのためlive stageの構造変更は比較方法として不採用とし、以後は既存Primへの値設定またはステージ接続前のoverlay authoringだけに限定した。

同梱command実装ではNative PointCloudが`FlowEmitterPoint.pointsPrim` relationshipでUSD `Points`を参照する。`FlowEmitterPoint`へ`pointPositions`／`pointFuels`／`pointTemperatures`／`pointSmokes`を直接設定する試行、および完成済みoverlayで`pointsPrim`を事前authoringする試行は、USDの点数・合計値・revisionが一致し、1 publicationにつき関連`ObjectsChanged` 1回で完走した。しかし固定buildのFabricはpoint channelまたはrelationshipを未登録と警告し、public active-block／NanoVDB readbackは0だった。したがってこの経路のFlow取込み・rasterization・出力同値性は未確認であり、成功値として扱わない。なおNative PointCloud presetはcore simulationを既定で無効にするため、public active-block queryがこのoffscreen point-cloud処理を表す保証もない。

一方、固定extensionのbundled testと`FlowVoxelizePointsAndSync` commandが実際に呼ぶ`IFlowUsd.voxelize_points_and_sync_v2`は利用可能だった。runtime docstringも取得し、points/colorsは連続`numpy.float32`、2 transformは`numpy.float64`、cell sizeとmax blocksを受け、5 bufferを返すことを確認した。`init_persistent_voxelize_context()`／`release_persistent_voxelize_context()`は引数なしである。persistent contextを使わない反復は360点・`maxBlocks=256`でもprivate memoryが8 GBを超えて完了せず、毎frame利用候補として失格である。persistent contextをrun全体で再利用すると120計測＋20 warmupを安定完了した。

| 薪 | 点 | 入力bytes/update | source mean | contiguous準備 mean | native voxelize＋NanoVDB＋sync mean / p95 / max | 5 buffer bytes |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 360 | 8,640 | 0.0335 ms | 0.0030 ms | 3.0708 / 4.0099 / 9.6276 ms | 2,901,280 |
| 5 | 1,800 | 43,200 | 0.0355 ms | 0.0038 ms | 3.2976 / 4.2650 / 4.9662 ms | 5,794,880 |
| 10 | 3,600 | 86,400 | 0.0417 ms | 0.0032 ms | 4.1380 / 5.5074 / 5.9611 ms | 9,523,840 |
| 20 | 7,200 | 172,800 | 0.0563 ms | 0.0046 ms | 4.3039 / 5.7224 / 6.1838 ms | 10,896,000 |

これはpoint sourceからNanoVDBを作って同期するproducer境界だけの値であり、NanoVDB EmitterへのUSD発行、`omni.flowusd`取込み、consumer revision、Flow solver、描画は含まない。20本ではproducerだけで4 msを超え、入力172.8 KBに対して生成payloadは約10.90 MB/updateとなった。したがってSet回数削減や`Sdf.ChangeBlock`だけでは解消せず、共有SoA＋Python proxy案もこのGPU voxelize／NanoVDB転送ボトルネックを解決しない。

現時点の判断は「native NanoVDB producerは実在するがproduction不採用」である。次は固定Flow版が5 bufferを`FlowEmitterNanoVdb`へ安全に接続できる公開consumer境界を、同梱command／OmniGraph／schemaの範囲で調べる。接続できるまでsolver/renderを含む比較値やfuel・temperature・smoke同値性を推定しない。再現は`run_phase6bq_flow_native_voxelize.ps1`、binding調査は`probe_flow_native_interface.py`である。標準Kit suiteは全8 process・47 / 47件を317.4秒で合格した。

## Phase 6BR–6BT NanoVDB buffer意味論とconsumer試行

固定Flow runtime、schema、同梱C++ OmniGraph node、`omni.volume` bindingを照合した。`voxelize_points_and_sync_v2`の5 bufferは、色をRだけ／Gだけ／Bだけ変える4ケースで次のように識別できた。index 0 / 1 / 2はそれぞれ入力R / G / Bだけに反応するNanoVDB float grid、index 3は入力色に依存しないalpha占有grid、index 4は全RGB入力に反応するgrid type 12のpacked RGBA8である。最初の4本はschemaのtemperature / fuel / burn / smoke、5本目は`nanoVdbRgba8s`に対応する。同梱schemaもPointの`pointColors`をtemperature / fuel / burn、RGBA8をtemperature / fuel / burn / smokeと定義している。各bufferは`buffer_to_volume()`で1 grid、grid名`Flow`、同じindex/world境界として読めた。

live stageのPrim削除・再定義はPhase 6BPでnative crashしたため行わず、Emitter、payload、revisionを全てoffline stageへauthoringしてからKitへ接続した。1本360点、cell size`0.025 m`、max blocks`256`の同一入力で次を試した。

| 公開consumer候補 | USD payload | stage接続 | consumer revision | Flow active block / readback | 判定 |
|---|---:|---|---:|---:|---|
| 4 float direct arrays | 4属性、USDA 4,634,548 B | 完了 | 1 | 0 / 空 | 未接続 |
| packed RGBA8 direct array | 1属性、USDA 1,168,567 B | 完了 | 1 | 0 / 空 | 未接続 |
| FlowPointCloud内 packed RGBA8 | 1属性、USDA 1,168,888 B | 完了 | 1 | 0 / 空 | 未接続 |
| `volumePrim`→UsdVol→`.nvdb` | relationship、`.nvdb` 11,560 B | 完了、Fabric proxy警告 | 1 | 0 / 空 | 未接続 |
| `nanoVdbRgba8s:assetPath` | asset + gridName、`.nvdb` 11,560 B | 完了 | 1 | 0 / 空 | 未接続 |

この試験の各process最初のvoxelize callはCUDA／Flow初期化を含み`36.8–41.1 s`だったため、Phase 6BQのsteady-state producer性能と混ぜない。直接配列のNumPy→Vt、offline Set、USDA保存、stage open値も静的な接続診断であり、高頻度発行性能ではない。`.nvdb`保存自体は`1.51–2.58 ms`だったが、ディスク経路は動的production候補にしない。

結論は「buffer意味論は確認、公開NanoVDB consumerは未qualified」である。USDに値が保存されrevisionが一致しても、Flow取込み、rasterization、solver、描画、fuel／temperature／smoke同値性の成功を意味しない。固定版の正式サンプルまたは公開APIでconsumer接続条件を追加確認できない限りNanoVDB比較の下流値を埋めず、Sphere production経路を維持する。共有SoA案もUSD発行やNanoVDB consumer不在を解決しない。再現は`run_phase6bs_flow_nanovdb_buffer_probe.ps1`と`run_phase6bt_flow_nanovdb_consumer.ps1`で、どちらも既定OFF、production変更なしである。標準Kit suiteは全8 process・47 / 47件を328.1秒で合格し、collapse coverageも189.3秒で完了した。

## Phase 6BU 公開native consumer APIの可用性ゲート

固定buildで実際に取得した`omni.flowusd._flowusd.IFlowUsd`を列挙すると、公開メンバーは19個だった。内訳はpoint／velocity pointからのvoxelize、persistent voxelize context、Flow readback、grid値／block数の照会、serialized NanoVDBから`omni.volume.GridData`を作る`buffer_to_volume()`、および`save_nanovdb(uint32[], path)`である。名前とruntime docstringの両方を監査したが、外部NanoVDB bufferをFlow Emitter consumerへattach、ingest、inject、set、submit、uploadする公開メンバーは0個だった。`buffer_to_volume()`はCPU側のvolume表現への変換、`save_nanovdb()`はファイル保存であり、どちらもconsumer注入境界ではない。

したがって、固定版の公開native APIもPhase 6BTの5候補をqualifiedにはしない。private ABI、未確認のFabric property、live stage再定義へ進まず、NanoVDBの下流比較は「利用可能性未成立」で停止する。これは性能負けではなく接続資格不足である。比較表ではproducer生成時間、payload量、静的USD境界までは実測値を残し、`omni.flowusd`取込み、Flow raster／solver／render、出力同値性は未計測のままにする。production Sphere経路と全契約は維持する。再現は`run_phase6bu_flow_native_consumer_api_audit.ps1`で、Phase 6BT runnerも安全な未qualified結果を正常な診断として返す。20 frame／warmup 1の最小否定smokeは46.3秒で正常終了し、revision `1`一致、active block peak `0`を報告した。標準Kit suiteは全8 process・47 / 47件を323.4秒で合格し、collapse coverageも188.6秒で完了した。
