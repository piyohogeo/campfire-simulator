# Wood visual V3 texture transport optimization

## Phase V3T-A: compact one-texel atlas

### 判断

Phase V3M-Cの4×4 pixel／surface cellを、1 pixel／surface cellへ置換する。Kit 110.2／RTX 3090で1×1、2×2、4×4を同一checker、同一camera、同一Meshで比較し、1×1と2×2の画像差は8-bit RGBでmean `0.1008`、p95 `1`、max `9`だった。side、両cap、seam、side/cap overlap、移動、回転、stage reload、4本、20本の全gate `12 / 12`に合格したため、padding／gutterは不要と判断した。

### 固定descriptor

atlas descriptorはstage接続前にrender log数から一度だけ作り、session中は変更しない。

| render log | tile | atlas | 2×RGBA8 |
| ---: | ---: | ---: | ---: |
| 4 | 4×1 | 96×15 | 11,520 B |
| 20 | 5×4 | 120×60 | 57,600 B |

1 tileは24×15 texelで、1 texelが1つの`log_id + local_surface_index`を表す。全face vertexの`st`を同じtexel中心へ固定し、`UsdUVTexture`のmin／mag filterは`nearest`、wrapは`clamp`とする。runtimeではUV、topology、descriptor、dynamic URIを変更しない。stage reloadではUSDに保存された同じdescriptorを検証し、異なるdescriptorは拒否する。動的resizeは行わない。

`modeled log`と`render log`は別である。Phase 3のrender logは4本、V2 payloadのmodeled logはLog_00／Log_01の2本で、payloadは各logの固定atlas slotへ書く。残りのrender logはneutral woodで埋め、架空の燃焼状態を与えない。

### 機械的同値性

- 4本1,440 sample、20本7,200 sampleはすべてuniqueなtexel centerだった。
- surface IDを符号化したatlas bytesを全sampleで読み戻し、期待値と完全一致した。
- Meshは384 face／360 unique stateを維持し、sideとcapの24 overlap faceは同じstateを読む。
- transform／reload前後のpoints、indices、surface identity、UV digestは一致した。
- 管理対象`/World/Logs`と`/World/Looks`のPrim path集合は不変だった。
- V3M-B `10 / 10`、V3M-C `17 / 17`をcompact atlasで再実行して合格した。

### 性能

20本・7,200 state・100 post-warmup sampleのisolated V3M-C回帰値:

| 区間 | V3M-C p95 | compact p95 |
| --- | ---: | ---: |
| beauty pack | 2.7769 ms | 1.8627 ms |
| CPU upload | 2.4774 ms | 2.2883 ms |
| revision commit | 1.0142 ms | 1.1126 ms |
| publication total | 5.4135 ms | 4.8254 ms |

転送量は`921,600 → 57,600 B/revision`で16分の1になった。一方、CPU upload p95は小幅改善に留まり、publicationは参考目標`1.0 ms`を満たさない。compact化だけで実アプリの約60 ms stallが解消したとは判定しない。

### lifecycleと非変更範囲

V3のowner thread、timeline、stale拒否、同一revision no-op、2 atlas成功後のrevision commit、failure recovery、reload完全再発行、close、wood／Flow／Pointをrollbackしない契約は維持する。V3は既定OFFのまま。

Mesh collider、points変形、収縮、亀裂、欠損、V4、Phase 6DM、Point Emitter契約、木材権威状態、Flowは変更しない。

### 次の限定作業

Phase V3T-BではV2 payloadを維持したまま、beauty量子化をnative bulk packへ移し、session所有bufferの再利用とbase／emission個別skipを評価する。V3T-A時点ではNumPy beauty mappingと毎revision 2 uploadを維持している。

機械レポート: [compact_atlas_report.json](../devlog/assets/phasev3ta/compact_atlas_report.json)、[RTX probe](../devlog/assets/phasev3ta/compact_atlas_probe.json)。

## Phase V3T-B: native beauty packとchange-aware publication

### C ABIとbuffer ownership

