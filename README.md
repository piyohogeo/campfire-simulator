# Campfire Simulator

焚き火の木材状態、剛体、炎・煙を段階的に検証する、NVIDIA Omniverse Kitベースのリアルタイム・シミュレータです。

現在は **Phase 6「校正と品質」進行中** です。公称12.7 mm・5層の合板試験片で、公開されたガス・タール・チャーの3つの一次Arrhenius反応を同時に解きます。35/70 kW/m² × 60/180/300/600秒 × 3反復の24条件について、初期面基準の座標、DAQ基準時刻、質量・温度・表面変位・断面画像の生データ契約とRun IDを固定しました。実測は0/24件で、責任研究室による実験検証は保留しています。現在は物理条件を変えず、CPU木材モデル内部の熱収支・状態確定・伝導などを排他的に測定しています。

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

固定シーンとFlow・剛体設定に加え、熱伝導のエネルギー保存、負質量・NaN防止、湿潤薪の着火遅延、5層試験片の層間熱伝導、材料別物性、温度依存比熱の正規化・範囲固定、3経路Arrhenius速度、生成物収率と質量収支、USD状態の保存再読込をテストします。

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

Kit、Flow、USD、描画を除いたCPU木材モデルだけの再現可能な性能測定も用意しています。既定条件は1本1,152セルの薪2本、`dt=0.2 s`、400 stepです。

```powershell
python .\scripts\benchmark_wood_model.py --output .\artifacts\performance\wood_cpu.json
```

複数のPhase 3 `summary.json`から起動・シナリオ・USD・Flow・キャプチャの中央値と範囲を集計できます。

```powershell
python .\scripts\summarize_phase3_profiles.py <run1-summary.json> <run2-summary.json> --json <report.json> --svg <report.svg>
```

Phase 4検証は6本の平行密積みと4本の井桁組みを比較し、酸素係数、着火順、熱分解ガス、質量収支と比較画像を検査します。

Phase 5検証は中央断面を局所加熱し、支持率`0.58`でFixedJointを解除します。分割後の質量・コライダー、PhysX変位、酸素係数`0.30 → 0.82`による再燃、質量収支、崩落前後の2枚の画像を検査します。

