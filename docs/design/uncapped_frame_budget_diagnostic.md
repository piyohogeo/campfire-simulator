# Phase V3T-O: capped / 240 Hz frame-budget diagnostic

## 結論

Candidate Performance、1280×720、Power Limit 210 Wで、production-cappedの既存3-run値と、main／rendering／viewport tickの上限を別processで240 Hzへ上げた新規3-run値を比較した。静的3 sceneはproductionの120 Hz rendering ceilingに当たっていた。production相当Flow＋volumeは240 Hz診断でも`50.696 FPS / 19.725 ms`で、`47.858 / 20.895 ms`からの改善は約5.9%に留まり、120 Hz ceilingではなくFlow／RTX workload側である。

production app、production rate、present、VSync、Power Limit、camera、stage、Flow、V3、wood authority、Emitter、collision、checkpoint、serializationは変更していない。Phase V3T-Mで保留したpartial Flow topologyは実行していない。

## 測定契約

- capped: Phase V3T-L Candidate Performance正式3-runを再利用。main 120 Hz、rendering 120 Hz、present 59 Hz、VSync OFF。
- 240 Hz診断: 隔離processだけでmain 240 Hz、rendering 240 Hz、viewport tick 240 Hzを起動前に要求。present 59 Hz、VSync OFFは変更しない。
- Flow volumeはtimeline／Flow起動後にmainが60 Hzへ再設定された。liveに押し戻さず、rendering／viewport tick 240 Hz、present 59 Hzの実効値を記録した。
- 既存visible viewportの`frame_info.frame_number`差÷wall time。display-present FPSやraw frame latencyではない。
- GPU値は測定区間のwhole-GPU `nvidia-smi`。GPU utilizationだけをFPS代用にしない。
- 追加RenderProduct、HydraTexture、capture、encode、測定中のPrim／material／asset変更なし。
- upload無効、`preserveDump=true`、run固有dump、fatal-token fail-fastを使用。

## 結果

| Scene | production capped | 240 Hz diagnostic | 240 Hz GPU | Power | Graphics clock |
|---|---:|---:|---:|---:|---:|
| floor＋stones＋lights | 116.708 FPS / 8.568 ms | 169.892 / 5.886 ms | 97.632% | 209.447 W | 1554.868 MHz |
| Cylinder 20 | 116.697 / 8.569 ms | 168.931 / 5.920 ms | 98.982% | 209.402 W | 1554.474 MHz |
| V3 Mesh 20＋fixed texture | 116.764 / 8.564 ms | 166.377 / 6.010 ms | 98.798% | 209.374 W | 1560.658 MHz |
| production相当Flow＋volume | 47.858 / 20.895 ms | 50.696 / 19.725 ms | 77.611% | 208.468 W | 1800.797 MHz |

静的3条件はcapped値が120 Hzの約97%へ集中し、240 Hzではいずれも240へ届かずGPU utilization約98～99%になった。production ceilingがheadroomを隠していたと判断する。一方Flowはcappedでも120から十分離れ、240 Hzによる増分は`2.838 FPS`である。

GPU render timeは確認済みのKit 110.2公開ViewportAPI／`omni.stats`から取得できず未計測である。追加描画経路による代用は行わない。

## preflightの扱い

正式前の失敗・確認runはすべて除外した。

- 初回: 新probeのscripts import path不足。probe開始前の`ModuleNotFoundError`で、手動停止した非正式run。native crashではない。
- 2回目: main 240 Hzに対しrendering／viewport tickが120 Hzのままでgate拒否。
- rate gate: viewport tickも240 Hzへ設定し、単一静的sceneで3値一致を確認。
- scene preflight: Cylinder、V3 Mesh、Flowを各1回。Flow mainが60 Hzへ再設定される実効境界を確認し、正式契約へ反映。

## フレーム予算

通常判断は引き続きproduction-cappedの`47.858 FPS / 20.90 ms`を使う。45 FPS枠へ`1.322 ms`、30 FPS枠へ`12.433 ms`の平均visible-counter上の推定余裕がある。240 Hz Flow値を通常余裕へ置き換えない。

## 安全性と次

正式12 processはnormal exit、fatal 0、dump 0、automatic upload attempt 0。Flow active blockを含む既存production相当stageだけを用い、partial topologyを再試行していない。

現時点のuncapped基準を確立したため、常時実行は不要である。大きな描画変更や最適化後に同runnerを再利用する。次は既存ロードマップへ戻り、Phase 6DQが指定する任意回転済み薪のnormal-app起動、停止中transform refresh、stage recoveryを独立Phaseとして検証する。

