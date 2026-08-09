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
