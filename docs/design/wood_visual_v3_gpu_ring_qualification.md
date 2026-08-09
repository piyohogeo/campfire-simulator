# Phase V3T-E GPU-source ring qualification

## 結論

`set_bytes_data_from_gpu()`の2重・3重source ringは、20本相当のbase＋emissionでowner threadの明示同期待ちを小さくし、Provider setter p95を約`0.2 ms`に保った。しかしproduction採用条件は満たさない。固定Kit 110.2の公開APIにはProviderがsource pointerを読み終えたことを示すevent／fence／documented lifetimeがなく、240回の実RTX readbackでも34回の複数revision混在を観測したためである。production V3、V3T-C consumer、既定値は変更しない。

## 固定境界

- 基準HEADは`e8bd9f2`。probeはproduction V3 moduleをimportせず、独立extensionとscriptだけで構成する。
- Kit 110.2、Flow 110.0.0、RTX 3090、RGBA8、96×15と120×60、base＋emissionの2枚を維持する。
- Provider 2個、dynamic URI、USD Prim、UV Mesh、material binding、asset pathを測定前に作り、性能区間では変更しない。USD revision Setも行わない。
- 最大3 slot×2 textureのWarp device arrayをprocess開始時に確保し、Provider破棄までresize、free、reallocationしない。CPU pointerの偽装、private API、`get_managed_resource()`の保持は行わない。
- source revisionは表示検査専用であり、wood authority、Flow input、checkpoint、Resident revision／rollbackへ入れない。

## 実装した方式

| 方式 | source ready | 再利用 |
|---|---|---|
| CPU reference | NumPy所有bufferを`set_raw_bytes_data()`へ渡す | 同じ永続bufferを次publication前まで不変に保持 |
| single GPU sync | Warp所有bufferへH2D後、毎回`warp.synchronize_device()` | 1 slot、完全source-generation同期 |
| GPU ring 2 | slot固有streamへH2D、公開Warp Eventをsetter前に同期 | A→B、各slotを2 publication空けて再利用 |
| GPU ring 3 | 同上 | A→B→C、各slotを3 publication空けて再利用 |
| immediate reuse stress | setter直後に同じslotへ次revisionをenqueue | tearing検出専用、production候補外 |

Eventが保証するのはWarp stream上のsource生成完了だけである。`set_bytes_data_from_gpu()`は`None`を返し、docstringは「GPU memoryのcopyからdataを設定する」とだけ記述する。Provider source消費完了event、使用stream、multi-GPU device、再利用可能時点は公開契約にない。ringの再利用間隔は実測可能なbest effortであり、ABI／lifetime保証ではない。

## 測定

各atlasを3独立processで実行し、runごとに4方式の順序をrotateした。各方式はwarmup 20後に120 sample、合計`2,880`性能sampleである。captureとファイル保存は性能母集団から除外した。各publicationは2 texture、96×15では`11,520 B`、120×60では`57,600 B`、Provider API callは2回である。

### 120×60、Flow＋RTX、median-of-three p95

| 方式 | pattern生成 | H2D enqueue | 明示同期 | Provider setter | 次RTX frame | Kit update全体 |
|---|---:|---:|---:|---:|---:|---:|
| CPU reference | 1.3869 ms | 0 | 0 | 27.5362 ms | 31.1384 ms | 34.1094 ms |
| single GPU sync | 1.5290 ms | 0.3652 ms | 0.7911 ms | 0.2152 ms | 30.7357 ms | 32.5311 ms |
| GPU ring 2 | 1.5110 ms | 0.2594 ms | 0.0599 ms | 0.2008 ms | 31.6607 ms | 33.0441 ms |
| GPU ring 3 | 1.5065 ms | 0.2722 ms | 0.0689 ms | 0.2193 ms | 31.5550 ms | 32.5468 ms |

ringはsingle GPU referenceの同期p95を約`0.79 ms`から`0.06–0.07 ms`へ減らした。2重と3重の差は実用上小さい。GPU setterは全120 sampleで5 ms超過0、p95約`0.2 ms`を維持した。一方、次requested RTX frame p95は約`31 ms`のままで、Flow＋RTX end-to-end latencyを解決していない。CPU referenceは27.5362 msのsetter tailを再現した。

96×15ではGPU setter p95は`0.2159–0.2306 ms`だったが、GPU方式の次frame p95は`48.7678–49.6075 ms`、CPU setter p95は`98.3876 ms`まで悪化した。小さいatlasが速いという帯域支配の傾向ではなく、実行時scheduler／renderer境界の不安定性を示す観測である。内部原因は未確認であり、120×60結果と平均化しない。

## pixel readback

各revisionを8色×32 macroblockの識別patternにし、base／emission URIを2枚のdiffuse-only診断Meshへ接続した。Flow geometryの遮蔽とemissive bloomを分離し、publication後24明示viewport frameを進めてから、公開`capture_viewport_to_file()`のPNGをblock単位でCPU referenceと比較した。

