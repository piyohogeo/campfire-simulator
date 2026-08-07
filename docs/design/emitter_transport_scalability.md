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
