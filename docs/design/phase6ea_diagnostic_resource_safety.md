# Phase 6EA diagnostic resource safety

## Scope

Phase 6EAのshutdown hang診断PowerShellが長時間CPUを使い、Private Bytesを数十GiBまで増加させた問題への安全修正である。これは診断ツールだけの変更で、production app、木材authority、Flow、Collider、V3、Resident session、Phase 6DM以降の機能を変更しない。保存済み約5.95 GBのfull dumpも再生成、移動、削除、上書きしない。

## 確認済み事実

- 同じcapture scriptを実行するPowerShellが2本残留した。監査時点の一方はPrivate Bytes約65.5 GiB、もう一方は約2.49 GiBで、どちらも1 threadでCPU時間を増やしていた。その後両PIDは消滅し、追加の強制停止は行われなかった。
- `raw.json`と`kit.log`は小さく、出力directoryには`pre_dump_diagnostics.json`が無かった。このため巨大JSON serialization、最終dump hash、WinDbg解析より前の経路で停止した。
- 旧WCT marshallingは固定長`WCHAR[128]`を長さなし`PtrToStringUni`で読み、構造体境界を保証していなかった。
- 旧`GetWaitChainsBounded`はin-process `Task.Run`を待つだけで、timeout後のnative WCT taskを停止できなかった。
- 旧captureはWCT、live process module列挙、full dump作成、existing-dump metadataを一つのprocessに持ち、多重実行lock、helper Private Bytes上限、`.partial` commitが無かった。

## 原因分類

WCT ObjectNameの境界外read、またはtimeout後も残るnative WCT taskがrunawayの最有力候補である。`pre_dump_diagnostics.json`より前という到達点と整合する。どちらが単独のroot causeかは実5.95 GB dump／Kitを用いた再現を禁止したため未確定であり、断定しない。二重起動防止が無かったことは、同じ危険経路を並列化してメモリ圧迫を増幅した確定要因である。

## 新しい境界

### WCT helper

WCTは`phase6ea_wct_helper.py`という短命processへ隔離した。node size `280` bytes、union offset `8`、最大node `16`、ObjectName `128` UTF-16 code unitsを定数化する。ObjectNameは固定256 byte sliceだけをUTF-16LEとして読み、偶数境界の最初のNULLまたは128 code unitで打ち切る。WCTが返すnode countが16を超えた場合は拒否する。

初版のhelperは起動ごとにPowerShell `Add-Type`でC#を動的compileしていた。2026-08-11の追加再検証では、報告済みの約66 MB・低CPUの90秒fixture待ちを同じcommandで再現できず、durable marker付き単独runでは`Add-Type`開始から完了まで0.157秒、process entryからexit直前まで0.232秒だった。8並行runも全件exit直前markerまで到達した。このため、過去のmarkerなしtimeoutが`Add-Type`、外部compiler、一時file／AV、またはrunspace shutdownのどこで止まったかは確認不能であり、単一原因を断定しない。

一方、fixtureごとの動的compileとPowerShell runspace shutdownがWCTの本来の仕事に不要な可変境界だったこと、および当時のPython `subprocess.run(timeout=...)`がtimeout後のprocess tree不在まで保証していなかったことはコード監査で確認した。追加修正ではWCTの固定layout decodeと公開WCT API呼出しをPython標準`ctypes`だけで実装し、`Add-Type`とcompiler processを経路から除去した。fixture markerは`dynamic_add_type_not_used`、境界decode完了、JSON flush、process exit直前を残せる。test timeoutはfixture PIDのtreeだけを`taskkill /T`で回収し、suite全体も別processの120秒guardで囲う。

親processは既定10秒、Private Bytes 512 MiBでhelperを監視する。timeoutまたは上限超過時はhelper treeだけを終了し、対象Kitは停止しない。結果は`wct_timeout`または`wct_memory_limit`としてpre-dump reportへ残し、dump収集／後続WinDbg解析を継続できる。WCTは補助診断であり、dump成功gateではない。

### Dump helper

`MiniDumpWriteDump`は`phase6ea_dump_helper.ps1`で実行する。既定timeoutは300秒、helper Private Bytes上限は512 MiB、dump上限は16 GiB、予測dump容量に加えて2 GiBの空きdisk marginを要求する。出力は`hang-full.dmp.partial`へ作り、helper exit 0、flush完了、size gate、先頭`MDMP` signatureを確認した後だけ正式名へrenameする。失敗時はpartialだけを削除し、完成済みdumpへ触れない。

