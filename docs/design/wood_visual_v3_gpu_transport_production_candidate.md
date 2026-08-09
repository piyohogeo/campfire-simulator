# Phase V3T-F GPU-source production候補の採否

## 結論

三重GPU-source ringはowner thread上の`DynamicTextureProvider` setter tailを大幅に減らした。しかし、最終lifecycle probeがKit終了中にWindows access violation `0xC0000005`で停止したため、production採用条件を満たさない。候補実装、設定、V3 demo preset変更はすべて`c5cbb4a`相当へ戻した。現行V3は既定OFFかつCPU-sourceのままである。

このPhaseは性能上の可能性を記録するprobe-onlyの安全な停止点であり、「完全に安全」「原子的」「tearing-free」とは扱わない。

## 固定した境界

- Kit 110.2、Flow 110.0.0、RTX 3090を維持した。
- 20本相当、120×60 RGBA8 atlas、base＋emission各1枚を使用した。
- Provider、dynamic URI、USD Prim、UV Mesh、material binding、asset pathは測定開始前に構築し、測定区間では変更しなかった。
- wood authority、Flow入力、物理式、checkpoint、serialization、Resident revision／rollback、Mesh collider、形状、Point／rigid layout、Sphere既定を変更していない。
- V3表示は再生成可能なobserverであり、woodまたはFlowのcommit条件に使わない。

## 一時的に検証したproduction候補

候補は既存base／emission Providerを維持し、各textureに3個の永続Warp GPU source bufferを割り当てた。slotはA→B→Cで循環し、probe所有stream／eventによりsource生成完了をsetter前に待った。公開されていないpointerやprivate API、CPU pointer偽装、`get_managed_resource()` cacheは使っていない。

設計上はV3 OFF、V3 ON＋GPU OFF、V3 ON＋GPU ONを分離し、初期化失敗はpublication前にCPUへfallback、途中失敗はGPU経路をfaultedにして次の完全なbase＋emission境界からCPUへfallbackする案だった。表示だけをeventually consistent best-effort observerとして扱い、最新と直前revisionの一時混在を許容する方針も反映した。

ただし、`set_bytes_data_from_gpu()`はProviderがsourceを読み終えたことを通知する公開fence、消費stream、再利用可能時点を提供しない。三重ringは固定環境で再利用間隔を増やすbest effortであり、API保証ではない。

## 性能の観測事実

各transportを3独立run、runごとにwarmup 20、測定120回、計720 publication sampleで比較した。20本・120×60・base＋emission・Flow＋RTXの全run集計は次のとおり。

| 指標 | CPU reference p95 | GPU ring3 p95 |
|---|---:|---:|
| pattern生成 | 2.3709 ms | 2.4027 ms |
| H2D enqueue | 0 ms | 0.6046 ms |
| source-ready待ち | 0 ms | 0.6105 ms |
| Provider setter | 29.8788 ms | 0.2531 ms |
| publication合計 | 31.7981 ms | 4.5846 ms |
| 次requested RTX frame | 72.3302 ms | 56.8542 ms |
| Kit update | 21.5407 ms | 23.4482 ms |

GPU setterは全360 sampleで5 ms未満、p95 1 ms未満だった。CPU-sourceで観測された約28～35 msのsetter tailはGPU ring3では再発していない。source-ready待ち＋setterもCPU setterより明確に小さい。

一方、次RTX frameはGPUでもp95 56.8542 msである。GPU transportはowner threadのpublication stall候補を減らしたが、Flow＋RTXのend-to-end frame latencyを解決したとは扱わない。

## 画素とeventual consistency

probe専用revision macroblockをactual RTX viewport PNGからreadbackし、CPU／GPUを比較した。1,200回連続更新と停止後のbounded convergenceは、クラッシュ前のprocessで成立した。初期化失敗、途中publication例外、timeline STOP／再開、stage replacement、Provider再生成も個別に通過した。