| 方式 | 最新完全 | 複数revision混在 | 合計 |
|---|---:|---:|---:|
| CPU reference | 52 | 8 | 60 |
| single GPU sync | 51 | 9 | 60 |
| GPU ring 2 | 51 | 9 | 60 |
| GPU ring 3 | 52 | 8 | 60 |

全240 readback中、最新完全206、混在34、invalid 0、1世代前0だった。混在率はCPU reference、同期GPU、2重、3重で同程度で、ring固有の悪化は観測していない。強い推定は、2枚の逐次publicationとrenderer/capture反映境界が主な候補という範囲に留める。実画素が混在した観測自体は採用gateを満たさないため、原因推定で合格へ読み替えない。即時再利用stressは12回中10最新完全、2混在で、通常方式との差を断定できなかった。

## lifecycle

- timeline STOP／再開、stage reload、stage replacement、Provider再生成、GPU source生成失敗後のCPU fallbackは完全revisionを表示した。stage replacementは別runで1世代前完全も許容範囲として観測している。
- publication途中にbaseだけGPU発行して例外を注入し、transportをfaultedへ遷移して次publicationをCPU fallbackした。無効pointerは再利用しなかったが、そのfallback readbackは複数revision混在でありpixel gate不合格である。
- 1,200連続ring3更新は7 checkpointすべて最新完全、device lost、use-after-free、invalid device pointer、illegal addressは0だった。
- close直前のpublication後に1 requested RTX frameをdrainした。実Kit extension managerからisolated extensionをdisableし、`on_shutdown()`で「Warp source生成同期→Provider destroy→GPU allocation release」の順を記録した。extension object保持warningも除去した。
- lifecycle gateは10 / 12。startup warmup readbackとpartial-publication CPU fallback readbackが混在で不合格である。
- Warpは`cuda:0 / NVIDIA GeForce RTX 3090 / sm_86`、`nvidia-smi`は同一process環境のGPU 0を示した。ただしrenderer／Provider側device identityを返す公開APIがないため、device matchは「強い状況証拠、正式には未確認」とする。
- ring3 device sourceの明示所有量は最大`172,800 B`、同じhost source量も`172,800 B`。最終lifecycle runのwhole-GPU telemetryは平均`5,465.574 MiB`、最大`6,582 MiB`だが、Provider所有量とは主張しない。

## 観測・推定・未確認

- 観測事実: 全timer、tail count、2,880 sample、240 PNG readback、34混在、1,200更新、lifecycle transition、fault fallback、close順序、runtime docstring、whole-GPU telemetry。
- 強い推定: ring prefetchはsource-ready待ちをowner threadからほぼ除去する。CPU referenceとGPU方式の混在率が同程度なので、観測混在はring再利用だけでは説明できない。
- 未確認: ProviderがGPU sourceを読み終える正確な時点、renderer fence、Provider使用stream、正式なrenderer/Warp device一致、Provider所有memory、96×15の大きなscheduler差の内部原因。

## 採否と停止点

production統合条件は不成立である。理由は、(1) public source-consumed fence／documented reuse lifetimeがない、(2) 通常画素240件に34件の混在、(3) lifecycle 12 gate中2 gate未達、の3点である。したがってproduction V3、V3T-C consumer、設定schema、既定値、CPU reference/fallbackを変更しない。GPU ringはprobe成果として停止し、公開fence/lifetime契約を持つ将来API、Kit更新の隔離再評価、または操作上の支障が具体化した場合だけ再開する。

## 最終回帰

- release buildは`8.34 s`、Phase 0はRTX ready `16.423 s`で合格した。
- 標準suiteは全8 process・`77 / 77`件が`385.0 s`で合格し、collapse coverageは`227.4 s`だった。120秒で外側runnerが終了した先行試行は結果へ含めず、孤立processを特定・停止した後、競合processなしで完走した最終runだけを採用した。
- V3T-Cは隔離出力で6/6 run、wood authority／metrics SHA／mass balance／ignition／Resident revision／Flow input／1 update以内のRTX reflectionをまとめた`7 / 7` gateに合格した。OFF/ON update-frame p95中央値は`8.9032 / 7.4781 ms`で、判定は従来どおり`qualified_functionally_explicit_preset_only`である。
- Phase 6DQは既存成果物を上書きしない隔離出力で`11 / 11` gate、rigid-frame revision `710`、active blocks peak `397`、`59 / 60` unique video frameを再確認した。
- 機械可読な回帰集計は`docs/devlog/assets/phasev3te/regression_report.json`と`gpu_ring_report.json`内の`regression`に固定する。

再現コマンドは`powershell -ExecutionPolicy Bypass -File .\scripts\run_phasev3te_gpu_ring.ps1`。raw sample、集計、SVGは`docs/devlog/assets/phasev3te/`に固定する。
