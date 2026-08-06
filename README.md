# Campfire Simulator

焚き火の木材状態、剛体、炎・煙を段階的に検証する、NVIDIA Omniverse Kitベースのリアルタイム・シミュレータです。

現在は **Phase 6「校正と品質」進行中** です。公称12.7 mm・5層の合板試験片で、公開されたガス・タール・チャーの3つの一次Arrhenius反応を同時に解きます。実木材・実火炎・実験設備を使う検証はスコープ外とし、Phase 6N〜6Qの24条件計画と受け入れ契約は履歴資料として保持します。現在はdebugger-free実アプリで局所CPU改善を権威出力とend-to-end性能の両方で選別しており、Phase 6AHでは顕熱更新のうち熱容量評価を次の試作候補へ絞りました。

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

開発日誌用の実画面動画は任意指定で生成できます。固定カメラの1280×720 PNGをモデル時間4秒ごとに60枚取得し、ffmpegで10 fps・6秒のH.264 MP4へ変換します。通常の検証と性能測定では無効なので追加時間は発生しません。動画生成時も状態SHA、CSV、着火、質量収支の検査を省略しません。

開発日誌では各進捗に小さな再生アイコンを付け、クリックすると共通モーダル内で動画を再生します。新しい進捗が権威状態と見た目を変えない場合は同一MP4を再参照でき、バイナリを複製しません。Esc、背景クリック、閉じるボタンに対応し、自動再生が拒否された場合も標準コントロールから再生できます。

```powershell
.\scripts\run_phase3.bat -OutputDir .\artifacts\phase3\video -CaptureVideo
```

Python経路では、外部面積が厳密に0の内部セルについて放射・対流・外部加熱を省略し、伝導だけを適用します。1本1,152セル中792セルが対象です。debugger-free Phase 3の交互順序3組では、権威出力を完全一致させたまま木材step中央値を`11.3241 → 10.4262 ms`、シナリオ中央値を`17.6416 → 16.5991 s`へ短縮しました。比較を再実行する場合は次を使います。

```powershell
.\scripts\run_phase6aa_surface_boundary_benchmark.ps1
```

状態確定区間の分岐頻度は、通常無効の診断runで再現できます。時間値は性能根拠に使わず、温度・質量clamp、相割当、実際の相遷移だけを記録します。

```powershell
.\scripts\run_phase6ab_state_diagnostics.ps1
```

診断でclampが0回だったことを受け、安全境界・NaN・`-0.0`の扱いを維持しながら、正常範囲の組込み`min/max`を比較分岐へ変更しました。交互順序3組では木材step中央値を`10.3717 → 8.2559 ms`、シナリオ中央値を`16.4571 → 14.1304 s`へ短縮しています。

```powershell
.\scripts\run_phase6ac_state_clamp_benchmark.ps1
```

Phase 3のFlow入力、CSV、表示、着火判定はセルの`phase`を読まず、診断と最終永続化だけが必要とすることを監査しました。通常の`step()`は従来どおり逐次更新しますが、Phase 3 runnerでは相分類を最終一回へ遅延します。交互順序3組では木材step中央値を`7.6849 → 7.2286 ms`、シナリオ中央値を`13.8153 → 13.2939 s`へ短縮し、最終状態とCSVは完全一致しました。

```powershell
.\scripts\run_phase6ad_deferred_phase_benchmark.ps1
```

Phase 3の毎step集計を監査し、Flow、CSV、薪表示が使う表面平均温度と4質量だけを同じセル順序で集計する経路を追加しました。完全な`metrics()` APIと最終summaryは維持しています。交互順序3組では集計中央値を`0.9889 → 0.3283 ms`、集計を含むstep loopを`9.9631 → 9.3976 ms`、シナリオを`11.9105 → 11.2295 s`へ短縮しました。

```powershell
.\scripts\run_phase6ae_runtime_metrics_benchmark.ps1
```

Phase 6AFでは、セル一覧・表面セル一覧・表示用初期乾燥質量を、シナリオ設定後に明示的にスナップショットする試作を評価しました。セルと表面属性は公開可変で、校正処理が生成後に表面を編集するため、コンストラクタでの無条件キャッシュは採用していません。交互順序3組で対象のmetrics集計は`0.3320 → 0.2902 ms`、表示更新は`0.8605 → 0.5588 ms`へ短縮しましたが、step loopは`9.1705 → 9.2754 ms`、シナリオは`10.9577 → 11.0834 s`へ悪化しました。3/3組で全体時間が悪化したため既定は動的読取りのままです。標準テストは一度、熱モデル分割の既存180秒上限へ達しましたが、同じ設定の再実行で`271.5 / 189.4 / 23.5 s`、41/41件を`489.2 s`で成功させました。

```powershell
.\scripts\run_phase6af_runtime_topology_benchmark.ps1
```