親は診断全体を既定360秒で制限する。helperのstdout/stderrは直接ファイルへredirectし、PowerShell変数へ全量を保持しない。dump SHA-256は1 MiB bufferと`FileOptions.SequentialScan`によるincremental streamで計算し、`ReadAllBytes`、`ReadAllText`、dumpへの`Get-Content -Raw`を使用しない。

### Live captureとexisting dump

live captureはPID、expected executable、process start timeを開始時、dump前、monitorによるKit停止前に再確認する。capture自身はKitを停止しない。monitorはdump成功後に同じ3値を再確認してからだけ対象Kitを停止する。helper失敗とKit停止判断は分離され、capture失敗時にmonitorはKitを停止しない。

existing-dump parameter setはPID、WCT、Process.Modules、Stop-Processを一切要求しない。dumpをread-onlyで開き、size、MDMP signature、要求された場合だけ既知SHA-256をstream検証する。完成dumpの上書き、移動、削除は禁止する。

### 多重起動

canonical output pathに対するatomic `CreateNew` lockを使う。lockはowner PID、owner process start time、開始時刻、target PID、dump pathを含む。生存ownerのPIDとstart timeが一致すれば即座に重複を拒否する。stale lockはownerが不在、またはPID再利用でstart timeが異なる場合だけ回収する。読めないlockは自動削除せずfail closedとする。

## Fixture検証

実Kitと保存full dumpは使用していない。次を小fixtureで確認した。

- 非NULL 128文字のObjectNameを正確に128文字で返す。
- WCT helperを1秒でtimeoutさせ、helper PIDが残らない。
- 同じcanonical outputへの二重起動を即時拒否する。
- owner不在のstale lockだけを回収する。
- existing-dump modeがlive PIDなしで動き、WCT／Stop-Processを使わない。
- 128 MiB sparse MDMP fixtureのSHA-256中、PowerShell Private Bytes peakが256 MiB未満で、report上のbufferは1 MiBである。
- dump helper timeoutでpartialだけが消え、正式fileを作らない。
- SHA不一致でexisting-dump診断が失敗しても完成dumpがbyte-for-byte不変である。
- helper stdout/stderrが専用fileへ作られる。

追加再検証の最終acceptanceではresource safety 7件を直列・suite全体120秒guardで実行し、10.548秒で7/7合格した。128文字fixture単体は0.089秒で、値は`X`×128と一致した。128 MiB sparse hash時の対象PowerShell peak Private Bytesは75,014,144 bytes、suite親process peakは12,709,888 bytesだった。static contractは0.003秒で6/6合格した。timeout fixtureのhelper PID消滅と、live sleep fixtureに対するWCT node取得も確認した。

追加検証中、標準userでCIM列挙と`taskkill /T`の両方が拒否された場合にroot helper停止まで例外で飛ばされ、redirect logとpartial fileのhandleが残るcleanup raceも実際に検出した。fallbackの失敗を診断本体へ伝播させず、最後に既知のroot helperを`Stop-Process`し、`WaitForExit`後にだけpartial cleanupへ進むよう修正した。また、この環境の`Start-Process -PassThru`はprocess生存中に`Handle`を取得しないと終了後の`ExitCode`がnullになったため、起動直後にquery handleを保持し、`GetExitCodeProcess`で終了値を取得する。失敗unittestをexit 0と誤分類した中間runは正式合格から除外した。最終run後にPhase 6EA fixture由来PowerShell／Pythonが0件であることをcommand line付きprocess監査で確認した。元の数十GiB runawayと、報告された約66 MB・低CPUのfixture終了待ちは、メモリ特性も到達証拠も異なる別現象として扱う。

標準suiteは8 test processes、78/78件合格、311.6秒だった。最初のsandbox内runは共有Packman cacheの`uv.exe`読取り拒否でtest開始前に停止したため正式結果から除外し、cacheを変更せず同じsuiteを実環境権限で再実行した。

## 残る制約

- 実WCT hangのroot causeを再現していないため、境界外readとnative WCT stallの寄与割合は未確定である。markerなしだった過去の90秒fixture待ちも停止点を事後確定できない。動的compile境界は除去済みだが、過去事象の原因だったと断定はしない。
- 16 GiB、300秒、512 MiBはPhase 6EA隔離診断の既定guardで、全アプリ／全machineの一般保証ではない。
- PowerShell／CIMがprocess treeを列挙できない場合でもroot helperは停止するが、helperが未知の孫processを生成する新設計に変わる場合はtree cleanupを再検証する必要がある。現WCT／dump helperは子processを生成しない。
- 保存済みfull dumpの追加hashや再解析はこの修正では実行していない。
