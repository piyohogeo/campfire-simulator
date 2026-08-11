# Phase 6ED: Windows exception policy correction

## 目的

Phase 6ECのexact axis controlで発見したPhase 6EB Windows exception evidenceのfalse positiveを修正する。対象は`kit_shutdown_policy.ps1`のlog evidence抽出だけであり、NGX known signature、60秒grace、CDB 45秒／512 MiB guard、PID/path/start-time、full dump反復抑制、Phase 6EA resource safety、3軸分類、unknown evidenceのfail-closed契約は変更しない。Phase 6EC A/B/Cと実測用Flow／RTX scenarioは実行しない。保存logの再分類は完全offlineとし、最後の指定済み標準suiteだけが隔離headless Kit test processを起動する。

## 原因

旧patternは次のとおりで、exception文脈を要求せず任意の8桁`0xC........`をWindows例外として扱っていた。

```text
(?i)(exception code|0xC[0-9A-F]{7}|access violation)
```

Phase 6EC AのKit GPU inventoryにはRTX 2070のPCI subsystem identifierとして次の行があり、唯一のmatchになった。

```text
Sub System Id : 0xC75C1462
```

Probe、Flow計測、shutdown、OS exitは正常だったが、旧policyは`windows_exception_present=true`、`fault_module/fault_offset=unparsed`を生成し、fail-closedで`unknown_shutdown_failure`にした。Phase 6ECが停止した判断自体は当時のpolicyに対して正しい。

## 新しいpositive contract

検出器は`File.ReadLines()`でUTF-8 logを行単位に遅延走査し、log全体をメモリへ保持しない。Windows例外は次のpositive contextでのみ成立する。

- `Exception code: 0xC........`、`exception_code=0xC........`、WER形式の`ExceptionCode=...`
- `Unhandled exception ... 0xC........`
- `Process exited with code 0xC........`
- `access violation`
- access-violation code `0xC0000005`。ただしhardware identifier、driver/firmware/PCI、address、hash、color、bitmask等の値文脈はnegativeとする

`0xC0000409`等の他codeは裸の値では検出せず、explicit exception/exit contextを要求する。Hardwareと本物の例外が同じlogに共存する場合、本物のpositive行を検出する。大文字小文字、空白、timestamp/logger prefixを許容する。

空logはreadable evidenceとして例外なしになる。欠落またはread不能logは`windows_exception_present=false`だがevidence availableもfalseとなり、`no_windows_exception=false`でfail closedにする。存在しない例外を理由に`fault_module/fault_offset=unparsed`とはしない。Positive例外を検出しmodule/offsetを安全に解析できない場合だけ両者を`unparsed`としてunknown failureにする。

## Fixture

既存Phase 6EB 24件を維持し、7 contractを追加した。Negativeには`Sub System Id : 0xC75C1462`、同`0xC0000005`、Device/Vendor/Bus ID、GPU UUID、driver/firmware/PCI、color、hash、address、bitmask、裸の`0xC0000409`を含む。PositiveにはException code、Unhandled exception、Process exited with code、Access violation、Crash Reporter `exception_code`、裸の`0xC0000005`を含む。Case、空白、prefix、hardware＋exception共存、空、欠落、exclusive lockによるread不能も検証する。

## Phase 6EC A offline再分類

保存済み`artifacts/phase6ec-static-rotation-1/formal/A_axis_on`の`kit.log`、`raw.json`、`runner_evidence.json`だけをread-onlyで使用した。実Kit／Flowは起動していない。3ファイルのSHA-256は前後一致した。

- exception evidence available: true
- `windows_exception_present=false`
- `access_violation_present=false`
- `fault_module=null`、`fault_offset=null`
- `no_windows_exception=true`
- `functional_status=pass`
- `lifecycle_status=normal_exit`
- `performance_sample_accepted=true`
- `os_process_normal_exit=true`
- production app SHA-256: `94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`

全13 gateが合格した。内訳にはsource artifact不変、evidence可用、Windows例外／access violationなし、fault field null、functional／lifecycle／performance／OS exit、production hash、実際のSubsystem ID行の存在を含む。

これは保存runのpolicy評価だけを訂正するもので、元artifactを上書きせず、過去のPhase 6EC safe-stop記録も改変しない。新しいraw分類はGit管理外の`artifacts/phase6eb-exception-policy-correction-1/`に保存する。

## 最終回帰

- Phase 6EA resource safety: 7 / 7（10.731秒、128 MiB sparse hashのpeak Private Bytes 75,526,144）
- Phase 6EA静的契約: 6 / 6（0.061秒）
- Phase 6EB: 既存24件を含む31 / 31（9.228秒）
- 標準suite: 8 / 8 process、78 / 78件（308.5秒、test upload無効）
- 開発日誌: local reference 369、JSON 182、SVG 148、欠落／parse failure／replacement character／duplicate ID 0
- 終了後: Kit、CDB、fixture helper残留0
- production app SHA-256: 検証後も`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`

## 停止点

Phase 6EC A/B/Cはまだ再実行しない。次の再開条件は、本correctionと全回帰が合格して独立コミットになった後、新しいartifact rootでPhase 6ECをAから開始すること。現在のAを回転比較の正式母集団へ再利用しない。
