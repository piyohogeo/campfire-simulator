# Campfire Simulator

焚き火の木材状態、剛体、炎・煙を段階的に検証する、NVIDIA Omniverse Kitベースのリアルタイム・シミュレータです。

現在は **Phase 1「Flow技術スパイク」完了** の状態です。固定された焚き火シーンでFlow火炎を生成し、移動Emitter、静的薪コライダー、統計、NanoVDB CPU読み戻しをウィンドウなしで検証できます。木材燃焼モデルはまだ実装していません。

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

実装の節目、画面キャプチャ、検証結果、既知の問題、次の課題を [Web版Development Log](docs/devlog/index.html) にまとめています。ブラウザで `docs/devlog/index.html` を開くと、外部サービスなしで閲覧できます。

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

固定シーンの必須Prim、Stage単位・重力、再生成時の決定性に加え、Phase 1のFlow Prim、衝突設定、読み戻し設定、Emitter移動をテストします。

## 自動Phase 0検証

```powershell
.\scripts\run_phase0.bat
```

既定の出力先は `artifacts/phase0/latest/` です。別の出力先も指定できます。

```powershell
.\scripts\run_phase0.bat -OutputDir .\artifacts\phase0\manual
```

成功すると次を生成します。

- `assets/scenes/phase0.usda`: 固定シーンの正規USD出力
- `artifacts/phase0/latest/frame_0000.png`: 1280×720の固定カメラ画像
- `artifacts/phase0/latest/summary.json`: ステータス、出力パス、カメラ、解像度

スクリプトはウィンドウなしでアプリを起動し、必要なファイルが揃って終了コードが0であることを検証します。`artifacts/` の生成物はGitの追跡対象外です。

## 自動Phase 1検証

```powershell
.\scripts\run_phase1.bat
```

既定の出力先は `artifacts/phase1/latest/` です。220 updateのFlowシミュレーションを実行し、frame 90と220のPNG、JSON要約、250 ms間隔のGPU CSVを保存します。active block、Emitter終点、4本の薪の衝突設定、PNG寸法も自動検証します。

## GUI起動

```powershell
.\repo.bat launch
```

表示される一覧から `campfire.simulator.kit` を選びます。起動時に固定Phase 0シーンが生成されます。

## 主な構成

- `source/apps/campfire.simulator.kit`: アプリ定義と固定依存バージョン
- `source/extensions/campfire.app/`: シーン生成、キャプチャ、自動テスト
- `scripts/run_phase0.bat`: PowerShell実行ポリシーに依存しないヘッドレス検証の入口
- `scripts/run_phase0.ps1`: 検証本体
- `assets/scenes/phase0.usda`: 生成済み固定シーン
- `DESIGN.md`: 全体設計、段階計画、実測結果、判断ログ
- `AGENTS.md`: 実装時のプロジェクトルール
- `docs/devlog/`: 画面キャプチャ付きのWeb版開発日記

## 現在の制限

- Flowの技術検証用火炎は実装済みですが、木材状態に基づく燃料放出と熱帰還は未実装です。
- 木材の温度、水分、未燃物、炭、灰、質量の状態モデルは未実装です。
- Phase 0の石と薪は検証用プリミティブで、最終形状ではありません。
- raw NanoVDBはCPUへ取得できますが、世界座標一点を読む局所場アダプターは未実装です。
- キャプチャ後のFabric interface version警告とFlow Python node登録警告が非阻害で残っています。

次のマイルストーンはPhase 2「薪・剛体MVP」です。薪の追加・把持・落下・積層とEmitter追従を実装します。