ただし、RTX exposureとtemporal renderingを通した色からrevisionを逆分類する処理は安定せず、探索runではinvalidや2世代以上古いという分類も生成した。別runではCPU／GPUとも10/10の完全revisionを観測したが、classifier結果をproduction画素安全性の証明へ読み替えない。保持した`production_gpu_ring_precrash_report.json`は探索的なraw evidenceであり、最終qualificationではない。

許容方針は最新／直前revisionの一時混在、base／emissionの1 revision差、停止後の最新収束だったが、終了時クラッシュが独立した必須gateを破ったため、画素許容方針にかかわらず不採用である。

## lifecycle停止条件

最終の隔離lifecycle processは約29.5秒でexit code `3221225477`（`0xC0000005`）となった。logの主なbacktraceは次の境界である。

1. `UsdGeomCylinder_1::ComputeExtent`
2. `UsdContext::unregisterViewOverrideToHydraEngines`
3. event dispatcher
4. timeline
5. Kit shutdown

logにはCUDA illegal addressまたはdevice lostという明示メッセージはない。backtraceのUsdGeom frameはlow-confidenceを含み、GPU source lifetimeが原因だとは断定できない。しかし、公開source-consumed fenceがない以上、Provider破棄／source allocation解放との因果を反証することもできない。ユーザー指定ではクラッシュまたは終了時不正解放がproduction接続撤回条件なので、原因未確定のまま不合格とした。

## 最終production状態

- `woodVisualV3GpuTransportEnabled`相当の設定は追加していない。
- `campfire.simulator.kit`、benchmark app、V3明示demo presetは変更していない。
- V3は既定OFF、CPU-source経路を維持する。
- Pointとrigid layoutは既定OFF、Sphere Emitterがproduction既定である。
- GPU transport失敗がwood、Flow、物理、checkpoint、Resident revisionへ伝播する経路は残していない。
- runtime probeは安全基準点ではfail closedし、保持済み証拠のanalysis-only再生成だけを許す。

## 観測事実・推定・未確認

観測事実:

- GPU ring3はProvider setter p95を29.8788 msから0.2531 msへ下げた。
- 720 timing sampleと1,200-update probeを取得した。
- lifecycle終了時に`0xC0000005`が発生した。
- production候補差分は最終回帰前にすべて撤回した。

強い推定:

- GPU-sourceはowner-thread latencyには有望だが、固定環境でproduction採用するにはlifetime／shutdown境界が不足している。

未確認:

- source buffer再利用または解放がクラッシュに寄与したか。
- low-confidenceのUsdGeom backtraceが根本原因か、shutdown後の二次的結果か。
- rendererがGPU sourceを読み終える正確な時点。
- base／emission間または単一texture内の原子的更新。

## 再開条件

次のいずれかが成立するまでproduction統合を再開しない。

1. 公開source-consumed fenceまたはGPU pointer再利用／lifetime契約が提供される。
2. 隔離したKit／renderer更新環境で、繰り返しshutdown、stage replacement、extension disable、長時間更新がcrash-freeになる。
3. CPU-source経路が実操作上の支障となり、独立再評価の費用を正当化する。

再開時も、CPU fallback、V3既定OFF、observer非authority、Flow／wood非変更を維持する。

## 成果物

- 最終採否: `docs/devlog/assets/phasev3tf/production_gpu_ring_report.json`
- 720 timing sample: `docs/devlog/assets/phasev3tf/production_gpu_ring_samples.json`
- crash前探索report: `docs/devlog/assets/phasev3tf/production_gpu_ring_precrash_report.json`
- shutdown抜粋: `docs/devlog/assets/phasev3tf/shutdown_crash_excerpt.txt`
- 比較図: `docs/devlog/assets/phasev3tf/production_gpu_ring_report.svg`
- analysis-only再生成: `.\scripts\run_phasev3tf_production_gpu.ps1 -AnalyzeRetainedEvidence`