Phase 6AGでは、Phase 6AA〜6AEの採用後構成を内部タイマー付きで3回測定し直しました。内部合計はPhase 6Yの`11.6346 → 6.1429 ms`（`47.20%`短縮）となり、状態確定は`3.7012 → 0.3448 ms`まで低下しました。現在の最大区間は顕熱`3.0032 ms`（`48.89%`）、次いで熱分解`1.0256 ms`、伝導`0.8524 ms`です。このprofileは候補選定用で、採用判断には別の非計測交互runを要求します。

```powershell
.\scripts\run_phase6ag_adopted_profile.ps1
```

Phase 6AHでは、顕熱更新をセル単位の操作へ分けて3回測定しました。詳細合計中央値`4.2752 ms`のうち、熱容量評価は`2.6504 ms`（全体の`61.99%`、3操作の`78.51%`）、内部セル更新は`0.2847 ms`、表面境界更新は`0.4408 ms`、ループ／タイマー負荷は`0.8993 ms`でした。セル単位タイマーが絶対時間を歪めるため、結果は候補順位にだけ使います。3 runの状態SHA-256、CSV SHA-256、着火`66.2 / 166.4 s`は完全一致しました。標準テストはcoverage付き4群とcoverageなし数値群へ分け、`32 + 4 + 2 + 1 + 2 = 41`件を`595.0 s`で成功させました。

