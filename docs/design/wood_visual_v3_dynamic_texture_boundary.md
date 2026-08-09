# Phase V3T-D DynamicTextureProvider publication境界

## 結論

V3T-Cの`cpu_upload_ms`は単純なCPU→GPU memcpy時間ではなく、`DynamicTextureProvider.set_raw_bytes_data()`によるCPU-source publication callの同期時間として読む。固定Kit 110.2 / Flow 110.0.0 / RTX 3090では、20本相当の120×60 RGBA8 atlasをbase+emissionの2枚連続で発行したp95は、provider未接続`1.8164 ms`、UV Mesh接続・RTX描画なし`1.8089 ms`、RTX描画・Flow OFF`2.1147 ms`に対し、RTX＋Flow実行中だけ`28.8968 ms`へ増えた。96×15でも`28.6312 ms`であり、5倍のbyte差に追従しなかった。

同期済みのprobe所有Warp GPU bufferから`set_bytes_data_from_gpu()`を呼ぶと、RTX＋Flow実行中のsetter p95は`0.2021 ms`、明示CPU→GPU staging p95は`1.4223 ms`だった。一方、publication完了から次のrequested RTX frame完了までのp95はCPU-source `32.7710 ms`、GPU-source `31.4113 ms`で残った。したがって、約35 msの同期setter tailの主因候補は「Flow負荷中のCPU-source provider publication境界」であり、画像生成量、未接続provider固定費、通常のRTX resource使用だけでは説明できない。GPU-sourceはsetter内tailを除くが、Flowを含むframe/render latency自体は除かない。

これは原因境界の分類であり、`DynamicTextureProvider`、resource manager、CUDA/D3D interop、renderer fenceの内部実装を特定した証拠ではない。production V3、V3T-C、既定値は変更しない。

## 固定した測定契約

- production moduleをimportせず、probe固有provider名、dynamic URI、USD stage、UV Mesh、UsdPreviewSurface、base/emission providerをprocessごとに測定前構築した。
- 4本相当は`96×15×4 = 5,760 B/texture`、20本相当は`120×60×4 = 28,800 B/texture`。2枚連続はそれぞれ`11,520 B`と`57,600 B`、API callは2回である。
- 未接続固定、未接続変更、Mesh接続・RTX描画なし、RTX＋Flow OFF、RTX＋Flow ON、GPU-source＋Flow OFF/ONを別processで実行した。各条件はwarmup 20後にcaseごと120 sample、3独立runで、case開始順とprocess mode順をrunごとにrotateした。
- 未接続と描画なし条件は`omni.ui`、`omni.usd`、`omni.warp.core`だけのprobe専用Kit rootを使った。GPU Foundation/resource managerはproviderのため存在するが、Hydra/RTX viewportは起動しない。
- RTX条件はproduction editor rootを使い、Flow ONではtimeline PLAYとnonzero active blockを12/12 processで確認した。
- 測定中のPrim作成・削除・再定義、material binding、asset path、USD revision Setは0。42/42 processでwarmup後と測定後のPrim path集合が一致した。
- source準備、CPU→GPU staging、provider setter、setter完了後から次のrequested RTX frame完了を別timerにした。captureとファイル保存は母集団外である。
- `nvidia-smi`は250 ms周期でprocess全体を観測した。utilizationとmemoryはprovider所有量ではない。

## API、ownership、lifetime

固定runtimeで`set_bytes_data_from_gpu()`は存在し、docstringは次の契約だけを公開する。

```text
set_bytes_data_from_gpu(self, gpu_bytes: int, sizes: List[int],
    format: TextureFormat = RGBA8_UNORM, stride: int = -1,
    strict: bool = False) -> None
Sets byte data from a copy of gpu memory at gpuBytes.
```