V2の`ImmutableWoodVisualSurfacePayload`は変更しない。新しいadditive C ABIはtemperature、moisture、char、ashのfloat32配列、stable render slot、compact atlas descriptorを受け、base RGB＋roughness Aとemission RGB＋opaque Aの最終RGBA8 layoutへ直接書く。入力は呼出し中だけ借用し、C++はpointerを保持しない。出力はconsumer sessionが所有する連続NumPy `uint8` work buffer 2枚で、render slot配列と合わせて3 allocationをsession中再利用する。成功済み表示は別のpreallocated committed buffer 2枚へ`copyto`し、failure時のvisual-only recoveryとprovider入力寿命を維持する。

全計算はV2 float32入力とNumPy参照の演算順に合わせ、RGBA8の全texelを独立比較した。4本1,440 cellと20本7,200 cellを各105 packし、base/emissionとも完全一致した。surface-cell値を入れ替えた場合はatlas bytesも変わり、平均値ではpermutationを隠していない。negative／non-finite入力拒否、owner thread、stale拒否、retry、reload完全再発行も維持する。

### revisionとskip semantics

`campfire:committedRevision`は「現在表示されているatlasが対応する最後のpayload revision」とする。consumer statusは別に`processed_revision`を公開し、量子化後のbase/emissionがともに同じ場合はprocessedだけを進め、texture uploadもUSD `Set()`も行わない。片方だけ変化した場合はそのatlasだけuploadし、両方同じなら0 upload／0 Setである。reload時は最新processed payloadを両atlasへ強制再発行し、表示revisionを最新値へ揃える。failureではprocessedもdisplayedも進めず、wood authority、Flow、Pointはrollbackしない。

### adaptive schedule

Resident sourceは5 Hzのまま変えない。最初のpublish、reload、明示force、25 K以上の変化、650／800／1000 K境界横断は5 Hz候補とする。通常の小変化は0.4 s間隔へ間引く。5 Hz sourceの離散tick上で500 ms遅延上限を守るため、有効頻度は2.5 Hzであり、厳密な2.0 Hzではない。probeでは26 source updateに対し13 publish、最大間隔0.4 s、急熱は0.2 sでpublishした。

### 実測と判断

Kit/RTX probeは`17 / 17`、変更後V3M-C regressionは`17 / 17`、標準suiteは8 process・`74 / 74`（`359.8 s`）、release buildとPhase 0 RTXも合格した。20本・100 post-warmup sampleの単一runではnative pack p95 `2.7026 ms`に対しNumPy参照は`2.3398 ms`で、native化単独は高速化にならなかった。changing publicationはpack `2.2045 ms`、CPU upload `2.3915 ms`、revision commit `0.7672 ms`、total `4.7540 ms` p95で、1.0 ms目標を満たさない。一方、105 unchanged quantized revisionsはupload `0`、USD Set `0`で、base-only／emission-onlyは各28,800 Bだけを転送した。camera capture直前はschedulerを迂回せず、同じprocessed revisionでも両atlasを強制再発行する。

このPhaseではnative boundary、固定buffer、個別skipを機能qualifiedとするが、性能採用は判断しない。単一probeのnative p95悪化と依然残るCPU upload stallを保留し、V3T-CのOFF／ON交互3組と実アプリframe pacingで採否を決める。V3は既定OFF、Cylinder collider、V0/V1 fallback、Flow／Point／authority契約は不変である。

機械レポート: [native_beauty_report.json](../devlog/assets/phasev3tb/native_beauty_report.json)、[Kit/RTX probe](../devlog/assets/phasev3tb/native_beauty_probe.json)。

## Phase V3T-C: 実アプリ統合計測と利用境界

### 交互計測

Resident adapter、handle cache、lightweight commit、unchanged derived skip、Resident native backend、render hierarchy、Flow、RTX、camera、warmup、1280×720 captureを固定し、pair 1をOFF→ON、pair 2をON→OFF、pair 3をOFF→ONの順で独立process実行した。各runは240秒・1,200 stepの同じPhase 3で、固定時刻2枚を撮影した。update frame、visual publication、CPU upload、GPU、authorityを同じ`summary.json`から集計した。

