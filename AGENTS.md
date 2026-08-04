# Campfire Simulator 開発ルール

作業前に `DESIGN.md` を読み、未決事項と仮説を確定仕様として扱わないこと。

## 実装方針

- GUI機能には、同じ操作を実行・検証できるヘッドレスまたはスクリプト経路を用意する。
- Kit、PhysX、Flowのバージョンは、明示的な設計判断と再検証なしに更新しない。
- シミュレーションはSI単位系を使う。無次元係数や表示専用倍率は、物理量と明確に分離する。
- 物理パラメータを追加・変更するときは、理由、単位、比較対象または出典を文書化する。
- 回帰判定をゴールデン画像だけに依存させず、物理的不変条件、数値メトリクス、画像を組み合わせる。
- 未確認のOmniverse APIを推測で実装しない。ローカルSDK、同梱サンプル、実行時挙動で確認する。
- 木材状態モデルを権威状態とし、Flowや描画状態へ不用意に結合しない。

## 基本コマンド

```powershell
.\repo.bat build
.\repo.bat test
.\repo.bat launch
.\scripts\run_phase0.bat
.\scripts\run_phase1.bat
.\scripts\run_phase2.bat
.\scripts\run_phase3.bat
.\scripts\run_phase4.bat
.\scripts\run_phase5.bat
.\scripts\run_phase6.bat
```

生成物は `_build/` と `artifacts/` に置く。各Phaseの正規シーンは `assets/scenes/phase0.usda`、`phase1_flow.usda`、`phase2_rigid.usda`、`phase3_thermal.usda`、`phase4_air.usda`、`phase5_collapse.usda`、`phase6_calibration.usda`。

## 変更時の確認

- PythonまたはUSD生成ロジックを変更したら `.\repo.bat test` を実行する。
- アプリ依存関係、起動設定、レンダリングを変更したら `.\repo.bat build` と `.\scripts\run_phase0.bat` を実行する。
- 実測結果や設計判断が変わったら `DESIGN.md` の判断ログと `CHANGELOG.md` を更新する。
- マイルストーン完了時、または画面・挙動が人間から見て変わる変更時は `docs/devlog/index.html` に開発日記を追記する。日付、目標、実装内容、実測・テスト、既知の問題、次の課題を含め、視覚的な変更には実機キャプチャを `docs/devlog/assets/<entry>/` に保存する。
- 開発日記のキャプチャは装飾用の合成画像ではなく、可能な限り固定カメラまたは再現可能な操作で生成した実画面を使う。画像だけを成功判定には使わない。
- NVIDIA由来ファイルのライセンス表記とKit App Templateの来歴を保持する。
