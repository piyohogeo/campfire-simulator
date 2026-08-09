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
