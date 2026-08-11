# Phase 6EA: Kit shutdown residual process diagnosis

## 目的と境界

Phase 6DZ の未回転 axis control は、stage close、renderer drain、`shutdown_requested`、Hydra shutdown まで到達した後も Kit process が残った。この Phase は回転や Flow collision の再検証ではなく、既知正常な Phase 6DY stage でも同じ終了異常が起きるかを、production-neutral な独立 process で分類する。

production app、Flow 110.0.0、V3、Resident session、wood authority、Emitter、Collider、既定値は変更しない。Cylinder `convexHull`、回転、Flow readback は実行しない。hang dump、command line、process treeなどの機密を含み得る詳細artifactはGit管理外の`artifacts/`だけへ置く。

## Read-only stage監査

比較対象は次の2ファイルである。

- Phase 6DY qualified: `BC65721F4C6D4ECF1F35C736F2DD10F7A47C9F2B361E45898032E869D894D5F9`
- Phase 6DZ regenerated axis: `45CABF115369E538949437599743AAD102CD9CBD3108499A49C4962EFCE26848`

OpenUSDでread-onlyに正規化した結果、差はroot layer documentationと同じ値を反映したpseudo-root metadata documentationの2項目だけだった。6DZには生成元6DY stageの説明が1段追加されている。geometry、topology、extent、schema、`physics:approximation`、attribute値、transform、relationship、Prim順序、custom layer dataは一致した。したがってbyte hashは異なるが、documentationを除くsemantic payloadは一致する。

## 利用可能な診断境界

新規ソフトウェアは導入していない。WinDbg、CDB、ProcDump、Process Explorer、Handle、DumpChkは未導入だった。WPRとWPA、Windows公開Wait Chain Traversal API、DbgHelp `MiniDumpWriteDump`は利用可能だった。

診断runnerはPhase 6DW runner/probeを変更せず外側から監視し、`shutdown_requested`後45秒の観察、executable path確認、thread/module/process情報、公開WCT、full-memory hang dumpを扱う。sandboxではCIM process tree取得が拒否されたため、実行中にread-onlyな権限付きCIMでPID/pathを確認し、今後のrunnerには同一pathかつ開始時刻以後の単一`kit.exe`を使うfallbackを追加した。WCTは今回durable outputを返さなかったため、今後は10秒で打ち切り、dump前snapshotを先に永続化する。

強制停止は正常終了として扱わない。対象PIDとexecutable pathを再確認した残留Kitだけを、dump保全後に停止する。

## 条件Aの結果

Phase 6DYで実際に合格したstageを、同じPhase 6DW runner、probe、引数、`omni.app.viewport.kit`、normal cacheで1回実行した。

- pure OpenUSD open: 到達
- USD context / Hydra接続: 到達
- first renderer update / viewport frame: 到達
- timeline stop / stage close / renderer drain: 到達
- `shutdown_requested`: 到達、probe status `ok`
- 正常OS exit: 未到達
- fatal / Crash Reporter dump / upload attempt / device lost / TDR: 0
- production app SHA-256: 前後とも`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`

最初のrenderer updateはcold pathで約159秒を要したが、その後のstage処理は完了した。`shutdown_requested`後もprocessは残り、dump採取後にpath確認して停止した。自動retryは行っていない。

### 正常ログとの終了境界

今回のhang logとPhase 6DY成功logで最後に共通する終了行は次である。

```text
Shutting down plugin gpu.foundation.plugin
```

成功logは次に`PerfMonitorManager::stop`へ進み、残りのwindow、renderer、CUDA、Fabric、tasking、crash reporter等をunloadして正常終了する。hang logは`gpu.foundation.plugin`の行で終わった。このため、Python probe、quit request、stage closeより後、GPU foundation shutdown中または直後が最も狭い観測境界である。

## Hang dump

Git管理外のfull dumpを保存した。

- path: `artifacts/phase6ea-shutdown-residual-1/A_monitor/sensitive-hang-diagnostics/hang-full.dmp`
- size: `5,949,208,019 bytes`
- SHA-256: `5D91062D28352D8CCBC5153AF1B9256BF4ABDAFA14B242BAC69BDC09ADD20520`
- process: path確認済み`kit.exe`, PID 26684
- threads: 133
- modules: 438
- ExceptionStream: なし
- captured instruction pointers: `ntdll.dll` 132、`win32u.dll` 1

最も早く作成されたthreadのinstruction pointerは`ntdll.dll+0xA0E84`だった。stack memoryの単純なmodule-address scanには`KERNELBASE.dll`、`NvTelemetryAPI64.dll`、`_nvngx.dll`、`D3D12Core.dll`、`carb.graphics-direct3d.plugin.dll`、`carb.dll`が現れた。ただしこれはsymbolized unwindではなくreturn-address候補の走査であり、call stackや責任関数として扱わない。

公開WCTは今回の収集中にdurable resultを返さず、正確なwait objectとowner threadは未確認である。dumpはHandleDataを含むが、ローカルに対応する公開analyzerがないためhandle targetも未解析である。WinDbg/CDBとmatching symbolsがないためnative stackは未展開である。

過去の`omni.fabric.plugin.dll+0xD6960` crashとは異なり、今回はExceptionStreamがなく同offsetもcaptured instruction pointerに現れない。同一原因を示す証拠とは扱わない。

## 判定

### 観測事実

- exact Phase 6DY qualified stageでもshutdown後のprocess残留を再現した。
- stage内容、rotation、6DZ serializationは条件Aの必要条件ではない。
- runnerが別PIDを待っていたのではなく、残っていたprocessは実体path確認済みKitだった。
- GPU/graphics plugin shutdownが`gpu.foundation.plugin`で進まなくなった。
- crash、device lost、TDRではなくhangである。

### 強い推定

captured contextの132/133が`ntdll.dll`にあり、正常logとの差もGPU foundation終了境界に集中するため、processはCPU spinよりGPU/graphics teardownのwait状態にある可能性が高い。

### 未確認

- 正確なwait object、owner thread、GPU fence
- D3D12、NGX、NVIDIA telemetry、Kit renderer/plugin lifetimeのどれが根因か
- 同じ条件が毎回hangするかという再現率
- 6DZ outer orchestration固有差とregenerated axis stage固有差

## Safe stop

条件Aでhangしたため、指示どおり条件B、C、Phase 6DY 3-run stability controlを開始しない。Phase 6DUとrotationの再開条件も満たさない。次に必要なのは、保存dumpをWinDbg/CDBと利用可能なsymbolsで解析するか、別途承認したbounded WPR/ETW teardown traceでwait境界を特定することである。同じ条件の自動再試行は行わない。

このPhaseは内部lifecycle診断で、映像上の新機能はないため新しいデモ動画を作らず、latest demo pointerも変更しない。

## 回帰

Release buildは`9.41 s`で合格した。Phase 6DY lifecycle contractは`6 / 6`、Phase 6DZ rotation/ROI contractは`5 / 5`、Phase 6EA診断contractは`5 / 5`で合格した。標準suiteは8 process・`78 / 78`件・`380.1 s`で合格し、Flow collider対象testもその正式suite内で合格した。日誌は333 local reference、JSON 178、SVG 145、欠落・replacement character 0だった。

補助的な単独Flow testのdirect Kit launcherは、sandboxからAppData test reporterへ書けず120秒でtimeoutしたため正式結果から除外し、対象Kitをpath確認後に停止した。自動retryは行っていない。正式suiteは実環境権限で正常完了している。Production codeとapp compositionを変更していないためPhase 0 RTXとPhase 3は実行していない。