Phase 6検証は[NISTIR 7094](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=101408) Appendix Aの35・70 kW/m²合板反復試験を固定分割します。公称12.7 mm・5層モデルで、Thurner–Mannの3経路を同じ未反応木材に対する競合一次反応として解きます。[NISTIR 4916](https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nistir4916.pdf)の材料値と[USDA Wood Handbook Chapter 4](https://research.fs.usda.gov/download/treesearch/62243.pdf)の範囲限定比熱を使用し、16候補をSAMP.1/2だけで評価します。炭化深さ側では、24条件の測定値ゲート、24個のRun ID、6テンプレート、座標・時刻同期、生データ保持、外部承認ゲートに加え、最初のRun ID用の空パッケージが上書きなし・計測値なし・取込み不可で生成されることを検査します。

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
- Phase 6Dの12.7 mmは、報告書に記載された元の屋根パネル公称厚をコーン試料にも適用した推定です。5層は等厚、木目は交互方向と仮定しています。Phase 6Gでは4つの接着界面を記録しますが、未報告の厚さ・組成・熱抵抗は追加していません。
- Phase 6Eの単一見かけ反応は比較用履歴として残しています。Phase 6Fでは3経路を同時に解きますが、一次資料の実験範囲573–673 K外への外挿、窒素中のオーク鋸屑から合板への転用、二次タール反応の省略があります。
- Phase 6Hの温度依存比熱は低温側の根拠を強めますが、Phase 6GからTable 2スコアは`0.382 → 0.452`、SAMP.3は`0.471 → 0.597`、OSBは`2.672 → 3.335`へ悪化しました。式の有効範囲は熱分解開始温度より低い`280–420 K`で、それ以上は420 K値へ固定する明示的近似です。最良共通倍率も探索上限`4`のままなので、予測精度達成とは扱いません。
- Phase 6Jの二次タール反応はNIST Model III記載の`tar → gas`、`A=4.28e6 s⁻¹`、`E=108 kJ/mol`を使う診断です。Borosonらの一次実験範囲`773–1073 K`、`τ=0.9–2.2 s`をシナリオ境界とし、`0.9 / 1.0 / 2.2 s`の感度を比較します。原料と速度式が異なるためモデル検証や係数適合には使いません。一次タールを二次ガスと残存タールへ再分類するだけで、総揮発分、熱収支、着火、質量減少、Flow入力は変えません。
- Phase 6Kでは一次元Darcy流`τ=εμL²/(KΔP)`を独立したSI入力契約として実装しました。現行合板で既知なのは試験片全厚だけで、チャー層厚さ、厚さ方向空隙率・透過率、高温混合気粘度、チャー層圧力差の5入力が未確定です。ブナ球モデルの文献値は文脈としてのみ記録し、滞留時間は`null`、二次反応への結合は無効のままです。
- Phase 6Lの`equivalent_unshrunk_pyrolysis_depth_m`は、各固定層の乾燥木材消費率を元の層厚で積分した質量等価値です。600秒のTable 2最良ケースでは35/70 kW/m²で`9.240 / 12.700 mm`ですが、連続した前線位置でも収縮後の物理炭化層厚さでもありません。Pozzobonらのブナ球で固定格子予測`1.3 mm`が収縮補正後`0.95 mm`、観測`1.0 mm`となる報告は両者を分ける根拠としてのみ使い、ブナの収縮率は合板へ転用しません。
- Phase 6MではKasymovらの未処理カバ合板について、34.7 kW/m²・600秒の端面IR炭化深さ`13.77 ± 0.60 mm`を外部文脈として追加しました。現在の35 kW/m²未収縮相当値は`9.240 mm`ですが、熱流束・時間・100 mm角だけが一致し、厚さ、密度、樹種、接着剤、含水条件、加熱環境、深さ定義は不一致です。比較誤差は`null`、係数選定と物理厚さへの転用は無効です。
- Phase 6Nの[測定CSVテンプレート](source/extensions/campfire.app/data/char_depth_measurement_template.csv)は24個の独立試験を予定します。初期・現在厚さ、符号付き露出面変位、光学前線、300 °C等温線、2種類の不確かさに加え、層別樹種・接着剤・各層厚・乾燥密度・乾量基準含水率・木目方向・質量履歴ファイルを全行で要求します。現在は予定24、完了0で、物理厚さ校正ゲートは閉じています。
- Phase 6Oの[実験プロトコル](source/extensions/campfire.app/data/char_depth_experiment_protocol.json)は、初期露出面中心を原点、試験片内部を`+z`、後退を正・外向き膨張を負と定義します。[24-runスケジュール](source/extensions/campfire.app/data/char_depth_run_schedule.csv)と質量・温度・表面・イベントの生データテンプレートを配布し、300 °C前線は実測深さ間で挟める場合だけ内挿します。技術計画は完成していますが、リポジトリは火災試験を許可せず、3つの外部承認を要求します。
- Phase 6Pは最初のRun ID `CF6O-F035-T0060-R01`について、manifest、4つの生CSV、断面JSON、2つの証拠ディレクトリを空のまま生成するファイルシステムdry runです。9つの実行時メタデータは`null`、計測値は存在せず、実行未承認・取込み不可です。完成済みまたは変更された既存runを上書きしません。
- Phase 6Qの[責任研究室ハンドオフ票](source/extensions/campfire.app/data/char_depth_lab_handoff_template.json)は、実行情報9項目、外部承認証拠3件、研究室レビュー4項目を空欄で配布します。数値・UTC時刻・構造を検査できますが、全欄が埋まってもリポジトリ自身は試験を許可せず、`authorized_to_execute = false`を維持します。
- Phase 6RのCPU単体ベンチでは、2,304セルのstep平均を`6.935 → 5.932 ms`（14.5%短縮）、集計平均を`1.751 → 0.719 ms`（59.0%短縮）しました。同じ物理式・入力・格子・時間刻みを使用し、乾燥薪の発火`66.2 s`、湿潤薪の80秒時点未発火、質量収支を維持しています。これはGPU化の結果ではありません。
- 実アプリPhase 3では木材step平均`43.820 → 35.386 ms`（19.2%短縮）、Flow入力変換平均`65.154 → 8.326 ms`（87.2%短縮）を確認しました。シナリオ全体時間は`276.602 → 50.125 s`でしたが、初回RTX／シェーダーキャッシュ状態が異なるため、この差全体をコード改善へ帰属しません。
- Phase 6Sでは同じPhase 3を2回測定し、runner中央値`256.73 s`のうちviewportのcapture-resolution待機が`199.17 s`（77.6%）、シナリオ中央値`48.23 s`のうちwarmup後CPU木材stepが`39.89 s`（82.7%）でした。薪表示USDは`1.64 s`、Kit／Flow／render更新待機は`1.93 s`、2画像の保存は`1.27 s`です。RTX 3090のアクティブ状態は確認しましたが、GPU利用率やカーネル占有率は採取していません。
- Phase 6TではCPU木材stepへオプトインの8区間タイマーを追加しました。3回中央値で顕熱更新`2.259 ms`、状態clamp・相判定`2.099 ms`が最適化前内部時間の約75%を占めました。相判定の関数呼び出しをセル走査へ統合し、定数比熱の検査をインライン化した結果、内部合計は`5.778 → 5.231 ms`（`9.5%`短縮）、非計測step平均は`5.652 → 5.292 ms`（`6.4%`短縮）でした。乾燥／湿潤状態のJSON SHA-256、発火、質量収支は不変です。
- ヘッドレス検証ではUSD transformを同期する `fetch_results` が平均約15.46 msを占めます。PhysX `simulate` 自体は平均約0.15 msですが、60 Hz実時間更新の性能条件はこの経路では未達です。
- raw NanoVDBを世界座標一点へ変換する局所場アダプターは未実装です。
- Fabric interface version警告とFlow Python node登録警告が非阻害で残っています。

次の作業は、実環境の実験検証を保留したまま、残る支配区間の顕熱更新と状態確定を、Python配列・NumPy・Warp候補について変換・転送・同期を含めて小さく比較することです。GPU化はCPUからGPUへ毎step状態を往復させない構成でのみ採否を判断します。約199秒のviewport／capture準備待機は木材計算と分離し、RTX readyイベントとの対応とキャッシュ書込みエラーを別に調査します。責任研究室からレビュー済み票を受領するまで設備dry runは開始しません。
