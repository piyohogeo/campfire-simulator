# Wood visual V3 Mesh integration

## 結論

Phase V3M-C は、V2 の `ImmutableWoodVisualSurfacePayload` を、V3M-B の stable render-only Mesh へ表示する経路として機能上は成立した。ただし 20 本・7,200 surface cell の表示発行 p95 は `5.4135 ms` で、参考目標 `1.0 ms` を満たさない。このため `/exts/campfire.app/woodVisualV3Enabled` は既定 `false` のままとする。

この判断は、機能の不成立ではなく性能ゲート未達によるもの。17/17 の実機ゲート、73/73 の回帰テスト、Phase 3 の authority SHA-256 同値性は合格している。

## 表示階層

V3M-B で導入した階層を変更しない。

```text
/World/Logs/Log_00                 Xform + RigidBody + Mass
├── Collider                       invisible UsdGeom.Cylinder + Collision
└── RenderSurface                  UV付き UsdGeom.Mesh、Physics APIなし
```

- root transform、mass、density、damping は物理の契約であり表示consumerは書き換えない。
- Collider は従来と同じ analytic Cylinder である。
- RenderSurface は 384 faces、360 stable surface identities を持つ。points、indices、UV、atlas slot は実行中に変更しない。
- OFF 時は従来の Cylinder-only stageを維持する。V3 は Phase 3、render hierarchy、Resident adapter、native backend が同時に明示された場合だけ起動する。
- Resident Point application、V0、V1 と同時に有効化した場合は stage 接続前に fail closed する。

## texture構成

1 本 1 texture、1 cell 1 Prim、cell単位 USD `Set()` は使わない。20本分を次の固定resourceへまとめる。

| resource | 内容 | format | size |
|---|---|---|---|
| `dynamic://campfire_wood_visual_v3_base` | base color RGB、roughness A | RGBA8 UNORM | 480×240 |
| `dynamic://campfire_wood_visual_v3_emission` | emission RGB | RGBA8 UNORM | 480×240 |

1 revision は2回のraw CPU uploadと、`/World/Looks/WoodVisualV3.campfire:committedRevision`への1回のUSD `Set()`で完了する。asset path、material binding、Prim構造は変更しない。1 revision当たりの転送量は `921,600 bytes`。

単一RGBA state atlasは不採用とした。現在の `UsdPreviewSurface` だけでは moisture、char、ash、temperature の非線形なbeauty mappingを表現できないためである。未確認のMDL APIを大規模に導入せず、Kit 110で実測できた最小構成として2枚のbeauty atlasを選んだ。RGBA16Fは必要な視覚差に対して転送量が増えるため採用していない。

## V2 payloadから外観への写像

入力順序は `log_id + local_surface_index`、1本360要素で固定する。NumPy viewをV2 immutable bytes上に作り、7,200 cellをPython loopで巡回せず一括変換する。

- moisture: dry woodから暗いwet brownへ補間し、roughnessを下げる。
- char: blackへ補間し、roughnessを上げる。
- ash: light greyへ補間し、roughnessをさらに上げる。
- `< 650 K`: emissionなし。
- `650–800 K`: dark redからred。
- `800–1000 K`: redからorange。
- `>= 1000 K`: orangeからyellow-white。
- ashが多いcellではemissionを弱める。

この写像はdisplay-onlyであり、木材の権威状態へ値を戻さない。未モデル化の薪slotはneutral dry woodで埋める。実際のPhase 3ではLog_00とLog_01だけがモデル化され、他の薪がneutral表示のままなのは意図した挙動である。

## revisionと失敗処理

`WoodVisualV3Consumer` はowner thread上のbest-effort observerである。

- timeline start前、stop後、close後のpublishを拒否する。
- 同じrevisionはupload 0、USD Set 0の完全no-op。
- 古いrevisionはupload前に拒否する。
- payload全体とlog順を検証してからpack/uploadする。
- baseとemissionのupload成功後にrevisionをcommitする。
- 途中失敗時は最後に成功した2 atlasとrevisionを再発行する。wood step、Flow publication、Point publicationはrollbackしない。
- stage reloadではproviderを破棄・再取得し、最新immutable payloadを強制再発行する。
- closeでnotice registrationとproviderを解放する。

