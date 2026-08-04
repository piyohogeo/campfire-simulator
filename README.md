# Campfire Simulator

焚き火の木材状態、剛体、炎・煙を段階的に検証する、NVIDIA Omniverse Kitベースのリアルタイム・シミュレータです。

現在は **Phase 3「木材熱モデルMVP」完了** の状態です。1本1,152セルの権威状態で熱伝導、水分蒸発、区分線形熱分解、炭化、質量収支を計算し、放出ガス量からFlow燃料入力を生成します。

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

固定シーンとFlow・剛体設定に加え、熱伝導のエネルギー保存、負質量・NaN防止、湿潤薪の着火遅延、USD状態の保存再読込をテストします。

## ヘッドレス検証

```powershell
.\scripts\run_phase0.bat
.\scripts\run_phase1.bat
.\scripts\run_phase2.bat
.\scripts\run_phase3.bat
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

## GUI起動

```powershell
.\repo.bat launch
```

表示される一覧から `campfire.simulator.kit` を選びます。既定でPhase 3の初期シーンが開きます。再現可能な240秒比較は `run_phase3.bat` で実行します。Phase 2の追加・持ち上げ・リセットUIもコード内に保持しています。

## 主な構成

- `source/apps/campfire.simulator.kit`: アプリ定義、固定依存バージョン、既定Phase
- `source/extensions/campfire.app/`: シーン生成、薪サービス、操作UI、キャプチャ、自動テスト
- `scripts/run_phase0.bat` ～ `run_phase3.bat`: ヘッドレス検証の入口
- `assets/scenes/phase0.usda` ～ `phase3_thermal.usda`: 生成済み正規シーン
- `DESIGN.md`: 全体設計、段階計画、実測結果、判断ログ
- `AGENTS.md`: 実装時のプロジェクトルール
- `docs/devlog/`: 実画面キャプチャ付きのWeb版開発日記

## 現在の制限

- 薪は単純な円柱1剛体で、GUI操作も追加・持ち上げ・リセットの最小構成です。マウス拘束による自由な把持は未実装です。
- 密度・摩擦・反発は、校正前の代表値・初期仮説です。実測木材に合わせた校正はPhase 6で行います。
- Phase 3の熱・反応係数と150 kW/m²の比較熱流束は校正前の初期仮説で、実測木材の予測値ではありません。
- 1,152セル×2本のPython更新は平均24.85 msです。5 Hzを60 Hzへ償却すると約2.07 ms/frameですが、更新フレームのスパイクは4 ms予算を超えます。
- Phase 3ヘッドレス比較は成功しますが、Flow/USD更新を含む実行は約276秒かかります。配列化またはWarp化と、Flowアダプター更新コストの分離が必要です。
- ヘッドレス検証ではUSD transformを同期する `fetch_results` が平均約15.46 msを占めます。PhysX `simulate` 自体は平均約0.15 msですが、60 Hz実時間更新の性能条件はこの経路では未達です。
- raw NanoVDBを世界座標一点へ変換する局所場アダプターは未実装です。
- Fabric interface version警告とFlow Python node登録警告が非阻害で残っています。

次のマイルストーンはPhase 4「配置と通気」です。接触・遮蔽から酸素係数を求め、積層方法による燃焼差を比較します。