| 指標（3 run中央値または合計） | V3 OFF | V3 ON |
| --- | ---: | ---: |
| update frame p50 | 6.4895 ms | 4.9647 ms |
| update frame p95 | 7.9833 ms | 6.5593 ms |
| update frame max | 9.2552 ms | 9.4021 ms |
| 16.67 / 33.33 / 50 ms超過 | 0 / 0 / 0 | 0 / 0 / 0 |
| GPU utilization mean | 19.870% | 35.750% |
| GPU memory max | 7,731 MiB | 7,793 MiB |
| visual publication p50 / p95 / max | — | 2.5241 / 36.1233 / 79.2889 ms |
| CPU upload p50 / p95 / max | — | 1.7373 / 35.4457 / 78.6662 ms |

V3 ONのupdate-frame p95はOFFより`1.4240 ms`低く、この交互runではframe pacing悪化は観測されなかった。ただしvisual publication p95の`36.1233 ms`は消えておらず、`35.4457 ms`がpublic CPU texture uploadである。uploadは`next_update_async`前に同期実行されるため、update-frame区間だけを見てstall解消と判断してはならない。3 ON runの転送合計は`14,999,040 B`、1 runあたり`4,999,680 B`だった。

provider upload完了から次のKit/RTX update完了まではp95中央値`44.8087 ms`、最大render update数`1`で、200 ms gateを満たした。これはpixelの全frame readbackではなく、同じowner threadで完了したpublicationが次のrenderer updateへ渡った境界の計測である。動画capture runは60回の強制再発行を含むためperformance母集団から外し、外観trajectoryの根拠だけに使用する。

最終回帰ではrelease build、Phase 0 RTX、Phase 2、Phase 3 V0 OFF/ON、V0 `13 / 13`、V1 `8 / 8`、V2 `8 / 8`、V3M-A `6 / 6`、V3M-B `10 / 10`、V3M-C `17 / 17`を確認した。旧Cylinder-only V3 probeはUV制約を示す既知の`6 / 9`非適格のままであり、Mesh経路への退行ではない。標準suiteは8 process・`74 / 74`件を`365.7 s`で完了した。

### 正しさと採否

6 runすべてでdry/wet authority SHA-256、metrics CSV SHA-256、mass balance error `0`、ignition `66.2 / 166.4 s`、Resident revision `1200`、Flow peak fuel `1.0`が一致し、Flow active blockは全runでnonzeroだった。20本・7,200 surface identity、reload完全再発行、visual-only failure recoveryはV3M-C `17 / 17`で再確認する。modeled logは2本、残り2本のrender logはneutral woodのままで、架空状態を与えない。

機能・正しさ、統合frame pacing、RTX反映境界は合格したが、20本isolated publication p95 `4.7540 ms`は参照目標`1.0 ms`を満たさない。したがって通常appとbenchmark appの`woodVisualV3Enabled`は`false`を維持し、標準デモ既定ONにはしない。一方、最適化済みV3を明示的に試せる単一command presetを提供する。

```powershell
.\scripts\run_visual_v3_demo.ps1
.\scripts\run_visual_v3_demo.ps1 -CaptureVideo
```

このpresetはrender hierarchy、Resident adapter、handle cache、lightweight commit、unchanged skip、Resident native backend、V3を一括で有効化する。Point application、V0、V1との競合は既存validationでfail closedとなる。従来Cylinder-only表示は設定OFFで選択でき、safe fallbackを削除しない。native libraryは同じcommand内でrelease buildする。

機械レポート: [integrated_report.json](../devlog/assets/phasev3tc/integrated_report.json)、[matrix manifest](../devlog/assets/phasev3tc/matrix_manifest.json)、[actual trajectory summary](../devlog/assets/phasev3tc/visual_v3_demo_summary.json)。