実機failure injectionではbase upload後の失敗から前revisionへ復帰し、その後の同一payload retryが成功した。管理対象 `/World/Logs` と `/World/Looks/WoodVisualV3` にはlive Prim追加・削除がなく、全20 Meshのtopology digestはreload後も一致した。viewportがCamera配下へ作る非管理helper 2 Primはレポートで分離している。

## 実測

Flow 110.0.0、Kit 110.2、RTX 3090、20本×360 = 7,200 surface cell、100 post-warmup sample。

| 区間 | mean | p95 | max |
|---|---:|---:|---:|
| V2 native extraction total | 0.5666 ms | 0.7880 ms | 1.0457 ms |
| beauty atlas pack | 1.5928 ms | 2.7769 ms | 2.8857 ms |
| raw CPU texture upload | 1.7216 ms | 2.4774 ms | 3.2631 ms |
| revision commit | 0.6132 ms | 1.0142 ms | 1.2478 ms |
| visual publication total | 3.9886 ms | 5.4135 ms | 6.1078 ms |

最初の可視更新はprobe frame 2で観測した。ただし各file captureは2 completion frameを待つため、これは厳密なGPU fenceではなく上限観測である。stage reload後の初回再発行は `5.9032 ms`。

whole-GPU `nvidia-smi` 250 ms samplingは96 samples、最大utilization 99%、memory 2,970–5,725 MiBだった。この差分にはRTX初期化・viewport・他resourceが含まれ、DynamicTextureProvider単体のGPU allocationとは扱わない。V2境界に所有権のある公開GPU pointer sourceがないためGPU uploadも未qualifiedである。

実燃焼runは2本、1,200 revision、2,400 uploads、1,200 revision Sets、`1,105,920,000 bytes`を発行した。capture/Flowと同時実行したpublication p95は`59.6170 ms`まで増え、CPU uploadが支配した。この値は20本isolated probeと測定条件が異なり、採用判断にはより厳しい実アプリ側の制約として残す。

## 物理・Flow回帰

V3 OFF/ONの現在コードによるpaired Resident-native Phase 3で次を確認した。

- dry authority SHA-256 exact match: `0dec57f3…be10`
- wet authority SHA-256 exact match: `148585f8…20c9`
- ignition: dry `66.2 s`、wet `166.4 s`
- mass balance error: dry/wetとも`0.0 kg`
- peak Flow fuel: OFF/ONとも`1.0`
- Resident revision: OFF/ONとも`1200`
- Flow active blocks: OFF peak 148、ON peak 394で双方nonzero

Flow active block数の完全一致は主張しない。dynamic textureのCPU stallがwall-frame pacingを変え、Flow fieldの進み方に差が出るためである。木材authorityとpublication revisionは完全一致している。

## 停止点と次の選択肢

V3M-Cで停止する。production既定ON、旧Cylinder-only経路削除、V0/V1削除、Mesh collider、points変形、収縮、ひび、崩落、欠損、V4、Phase 6DM再開は含めない。

次に検討できるのは、承認後の表示transport最適化だけである。

1. 4×4 cellの全pixel展開を避けるnative beauty pack、または小さい論理atlasをRTX側nearest samplingで使えるか確認する。
2. raw CPU uploadの同期・resource ownershipを再調査し、公開APIで安全なdouble bufferまたはGPU upload sourceを所有できるか確認する。
3. revision USD Setを表示通知用に残す必要があるか、consumer可視性とreload診断を維持したまま切り離して測る。
4. production Phase 3でモデル化された2本が上段のneutral薪に隠れるため、契約を変えない専用デモcamera/layoutを別途用意する。

参考資料: [機械判定レポート](../devlog/assets/phasev3mc/wood_visual_v3_report.json)、[実機probe](../devlog/assets/phasev3mc/dynamic_mesh_probe.json)、[性能図](../devlog/assets/phasev3mc/wood_visual_v3_performance.svg)。
