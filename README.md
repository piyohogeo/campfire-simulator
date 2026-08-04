# Campfire Simulator

焚き火の木材状態、剛体、炎・煙を段階的に検証する、NVIDIA Omniverse Kitベースのリアルタイム・シミュレータです。

現在は **Phase 6「校正と品質」進行中** です。公称12.7 mm・5層の合板試験片で、公開されたガス・タール・チャーの3つの一次Arrhenius反応を同時に解きます。相対反応速度は一次資料へ固定し、共通倍率と吸収率の16候補をSAMP.1/2だけで選定、未使用SAMP.3と別材料OSBへ再調整なしで適用します。

## 必要環境

- Windows 11
- RTX対応NVIDIA GPUと対応ドライバ
- Git
- PowerShell
- 初回ビルド時のネットワーク接続
- NVIDIA Omniverseライセンス条項への同意

このリポジトリは[NVIDIA Omniverse Kit App Template](https://github.com/NVIDIA-Omniverse/kit-app-template)を基盤にしています。初回ビルドはKit SDKと拡張を取得するため数分以上かかることがあります。

検証済み構成はKit SDK `110.2.0`、Flow `110.0.0`、PhysX `110.1.1`、Warp `1.14.0`、RTX 3090 24 GBです。詳細と設計判断は [DESIGN.md](DESIGN.md) を参照してください。

## 開発日記

実装の節目、実画面キャプチャ、検証結果、既知の問題、次の課題を [Web版Development Log](docs/devlog/index.html) にまとめています。ブラウザで `docs/devlog/index.html` を開くと、外部サービスなしで閲覧できます。

## セットアップとビルド

リポジトリのルートで実行します。

```powershell
.\repo.bat build
```

初回実行時にライセンス確認が表示された場合は、内容を確認して同意してください。同意状態を示すローカルファイルはGitへ登録されません。

## テスト

```powershell
.\repo.bat test
```

固定シーンとFlow・剛体設定に加え、熱伝導のエネルギー保存、負質量・NaN防止、湿潤薪の着火遅延、5層試験片の層間熱伝導、3経路Arrhenius速度、生成物収率と質量収支、USD状態の保存再読込をテストします。

## ヘッドレス検証

```powershell
.\scripts\run_phase0.bat
.\scripts\run_phase1.bat
.\scripts\run_phase2.bat
.\scripts\run_phase3.bat
.\scripts\run_phase4.bat
.\scripts\run_phase5.bat
.\scripts\run_phase6.bat
```

各スクリプトはウィンドウなしでアプリを起動し、`artifacts/phase*/latest/` へUSD、1280×720 PNG、JSON要約などを保存して検査します。別の出力先は `-OutputDir` で指定できます。

Phase 2検証は固定60 Hzで600 step（シミュレーション時間10秒）進めます。frame 30で5本目を追加し、永続ID、1 mを超える落下、最終1秒の静止、石囲い内への積層、Emitter追従誤差、Flow active block、画像寸法を自動判定します。

```powershell
.\scripts\run_phase2.bat -OutputDir .\artifacts\phase2\manual
```

Phase 3検証は乾量基準含水率12%と60%の薪を5 Hzで240秒加熱し、全1,200点をCSVへ保存します。着火順、質量収支、負値・非有限値、炭と熱分解ガス、木材由来のFlow入力、2枚のPNGを判定します。

```powershell
.\scripts\run_phase3.bat -OutputDir .\artifacts\phase3\manual
```

Phase 4検証は6本の平行密積みと4本の井桁組みを比較し、酸素係数、着火順、熱分解ガス、質量収支と比較画像を検査します。

Phase 5検証は中央断面を局所加熱し、支持率`0.58`でFixedJointを解除します。分割後の質量・コライダー、PhysX変位、酸素係数`0.30 → 0.82`による再燃、質量収支、崩落前後の2枚の画像を検査します。

Phase 6検証は[NISTIR 7094](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=101408) Appendix Aの35・70 kW/m²合板反復試験を固定分割します。公称12.7 mm・5層モデルで、Thurner–Mannの3経路を同じ未反応木材に対する競合一次反応として解き、4段階の共通A倍率×4吸収率=`16候補`をSAMP.1/2だけで評価します。未使用SAMP.3とOSBへの再調整なし適用、経路別生成量、収率合計、着火順、質量保存、有限値と、USD・PNG・5種のSVG・CSV・JSON生成を検査します。

## GUI起動

```powershell
.\repo.bat launch
```

表示される一覧から `campfire.simulator.kit` を選びます。既定でPhase 6の校正結果シーンが開きます。

## 主な構成

- `source/apps/campfire.simulator.kit`: アプリ定義、固定依存バージョン、既定Phase
- `source/extensions/campfire.app/`: シーン生成、薪サービス、操作UI、キャプチャ、自動テスト
- `scripts/run_phase0.bat` ～ `run_phase6.bat`: ヘッドレス検証の入口
- `assets/scenes/phase0.usda` ～ `phase6_calibration.usda`: 生成済み正規シーン
- `DESIGN.md`: 全体設計、段階計画、実測結果、判断ログ
- `AGENTS.md`: 実装時のプロジェクトルール
- `docs/devlog/`: 実画面キャプチャ付きのWeb版開発日記

## 現在の制限

- 薪は単純な円柱1剛体で、GUI操作も追加・持ち上げ・リセットの最小構成です。マウス拘束による自由な把持は未実装です。
- 密度・摩擦・反発は、校正前の代表値・初期仮説です。Phase 6Aの校正対象は熱モデルの3係数だけで、剛体係数は対象外です。
- Phase 3の熱・反応係数と150 kW/m²の比較熱流束は校正前の初期仮説で、実測木材の予測値ではありません。
- Phase 5の炭残存強度`0.12`、破断閾値`0.58`、崩落前後の酸素係数は校正前です。薪は事前に2セグメントへ分けた円柱で、連続亀裂や任意位置のメッシュ破断は扱いません。
- Phase 6Aは合板試験片を既存の円柱セルへ写像した等価クーポンで、着火は熱分解ガス閾値による代理値です。同じ2条件を探索と評価に使うため、独立した妥当性確認ではありません。
- Phase 6BのOSB評価は候補選択から隔離していますが、別材料への外挿試験です。合板内の独立検証やOSB固有物性を持つモデルではありません。
- Phase 6Cは同一材料内の反復ホールドアウトですが、各熱流束の検証試料はSAMP.3の1点だけです。分割による不確かさがあり、新しい熱流束や試験片条件への予測検証ではありません。
- Phase 6Dの12.7 mmは、報告書に記載された元の屋根パネル公称厚をコーン試料にも適用した推定です。5層は等厚、木目は交互方向と仮定し、接着層を明示していません。
- Phase 6Eの単一見かけ反応は比較用履歴として残しています。Phase 6Fでは3経路を同時に解きますが、一次資料の実験範囲573–673 K外への外挿、窒素中のオーク鋸屑から合板への転用、二次タール反応の省略があります。
- Phase 6Fの最良共通倍率は探索上限`4`です。Table 2スコア改善は`3.4%`、SAMP.3は`2.1%`に留まり、OSBはわずかに悪化したため、係数同定や予測精度達成とは扱いません。
- 1,152セル×2本のPython更新は平均24.85 msです。5 Hzを60 Hzへ償却すると約2.07 ms/frameですが、更新フレームのスパイクは4 ms予算を超えます。
- Phase 3ヘッドレス比較は成功しますが、Flow/USD更新を含む実行は約276秒かかります。配列化またはWarp化と、Flowアダプター更新コストの分離が必要です。
- ヘッドレス検証ではUSD transformを同期する `fetch_results` が平均約15.46 msを占めます。PhysX `simulate` 自体は平均約0.15 msですが、60 Hz実時間更新の性能条件はこの経路では未達です。
- raw NanoVDBを世界座標一点へ変換する局所場アダプターは未実装です。
- Fabric interface version警告とFlow Python node登録警告が非阻害で残っています。

次の作業は合板の単板・接着層とOSBのストランド・バインダー物性を分離し、二次タール反応の要否を評価することです。その後、追加熱流束またはFDSで外部条件を再検証します。
