# Phase V3T-N: rendering frame-budget policy

## 決定

今後の通常起動、開発動画、性能probe、回帰試験はCandidate Performanceを暫定レンダリング標準とする。通常の目標は`45 FPS / 22.222 ms`、最低ラインは`30 FPS / 33.333 ms`とする。`60 FPS / 16.667 ms`は軽量sceneの理想値であり、Flow volumeを含む全sceneの絶対条件にはしない。

この運用基準はPhase V3T-L以前の58/60 FPS gateや測定結果を遡及変更しない。過去gateは当時の比較判定として保持し、今後の機能予算はFPSとframe timeの両方で管理する。

## 現在の予算

Candidate Performance＋production相当Flow volumeの既知基準は平均visible render counter `47.858 FPS / 20.90 ms`である。

- 45 FPS予算までの推定余裕: `22.222 - 20.90 = 1.322 ms`
- 30 FPS予算までの推定余裕: `33.333 - 20.90 = 12.433 ms`

これは平均visible render counterから導いた静的な差であり、display-present FPS、raw frame latency、p95/p99、1% lowの余裕ではない。内部render resolutionとGPU render timeもKit 110.2の確認済み公開境界からは取得できていない。

## 将来機能へ残す予算

薪の形状変化、炎由来の発光照明、表面表現を追加できるよう、高価なobserver更新は描画フレームから分離する。次は実測前の設計候補であり、固定仕様ではない。

- 薪状態texture: 30～60 Hz、または表示revisionが変化したとき
- 炎由来の照明: 15～30 Hz＋時間補間
- 薪形状変形: 数Hz、または変形量が閾値を超えたとき
- Mesh／RTX acceleration structure: 実際に形状が変化したときだけ更新
- 炎照明: Flow voxelを大量のlightへ直接対応させず、少数の代表lightまたはarea lightへ圧縮

これらはwood authorityやFlow入力ではなく、再生成可能な表示observerの更新方針である。低頻度化してもauthority revision、checkpoint、rollback、collisionを表示都合で変更しない。

## 2つの測定契約

### 通常・体感基準

- Candidate Performance
- productionと同じmain／render／present rate、VSync、1280×720
- 45 FPS目標、30 FPS最低ライン
- Flow、薪V3、shadow、emissionを含む実外観

### 最適化診断基準

- production設定を変更しない別process
- main／render上限だけを240 Hzへ上げた短時間診断。present設定は変更しない
- floor＋stones、Cylinder 20本、V3 Mesh 20本、production相当Flow＋volume
- visible FPS、Kit update rate、GPU utilization、power、clock、VRAMを記録
- Power Limit 210 W、1280×720、camera、stage、Candidate Performanceを固定
- cold compile、起動直後、crash後のrunを正式母集団から除外

120 Hzへ張り付いたvisible FPSの代わりにGPU utilizationだけで性能を主張しない。GPU render timeを公開APIで取得できない場合は未計測とし、追加RenderProductやHydraTextureを作って代用しない。

## 安全境界

Phase V3T-MのFlow component分解はsafe stopを維持する。クラッシュ済みpartial topology条件を自動再試行せず、production Flowへ推測対策を入れない。隔離Kitはupload無効、`preserveDump=true`、run固有dump、fatal-token fail-fastを必須とする。

## Phase V3T-O実測

240 Hz診断で静的3 sceneは`166.377..169.892 FPS`まで上がり、productionの約116.7 FPSは120 Hz rendering ceilingに当たっていた。production相当Flow＋volumeは`47.858`から`50.696 FPS`への約5.9%改善に留まり、通常予算の基準はproduction-capped値を維持する。詳細は`uncapped_frame_budget_diagnostic.md`。

## Phase V3T-P production V3予算

CPU-source Wood Visual V3のproduction既定ON後、20本production相当visible viewportは`45.784 FPS / HUD mean 21.904 ms`で45 FPS通常目標を維持した。通常appの単独qualificationは`30.528 FPS`で30 FPS最低線への余裕が小さいため、今後の大きな描画変更では両経路を再測定する。publication totalはp95 `10.175 ms`、max `13.946 ms`、30 ms超過0で、adaptive publicationは2.5125 Hz、実visual commitは2.1 Hzだった。過去の`47.858 FPS / 20.90 ms`基準はV3T-N当時の参照値として残し、V3既定ON後の現在値と混同しない。詳細は`wood_visual_v3_production_default.md`。