GPU baselineは同梱Warp 1.14.0の公開`warp.array`でCUDA device 0 allocationをprobeが所有し、公開`ptr`を渡した。NumPyをaliasするCPU Warp arrayから`warp.copy()`した後、毎回`warp.synchronize_device()`でsource生成完了を保証した。device arrayはprovider callと次のrender updateが完了するまで保持し、providerをdestroyしてから参照を解放した。CPU pointerの偽装、private API、未所有pointerは使っていない。

ただしprovider docstringはCUDA device ordinal、stream、fence、multi-GPU、renderer backendとのinterop条件を規定していない。今回の単一RTX 3090 runtime baselineは安全に完走したが、production ABI/lifetime契約としては未qualifiedである。二重・三重stagingは実施していない。

`get_managed_resource()`はruntimeで存在するが、docstringは戻り型`RpResource`だけで寿命を説明しない。そのため呼び出し、identity比較、Python保持、cacheは行っていない。

## 20本・base+emission変更の比較

| source / 接続条件 | setter p50 | mean | p95 | p99 | max | staging p95 | 次RTX frame p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CPU・未接続・変更 | 1.1600 | 1.2375 | 1.8164 | 2.3136 | 2.7258 | 0 | 対象外 |
| CPU・Mesh接続・RTX描画なし | 1.1964 | 1.2680 | 1.8089 | 2.2916 | 2.3299 | 0 | 対象外 |
| CPU・RTX・Flow OFF | 1.5573 | 1.5865 | 2.1147 | 2.2999 | 2.6253 | 0 | 7.7727 |
| CPU・RTX＋Flow | 10.4631 | 13.6859 | 28.8968 | 31.2646 | 32.1847 | 0 | 32.7710 |
| GPU・RTX・Flow OFF | 0.1142 | 0.1222 | 0.1935 | 0.2332 | 0.2539 | 0.5067 | 8.9804 |
| GPU・RTX＋Flow | 0.1226 | 0.1289 | 0.2021 | 0.2767 | 0.3503 | 1.4223 | 31.4113 |

同じ120×60・2枚変更条件のsource準備p95はCPU-source `0.2708 ms`、GPU-source `0.2868 ms`だった。GPU行のstagingはこの準備とは別に、`warp.copy()`と明示device同期を含む。source生成は28.8968 msのCPU setter tailではない。

CPU RTX＋Flowの2枚変更360 sampleでは、5/16.67/33.33/50 ms超過は`200 / 158 / 1 / 0`。16.67 msの整数倍±8%に入ったのは4 sampleで、周期量子化の有力証拠にはならなかった。GPU RTX＋Flowでは全閾値超過が0だった。

1枚更新はCPU RTX＋Flowでbase p95 `12.3545 ms`、emission p95 `12.8349 ms`、2枚連続は`28.8968 ms`だった。固定内容でもbase `12.6103 ms`、emission `12.4277 ms`、2枚`28.4733 ms`である。実画像変換量よりAPI callごとの同期が支配するという推定を支持する。providerは内容同一を自動no-opにしない。

96×15と120×60の2枚変更p95はCPU RTX＋Flowで`28.6312 / 28.8968 ms`、GPU RTX＋Flowで`0.2008 / 0.2021 ms`だった。11,520 Bから57,600 Bへの5倍増に対してほぼ一定で、今回の範囲で帯域支配は支持されない。

## whole-GPU観測

20本・2枚変更のprocess全体GPU utilization mean中央値 / memory max中央値は、CPU未接続`2.923% / 3,003 MiB`、CPU Mesh接続・描画なし`3.513% / 3,012 MiB`、CPU RTX Flow OFF`13.939% / 3,881 MiB`、CPU RTX＋Flow`48.166% / 5,693 MiB`、GPU-source RTX＋Flow`46.711% / 5,761 MiB`だった。これはprocess全体の粗い観測であり、provider allocation、setter中の瞬間値、GPU-source固有の使用量ではない。

## 原因分類