```powershell
.\scripts\run_phase6ah_sensible_heat_profile.ps1
```

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
- Phase 6Nの[測定CSVテンプレート](source/extensions/campfire.app/data/char_depth_measurement_template.csv)は24個の独立試験を想定した履歴資料です。実木材実験をスコープから外したため、予定24・完了0のままアーカイブし、物理厚さの定量校正には進みません。
- Phase 6Oの[実験プロトコル](source/extensions/campfire.app/data/char_depth_experiment_protocol.json)と[24-runスケジュール](source/extensions/campfire.app/data/char_depth_run_schedule.csv)は、座標・時刻・取得規則を記録するアーカイブです。外部承認の取得や火災試験の実施は作業予定に含めません。
- Phase 6Pの空run-package生成は、既存ファイルを上書きしない受け入れ契約の履歴として保持します。実設備dry runや実測取込みには使用しません。
- Phase 6Qの[責任研究室ハンドオフ票](source/extensions/campfire.app/data/char_depth_lab_handoff_template.json)は、権限分離を示すアーカイブです。責任研究室の記録は現在のソフトウェア開発の前提条件ではありません。
- Phase 6RのCPU単体ベンチでは、2,304セルのstep平均を`6.935 → 5.932 ms`（14.5%短縮）、集計平均を`1.751 → 0.719 ms`（59.0%短縮）しました。同じ物理式・入力・格子・時間刻みを使用し、乾燥薪の発火`66.2 s`、湿潤薪の80秒時点未発火、質量収支を維持しています。これはGPU化の結果ではありません。
- 実アプリPhase 3では木材step平均`43.820 → 35.386 ms`（19.2%短縮）、Flow入力変換平均`65.154 → 8.326 ms`（87.2%短縮）を確認しました。シナリオ全体時間は`276.602 → 50.125 s`でしたが、初回RTX／シェーダーキャッシュ状態が異なるため、この差全体をコード改善へ帰属しません。
- Phase 6Sでは同じPhase 3を2回測定し、runner中央値`256.73 s`のうちviewportのcapture-resolution待機が`199.17 s`（77.6%）、シナリオ中央値`48.23 s`のうちwarmup後CPU木材stepが`39.89 s`（82.7%）でした。薪表示USDは`1.64 s`、Kit／Flow／render更新待機は`1.93 s`、2画像の保存は`1.27 s`です。RTX 3090のアクティブ状態は確認しましたが、GPU利用率やカーネル占有率は採取していません。
- Phase 6TではCPU木材stepへオプトインの8区間タイマーを追加しました。3回中央値で顕熱更新`2.259 ms`、状態clamp・相判定`2.099 ms`が最適化前内部時間の約75%を占めました。相判定の関数呼び出しをセル走査へ統合し、定数比熱の検査をインライン化した結果、内部合計は`5.778 → 5.231 ms`（`9.5%`短縮）、非計測step平均は`5.652 → 5.292 ms`（`6.4%`短縮）でした。乾燥／湿潤状態のJSON SHA-256、発火、質量収支は不変です。
- Phase 6Uでは支配区間の顕熱更新＋状態確定だけを、2,304セル・400 step・3 runでPython AoS、NumPy、Warp CUDAへ同じfloat64式として実装しました。AoS変換込みNumPyは`3.952 → 3.067 ms/step`（`22.4%`短縮）でしたが、毎step H2D／D2Hを含むWarpは`4.159 ms/step`でPythonより`5.2%`遅く、現構成では不採用です。NumPy／Warp常駐の`0.064 / 0.071 ms/step`は、伝導・反応・Flowを含まないアーキテクチャ下限であり本番性能とは扱いません。全候補の最終状態SHA-256はPythonと完全一致しました。
- Phase 6Vでは標準`repo.bat test`を、coverage付きの通常39件とcoverageなしの決定論的NIST校正1件へ分離しました。最終実測は通常`217.7 s`、校正`24.5 s`、全体`246.9 s`で40/40成功し、各プロセスはKitの`300 s`上限内です。タイムアウト値を緩めたり校正テストを削除したりせず、API文書整合性の自動検査も維持しています。
- Phase 6Wでは`WoodThermalModel.step()`へ任意選択のNumPy経路を追加し、既定のPython経路を維持しました。2,304セル・400 step・3 runの完全な木材stepは`3.1313 → 2.8228 ms/model-step`（`9.9%`短縮）で、毎step結果履歴、最終状態SHA-256、集計値は完全一致しました。Phase 3の1,200 stepでも乾燥／湿潤状態、CSV、着火時刻、Flowピークが一致しましたが、デバッグ拡張が残った実行時間は採用判断から除外しています。標準テストは通常39件＋数値検証2件の41/41件が成功しました。
- Phase 6Xではdeveloper bundleをversion lockから除いた測定専用`campfire.simulator.benchmark.kit`を追加しました。debug拡張4種を実行時にも検査し、Python→NumPy／NumPy→Pythonの交互順序2組でPhase 3を再測定しています。全4 runの状態SHA-256、CSV SHA-256、着火時刻`66.2 / 166.4 s`、Flow peak`294`は完全一致しました。木材step平均の中央値はPython`11.218 ms`、NumPy`11.472 ms`でNumPyが`2.3%`遅く、シナリオも`17.532 → 17.858 s`（`1.9%`遅い）ため、既定はPythonに確定しました。runner中央値は約`35.4 / 35.9 s`です。標準テストはcoverage付き35件＋熱モデル4件、coverageなし数値2件へ分割し、`186.0 / 135.3 / 27.6 s`、全41件を`353.5 s`で成功させました。
- Phase 6Yでは同じdebugger-freeアプリで、明示指定時だけ既定Python木材stepを8区間へ分けて3回測定しました。各区間はwarmup後`1,180`サンプルで、二本のstep中央値は`11.716 ms`、シナリオ`18.275 s`、runner`36.834 s`です。顕熱更新`4.532 ms`（内部の`39.0%`）、状態確定`3.701 ms`（`31.8%`）、熱分解`1.251 ms`（`10.8%`）の順でした。3 runで乾燥／湿潤状態SHA-256、CSV SHA-256、着火`66.2 / 166.4 s`は完全一致し、Flow peakは3回とも`293`でした。計測なし通常runでは内部区間が空であることも確認し、標準テストは`180.2 / 129.6 / 25.3 s`、41/41件を`339.9 s`で成功させました。次の候補は配列往復を増やさない顕熱ループです。
- Phase 6Zでは顕熱更新のスカラー分岐、周囲温度4乗、係数参照をループ外へ出す局所試作を、profile前後各3 run・非計測前後各3 runで評価しました。profile顕熱区間は`4.5321 → 4.2853 ms`（`5.45%`短縮）しましたが、非計測木材stepは`12.0693 → 12.1800 ms`（`0.92%`悪化）、シナリオは`18.7336 → 19.0102 s`（`1.48%`悪化）でした。全runで状態SHA-256、CSV SHA-256、着火`66.2 / 166.4 s`は完全一致しました。end-to-end採用条件を満たさないため試作は戻し、元のPythonループを維持しています。最終ビルド後の標準テストは`272.2 / 126.6 / 26.6 s`、41/41件を`429.8 s`で成功させました。
- ヘッドレス検証ではUSD transformを同期する `fetch_results` が平均約15.46 msを占めます。PhysX `simulate` 自体は平均約0.15 msですが、60 Hz実時間更新の性能条件はこの経路では未達です。
- raw NanoVDBを世界座標一点へ変換する局所場アダプターは未実装です。
- Fabric interface version警告とFlow Python node登録警告が非阻害で残っています。

次の作業は、Phase 6AHで最大と分かった熱容量評価の呼出し・検査契約を監査し、定数乾燥木材比熱の重複評価を減らせるか限定試作することです。権威出力の完全一致と、交互順序の非計測step-loop／シナリオ改善が揃った場合だけ採用します。その後は2 / 5 / 10 / 20本へ薪本数を増やしてCPUとFlow境界のスケーリングを測り、CPU継続、GPU常駐再設計、性能作業打切りのいずれかを判断します。NumPyは明示選択可能な検証経路として残し、Warpは全状態とCPU側メトリクス・Flow・USD境界を一体で再設計できる場合に限って再検討します。実木材実験はスコープ外です。
