# Phase V3T-K: RTX stage／AA cost isolation

## 結論

Flow OFF時の約32 FPSは、V3 render Meshや未接続`dynamic://` textureだけで発生しているのではない。固定1280×720、RTX 3090、Power Limit 210 W（既定350 Wの60%）、DLSS Autoの3独立runでは、次の負荷が累積した。

1. empty RTX `101.523 FPS`から地面＋石＋ライトで`54.939 FPS`
2. 薪20本で`46.017 FPS`
3. timeline PLAY／PhysX更新で`44.775`から`36.229 FPS`
4. Flow subtreeをauthorし、Simulate／Render／Offscreen、Emitter、layer Flow settings、runtime global Flowを全てOFFにすると`44.247 FPS`
5. global Flow／EmitterだけOFFでsubtree／layer settingsをactiveのままにすると`31.483 FPS`
6. Flow simulationをONにすると`24.524 FPS`

Cylinder 20本とV3 Mesh 20本の差は`+0.119 FPS`、固定textureからProviderなし`dynamic://`への差は`-0.755 FPS`だった。V3 Meshと未接続dynamic URIはこの条件の主因ではない。productionコード、production設定、wood authority、Flow入力、Emitter、collision、rigid layout、checkpoint、serialization、V3既定OFFは変更していない。

## 測定契約

- 基準HEAD: `88136a2`（Phase V3T-J fixture UI suppressionまでのclean baseline）
- Kit 110.2、Flow 110.0.0、RTX Real-Time 2.0（runtime値`RealTimePathTracing`）、RTX 3090
- output 1280×720、同一camera、Power Limit 210 W固定。100%比較は行っていない
- 既存visible viewportの公開`ViewportAPI.frame_info`／`fps`だけを使用
- 追加RenderProduct、HydraTexture、capture、encode、測定中のPrim変更、Material rebind、asset path変更なし
- 各stageは接続前に構築・保存し、別processで測定
- 静止stageでも継続render throughputを測るため、隔離process内だけ`/rtx/ecoMode/enabled=false`を適用。persistent／production設定へ保存しない
- warmup 5秒後に実効Flow／AA／Eco Mode値を再適用・再読取し、8秒を正式母集団とした
- stage 13条件×3 run＝39 process、AA 3条件×3 run＝9 process。run順はrotateした
- `IRenderSettings::getRenderSettings failed getting a stage-id`、Traceback、CUDA illegal address、device lost、invalid pointerは1件でも拒否。採用48 processでは全て0、exit code 0
- `nvidia-smi`を250 ms間隔で取得。GPU全体の値であり、個別pass所有量とは主張しない

最初の4秒smokeはEco Mode下でvisible frameが進まなかったため不採用とした。Flow exact比較の初回も、extension遅延初期化がglobal Flow設定を上書きしたため実効値gateで拒否した。どちらも正式母集団へ再利用していない。

## RTX／AA実効値監査

Auto stage matrixの主な実効値は次のとおりだった。

| 項目 | 実効値 |
|---|---:|
| `/rtx/post/aa/op` | `3` |
| `/rtx/post/dlss/execMode` | `3`（Auto） |
| renderer mode | `RealTimePathTracing` |
| direct-light samples per pixel | `2` |
| dome-light sample count | `2` |
| shadows | `true` |
| reflection bounces | `1` |
| refraction bounces | `6` |
| indirect diffuse bounces | `2` |
| realtime OptiX denoiser | `false` |
| main／render loop cap | `120 Hz` |
| present loop cap | `59 Hz` |
| app／renderer VSync | `false` |
| viewport tick rate | `120 Hz` |

`/rtx/pathtracing/dlss/enabled=false`も見えるが、これはRTX Real-Timeのpost-AA設定ではなく混同しない。`/rtx/pathtracing/dynamicResolution/*`もPath Tracing側であり、Real-Timeの内部解像度証拠には使わない。`/rtx/post/dlss/manualScaling=1.0`、`/rtx/index/resolutionScale=100`は取得できたが、公開APIから実際の内部render width／heightへ対応付けられないため、内部レンダリング解像度は取得不可とした。Ray Reconstructionの公開runtime値も確認できなかった。

