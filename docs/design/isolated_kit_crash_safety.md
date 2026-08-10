# Phase V3T-MA: isolated Kit crash-reporting safety

## 結論

V3T-M以降の隔離Kit runnerは、production appを直接変更せず、同じbuild directoryに生成した一時的なderived `.kit`を使う。Crash Reporterの自動送信を明示的に無効化し、`preserveDump=true`とrun固有のdump directoryを固定する。dump、Kit log、raw解析JSONは機密情報を含む可能性があるローカルartifactであり、Gitへ追加しない。

## 実効設定

derived appとCLIの両方で次を固定し、Kit起動後に再読取する。

- `/app/uploadDumpsOnStartup=false`
- `/crashreporter/skipOldDumpUpload=true`
- `/crashreporter/preserveDump=true`
- `/crashreporter/compressDumpFiles=true`
- `/crashreporter/gatherUserStory=false`
- `/crashreporter/devOnlyOverridePrivacyAndForceUpload=false`
- `/crashreporter/url=""`
- repo-local privacy fileを選択し、`/privacy/performance=false`、usage／personalizationもfalse
- run固有の`/crashreporter/dumpDir`

通常起動smokeでは全gateが合格し、`upload enabled: true`およびupload試行は0だった。意図的なnative access violation fixtureは、Crash Reporter GUIを出さず`0xC0000005`で終了し、圧縮dumpをローカルへ保存した。次回起動後もdumpのSHA-256は不変で、upload試行は0だった。関連するWindows Error Reporting／AeDebug registry snapshotも前後一致した。fixture以外の`kit.exe`やmachine-wide設定は変更していない。

## Fail-fast契約

`[crash] A crash has occurred`、native nonzero exit、stage-ID error、Python traceback、CUDA illegal address、device lost、invalid pointerを正常終了と区別する。native crashを検出したrunnerは同じ条件をretryせず、dump書込み猶予後にrun固有directoryを保全してmatrixを停止する。次条件へ進む前に、自動送信無効の実効設定とupload試行0を確認する。

fixtureはGit外の`artifacts/isolated-kit-native-crash-fixture4-20260810/`へ保存した。dumpは410,922 bytes、SHA-256 `D73D24D51019A26F6C37C7EBCC13570AE28FCCD0D7EEA559566AC14D7BC9E3C9`。fixture固有のfaultは`phasev3tj_crash_handler.dll+0x1250`であり、実不具合の原因証拠ではない。

## 既知の実クラッシュ境界

AO OFFと`flow_layer_translucency_only`は別runだが、どちらも`0xC0000005` read target `0x20`、`omni.fabric.plugin.dll+0xD6960`だった。これはAO固有説を弱める観測だが、RTX設定適用時期、stage接続、Fabric/Hydra初期化、renderer初期化raceのどれが原因かは未確認である。private symbolsを持たないheuristic stack scanから原因を断定しない。

品質設定は可能な限りprocess起動時、stage接続前、RTX scene構築前に固定する。`flow_layer_translucency_only`とAO OFFは、初期化順序を分離した単独probeで保全条件が成立するまで正式matrixから除外し、同条件を自動再実行しない。

## 非変更範囲

production既定、wood authority、Flow入力、Emitter、collision、rigid layout、checkpoint、serialization、V3既定OFFは変更していない。Crash Reporterの送信無効化は隔離runnerだけに適用する。

最終標準suiteは8/8 process、77/77 testが合格し、wall timeは371.6秒だった。