| 判定 | 観測 | 分類 |
|---|---|---|
| 未接続でもtail stall | p95 1.8164 ms、16.67 ms超0 | 観測されず。provider/resource manager単独は主因候補ではない |
| Mesh接続・RTX描画なし | p95 1.8089 ms、tail 0 | 接続やmaterial参照だけでは悪化しない |
| RTX描画中・Flow OFF | p95 2.1147 ms | 使用中RTX resourceだけによる大tailは観測されない |
| Flow ON | CPU p95 28.8968 ms | Flow GPU競合またはscheduler/interop同期境界の強い候補 |
| GPU-source | setter p95 0.2021 ms、staging 1.4223 ms | CPU-source provider経路が同期setter tailの主因候補 |
| GPU-source後のrender | 次frame p95 31.4113 ms | destination/render/Flow frame待ちは残る。GPU publicationだけでend-to-endは解決しない |
| 固定内容 | 変更内容とほぼ同じ | 画像内容処理ではなくcall固定費または同期の候補 |
| atlas size | 5倍でもp95ほぼ同じ | 57,600 B以下では帯域支配を支持しない |
| 16.67 ms量子化 | 4 / 360 | frame-bound synchronizationの有力証拠には不足 |

### 観測事実

上表のtimer、sample、閾値、byte/API call数、Flow active block、runtime docstring、Warp所有/sync手順、whole-GPU telemetryである。全sampleは`dynamic_texture_boundary_samples.json`に保存する。

### 強い推定

V3T-Cの約35 msは、2回のCPU-source DynamicTextureProvider publication callがFlow実行中に同期する境界で再現した。GPU-sourceでsetter tailが消え、固定/変更とatlasサイズがほぼ同じため、NumPy packやraw memcpy帯域ではない可能性が高い。

### 未確認

同期主体がDynamicTextureProvider実装、renderer resource manager、CUDA/D3D interop、使用中texture fence、Flow schedulerのどれかはprofiler/公開実装証拠がなく未確認である。次requested viewport frame完了をRTX反映のproxyとして測ったが、全sampleのpixel identityをreadbackしてはいない。`get_managed_resource()` identity/lifetime、multi-GPU、非同期stream、二重/三重bufferの安全性も未確認である。

## 判断と次の候補

Phase V3T-Dは測定完了で停止する。production V3、V3T-C consumer、物理、Flow、Point、rigid layout、Mesh/UV/collision、revision/rollback、既定値を変更しない。

GPU-sourceはsetter境界を有意に改善したため、将来の独立Phase候補にはできる。ただし再開条件は、公開APIでdevice/stream/fence/lifetimeをproduction契約として説明できること、または実操作上の支障が確認されることとする。次Phaseを行う場合も、まずsingle-bufferのpixel反映確認、GPU/renderer device一致、stage reload/close/failure、二重buffer lifetime、end-to-end frame pacingを既定OFFでqualifiedし、成功前にV3T-Cを置換しない。

## 最終回帰

- release build: `9.02 s`で成功。
- Phase 0: cold RTX ready `162.1 s`を含めて成功。
- 標準suite: 8 process、`77 / 77`、`417.4 s`で成功。
- V3T-C: 隔離出力でOFF/ON 3組・6 processすべて`status=ok`。wood authority SHA-256、metrics CSV、mass balance、ignition、Resident revision、Flow input/active block、1 render update以内のRTX reflectionの7 gateを再確認した。今回のpublication p95中央値は`33.8377 ms`、CPU-source provider callは`33.0218 ms`で、既存の約35 ms分類と整合した。
- Phase 6DQ: 隔離出力で`11 / 11` gate、revision `710`、active blocks peak `384`、60 frame中58 uniqueを再確認した。既存Phase 6DQ report、設定、開発日誌は書き換えていない。
- 開発日誌: 実ブラウザでV3T-Dカード、1240×688 SVG、共通modalからのV3明示preset動画再生を確認した。