`/rtx-transient/dlssg/enabled=true`は設定辞書に存在したが、本PhaseはFrame Generationを要求・有効化しておらず、RTX 3090上の実動作証拠として扱わない。

## 段階比較

| 条件 | mean FPS | SD | GPU util | power | stage要素 |
|---|---:|---:|---:|---:|---|
| empty RTX | 101.523 | 1.150 | 98.5% | 209.6 W | Cameraのみ |
| ground＋stones、lightなし | 57.471 | 0.231 | 98.2% | 209.4 W | 地面＋石 |
| ground＋stones＋lights | 54.939 | 0.116 | 98.7% | 209.5 W | light 3 |
| Cylinder 20、単色 | 46.017 | 0.585 | 97.0% | 209.2 W | implicit Cylinder 20 |
| V3 Mesh 20、単色 | 46.136 | 0.193 | 100.0% | 209.6 W | Mesh 20、14,880 triangles |
| V3 Mesh＋固定texture | 45.536 | 0.073 | 99.2% | 209.6 W | base＋emission asset |
| V3 Material＋未接続dynamic URI | 44.781 | 0.073 | 100.0% | 209.6 W | dynamic URI 2、Provider 0 |
| 上記＋RigidBody、STOP | 44.775 | 0.144 | 98.5% | 209.5 W | RigidBody 20 |
| 上記＋timeline PLAY | 36.229 | 0.041 | 77.5% | 208.9 W | PhysX更新あり |
| Flow author済み、明示all-OFF | 44.247 | 0.130 | 97.9% | 209.3 W | Simulate／Render inactive、active block 0 |
| global／Emitter OFF、subtree／layer settings active | 31.483 | 0.118 | 81.6% | 208.8 W | Flow Prim 17、active block 0 |
| Flow simulationのみ | 24.524 | 0.045 | 99.8% | 209.2 W | active block 184 |
| Flow simulation＋volume | 24.517 | 0.053 | 99.6% | 209.2 W | active block 180 |

最初の大きな低下はempty RTXから地面＋石（`-44.052 FPS`、`-43.39%`）である。地面／石はpixel coverage、geometry、RTX shadingを一括で増やすため、個別passまでは分離していない。light追加は`-2.532 FPS`。影OFF preflightは`55.634 FPS`、影ONは`55.799 FPS`で支配的ではなかった。

Cylinder 20本からV3 Meshへの差は測定ばらつき内だった。単色V3 Meshから固定textureは`-0.600 FPS`、固定textureから未接続dynamic URIは`-0.755 FPS`。dynamic URIに関するWarning／Errorは0件だったが、内部lookupが全くないとは断定しない。

RigidBodyをauthorしてtimelineを停止した条件は変化しなかった。一方、PLAYで`-8.546 FPS`（`-19.09%`）。GPU utilが低下しているため、単純なpixel shader増加よりPhysX、transform／TLAS更新、Kit同期の候補が強いが、個別内訳は未確認である。

Flow比較は二段階に分けた。厳密all-OFFではFlow subtreeをUSDへauthorしたままSimulate／Render／Offscreenをinactiveにし、Emitter、root layerの全`rtx:flow:*` renderSettings、runtime global Flowをfalseにした。この条件は`44.247 FPS`だった。同じ構築sceneでglobal Flow／EmitterだけをOFFにし、subtree／layer settingsをactiveのまま残すと`31.483 FPS`へ`-12.764 FPS`（`-28.85%`）低下した。約32 FPSは「Flow Primが存在するだけ」ではなく、OFF時にもactiveな統合境界で再現する。

