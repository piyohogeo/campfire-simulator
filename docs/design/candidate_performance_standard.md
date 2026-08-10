# Phase V3T-MB: Candidate Performance temporary rendering standard

## 決定

Phase V3T-LのCandidate Performanceを、通常起動、benchmark、開発動画、性能probe、回帰試験の暫定レンダリング標準にする。これは58 FPS gate合格を意味しない。Phase V3T-Lのproduction相当Flow＋volume基準は平均visible render counter `47.858 FPS`、`20.90 ms`である。display-present FPSやraw frame pacingとは表現しない。

## 固定設定

normal／benchmark appのstage接続前に次を固定する。

- `/rtx/rendermode="RealTimePathTracing"`（RTX Real-Time 2.0）
- `/rtx/post/aa/op=3`
- `/rtx/post/dlss/execMode=0`（Performance）
- `/rtx/rtpt/maxBounces=2`
- AOは変更せず、実効値は`true`

`run_phase3.ps1`の`Inherit`はこのapp標準を継承する。`AutoBaseline`はDLSS Auto＋maxBounces 4、`CandidateBalanced`はBalanced＋maxBounces 2を独立process比較用に残す。RTX MinimalとAO OFFはproduction候補にしない。

## 実効値

Release build後、normal／benchmarkを別processで起動し、8連続visible frame後に設定を再読取した。両方ともRT2、AA op 3、DLSS Performance、maxBounces 2、AO ON、1280×720、VSync OFF、main／render 120 Hz、present 59 Hzだった。RTX 3090、driver 591.86、Power Limit／enforced Power Limitは210 W。内部レンダリング解像度はKit 110.2の公開ViewportAPI／設定から取得できず、推定しない。

## 回帰と外観

明示V3デモを`RtxVisualPreset=Inherit`で実行し、次を確認した。

- status `ok`、dry／wet mass-balance error `0.0 kg`
- Resident／USD revision 1200、一致gate合格
- Flow active block final 278、peak 305
- V3 processed revision 1200、visual commit 505、texture upload 868、failure 0
- 96×15 atlas、4本のrender log
- 実画面でFlow volumeの炎煙、影、薪surface texture、高温emissionを確認

Performanceでは炎の時間方向ディテールが多少平滑化される。これは既知の許容事項で、Flow欠落とは区別する。既存のCandidate Performance動画はこの判断の目視証拠として再利用し、性能母集団には含めない。

## 非変更と制約

wood authority、Flow入力、Point／Sphere Emitter、collision、rigid layout、checkpoint、serialization、AO、Power Limitは変更しない。この文書で記録したPhase V3T-MB時点ではV3既定OFFだった。Phase V3T-P以降のproduction既定ONは別のcorrectness／lifecycle／30 FPS gateを通した後続判断であり、この過去測定の意味を変更しない。V3T-M以降の主要計測はCandidate Performanceを使い、各Phaseで代表条件のAutoBaselineも別processで測る。

最終回帰はRelease build 8.21秒、Phase 0 RTX exit 0、標準suite 8/8 process・77/77 test（354.5秒）が合格した。

## Phase V3T-N以降の運用予算

Candidate Performanceの採用後、今後の通常目標は`45 FPS / 22.222 ms`、最低ラインは`30 FPS / 33.333 ms`とする。`60 FPS / 16.667 ms`は軽量sceneの理想値で、全sceneの絶対条件ではない。production相当Flow＋volumeの既知値`47.858 FPS / 20.90 ms`からの推定余裕は45 FPS枠へ`1.322 ms`、30 FPS枠へ`12.433 ms`である。これは平均visible counterの差であり、display-presentやraw latencyの余裕ではない。詳細は`frame_budget_policy.md`。