Flow Primなしのtimeline PLAYは`36.229 FPS`で、明示all-OFF Flow sceneより遅かった。active prim pathはFlow Xform＋disabled Emitter以外ほぼ同じだが、root layer metadata、Flow extension登録、timeline進行率または物理状態の差を分離できていないため、この`+8.017 FPS`をFlowによる改善とは扱わない。simulation ONでglobal-OFF／active-subtreeからさらに`-6.959 FPS`、volume ON追加は`-0.007 FPS`だった。

## AA／DLSS比較

約32 FPSを再現する「global Flow／Emitter OFF、subtree／layer settings active」sceneを代表条件にした。

| mode | mean FPS | SD | 各run |
|---|---:|---:|---|
| Performance | 59.812 | 0.121 | 59.913 / 59.678 / 59.844 |
| Auto | 31.156 | 0.003 | 31.159 / 31.155 / 31.154 |
| DLAA | 31.130 | 0.089 | 31.214 / 31.138 / 31.037 |

Balanced `52.623 FPS`、Quality `51.062 FPS`は各1回preflightでPerformanceとAutoの間だったため正式3 runへ進めなかった。Kit 110.2の固定RTX UIがAAなしを正式選択肢として公開していないため、AAなしは実行していない。要求したmodeはmeasurement直前の`aa/op=3`と`execMode=0/3/4`で一致を確認した。

Performanceは約60 FPSまで改善するが、3 runすべて60未満で、厳密な60 FPS gateは満たさない。この比較内で60 FPSを満たす「最も高品質な設定」は存在しない。最も近い設定はDLSS Performanceである。AutoとDLAAのFPSはほぼ同じだが、内部解像度が取得できないためAutoがDLAAそのものだとは断定しない。

## 観測事実・推論・未確認

観測事実:

- V3 Mesh形状はCylinderより遅くなっていない
- 未接続dynamic URIの追加差は小さく、log warning/errorはない
- timeline STOPからPLAYで約19%低下
- 明示all-OFFからglobal-OFF／active-subtreeで約29%低下
- AutoからPerformanceで約92%改善
- 全formal runはPower Limit 210 W、fatal log 0

強い推論:

- 約32 FPSはglobal Flow／EmitterをOFFにしてもactive Simulate／Render Primとlayer Flow settingsが残る境界で再現する
- V3 MeshやProvider不在をproductionの主因として修正する根拠はない
- Autoの高負荷挙動は内部AA／upscaling選択に依存する可能性が高い

未確認:

- Real-Time内部render resolution
- Ray Reconstructionのruntime状態
- timeline PLAY時のPhysX、transform、TLAS、scheduler別内訳
- global Flow OFFでも残るRTX／Flow passの正体
- display-present FPS、raw frame p95/p99、1% low

段階比較とAA比較だけで主要境界が明確になったため、本PhaseではGPU profilerを追加しなかった。profiler負荷を通常FPS母集団に混ぜていない。

## 判断

production変更は行わない。V3既定OFF、Sphere production既定、Point／rigid layout既定OFFを維持する。次に修正候補として扱う価値があるのは、Flow OFF時にもSimulate／Render Primとlayer Flow settingsをactiveのまま残す経路である。まず別Phaseの代表scene profilerまたはFlow stage-authoring auditで、無効時にも登録・RTX pass・stage observer更新が残るかを確認する。

AAについては、DLSS Performanceを明示的な低負荷デモ候補として提案できるが、production既定は変更しない。内部解像度と画質の実測がないため「高品質60 FPS」またはAutoの不具合とはまだ判断しない。

機械可読結果は`docs/devlog/assets/phasev3tk/rtx_stage_cost_report.json`、全採用run／preflight summaryは`rtx_stage_cost_samples.json`、図は`rtx_stage_cost_report.svg`に保存した。

最終状態で標準suiteを再実行し、8/8 process、77/77 testが合格した。py_compile、PowerShell parse、JSON／SVG、`git diff --check`を含む最終commandのwall timeは`352.9 s`で、suite単独時間とは扱わない。production module、app dependency、起動設定を変更していないため、release buildとPhase 0の再生成はこの測定Phaseの必須対象外とした。
