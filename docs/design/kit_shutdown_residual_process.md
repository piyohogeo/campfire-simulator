# Phase 6EA: Kit shutdown residual process diagnosis

## Phase 6EL: bounded CDB diagnostic path

Debugging Tools for Windows supplies x64 CDB at `C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe`. The diagnostic now finds this installed path before the Store-package fallback and records file version `10.0.28000.2526 (WinBuild.160101.0800)`, size 178,632 bytes, and SHA-256 `506D1FD7AD306F6F53D8D157375A03A8368446923DEF9457CDFB2E3214054376`. It does not call `cdb -iae`, write AeDebug/WER registry state, or install a system-wide postmortem debugger. Read-only hashes of the relevant machine debugger settings were identical before and after the fixtures.

CDB remains a residual-only diagnostic. The policy first matches PID, process start time, and absolute executable path, then uses a non-invasive `-pv` attach. CDB stdout and stderr are redirected directly to files with 16-MiB and 2-MiB ceilings, a 512-MiB process ceiling, and an explicit timeout. Commands enumerate loaded modules and `~* kPn 64` all-thread native stacks, then `qd` detaches. Flushed markers record attach start/completion, stack start/completion, detach completion, and debugger cleanup. The report also records CDB/target/diagnostic-helper Private Bytes and cumulative user/kernel CPU time. Symbol loading uses a per-artifact cache and the Microsoft public symbol server inside the same timeout; missing private NVIDIA/Omniverse symbols leave raw module-plus-offset evidence rather than relaxing classification.

Five isolated fixtures passed. The final wait target and exclusive-log target produced 37,449-byte and 38,518-byte stack files, retained their target processes after detach, and removed CDB. The exclusive log recorded `log_capture_error` but still committed its diagnostic JSON. A normal target exited before attach and was rejected by identity/liveness validation. An intentional CDB sleep crossed the two-second debugger timeout; only CDB was stopped, the target remained alive for exact fixture cleanup, and no helper remained. Invalid CDB arguments produced a bounded nonzero exit and no residual. CDB peak Private Bytes was at most 48,279,552 bytes in the validated run, diagnostic-helper peak was at most 96,796,672 bytes, and the fixture runner peaked at 98,504,704 bytes.

These fixtures prove the attach/capture/detach mechanism, not the known NGX signature on Kit. Known-NGX acceptance still requires the existing five stack tokens; an unknown module/offset, incomplete symbols, missing marker, timeout, or ambiguous stack fails closed. Phase 6EG remains unqualified and its 36-process matrix was not restarted. The next formal run is now diagnosable if it leaves a residual, but still requires a new artifact root and explicit approval.

Regression passed the Release build in 6.57 seconds, 79/79 focused Phase 6EA/6EB/6ED/6EJ/6EL and Phase 6EG contract tests, and the eight-process standard suite with 78/78 tests in 310.2 seconds. Production and frozen-contract SHA-256 values remained unchanged.

## Phase 6EK: locked-log and descendant-cleanup correction

The approved Phase 6EG restart reached a low-CPU shutdown wait in P4 after Flow measurement. Kit held `kit.log` exclusively, so the isolated diagnostic failed before its bounded JSON report and CDB decision. Log tailing is auxiliary evidence: the diagnostic now records `log_capture_error` and continues. A dedicated exclusive-lock fixture persisted `kit_log_parse_complete`, GPU inventory, CDB decision, JSON commit, cleanup, normal child exit, and parent return. This does not make a capture successful when CDB is unavailable; known-NGX classification still requires the accepted stack signature and otherwise fails closed.

The outer guard previously proved only root-process absence. It now stores every observed descendant identity as PID, creation time, and exact executable path. After root termination, exact surviving identities are rejected as `observed_descendant_residual`, stopped, and rechecked. An isolated orphan-child fixture verified both rejection and zero remainder. The original P4 residual Kit was stopped only after exact identity matching. The 512 MiB runner/diagnostic limits, 14 GiB Kit limit, 16 GiB tree limit, headroom floors, bounded output, and no-automatic-retry contracts are unchanged.

## Phase 6EJ: whole-diagnostic process isolation

The lightweight diagnostic now runs entirely in a short-lived guarded PowerShell child. Identity validation, capture-lock ownership, isolated `nvidia-smi`, bounded lifecycle/log parsing, CDB necessity and capture, report commit, and cleanup no longer execute in the formal runner runspace. The child has a 90-second and 512-MiB ceiling, redirects stdout/stderr to files, writes through `.partial` plus atomic rename, and returns only a bounded JSON document or guarded failure state.

Flushed markers make the last completed boundary durable even when JSON publication fails. The fixture reached every marker and exited normally with an 85.1-MB peak. The timeout fixture was terminated at 71.2 MB and left no process. CDB was not available in the installed WinDbg package search, so this fixture proved bounded persistence and cleanup, not known-NGX signature acquisition. No residual may be classified as known without the existing stack-signature requirement.

CPU telemetry is part of the low-volume resource JSONL, not the diagnostic report payload. It records cumulative user/kernel time and the delta normalized so 100% equals all logical processors. The first sample is missing by design. A top Kit thread is sampled only on high CPU. Telemetry OFF/ON comparison stayed within the fixed overhead limits. In the successful P0-equivalent run, shutdown CPU was low (1.84% mean, 3.77% maximum), while high-CPU thread samples occurred only during startup. Since that run exited normally, the earlier silent interval's wait/spin state is still unknown.

The old Phase 6EI increase from 146.9 to 553.9 MB is confirmed to precede report commit in the former in-process diagnostic. Isolation removes that allocation from the parent boundary, but the specific PowerShell/native allocator responsible has not been reproduced or asserted. A future residual must persist its last marker and remains fail closed when CDB is unavailable.

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

収集時の公開WCTはdurable resultを返さなかったが、その後インストールしたWinDbg 1.2606.22001.0同梱のx64 CDB 10.0.29617.1000で同じdumpを再実行なしに解析した。Microsoft public symbol serverのcache、WinDbg command、raw logはすべてGit管理外の`artifacts/phase6ea-shutdown-residual-1/windbg/`へ置いた。NVIDIA／Omniverse private symbolは得られず、該当moduleはexport名とmodule offsetで扱う。

### WinDbg symbolized解析

`!analyze -hang`は`APPLICATION_HANG_cfffffff_NvTelemetryAPI64.dll!Unknown`、`NvTelemetryAPI64+0x3CC87`を選んだ。全133 threadのstack、`!runaway 7`、handle data、module inventoryを突合すると、main thread 0（OS thread `0x641C`）のblocking chainは次だった。

```text
kit / carb framework shutdown
  -> gpu.foundation.plugin.dll+0x18F4D3
     (nearest export: carbOnPluginShutdown+0x133)
  -> carb.graphics-direct3d.plugin.dll+0x621BE
  -> _nvngx!NVSDK_NGX_D3D12_Shutdown1+0x82
  -> NvTelemetryAPI64!UninitializeTelemetry+0xAF
  -> WaitForSingleObjectEx(handle 0x1D4C)
```

handle `0x1D4C`はEventやGPU fenceではなくThread objectで、targetはthread 128（OS thread `0x1A60`）だった。対象threadは`NvTelemetryAPI64.dll+0x44780`から開始され、`NvTelemetryBridge64.dll+0x134F8`内から`KERNELBASE!WaitNamedPipeW`を呼び、GUID名のlocal named pipeを待っていた。stack frameには`0x1388`（5000 ms）があるため5秒のpipe timeout候補と読めるが、private symbolがないので引数同定は強い推定に留める。mainとtelemetry threadのTEBはともにowned lock 0で、`!locks`にも保持critical section chainは出なかった。

loaded moduleは`gpu.foundation.plugin.dll`、D3D12、NGX、NVIDIA UMD、Telemetry API/Bridgeを含んだ。D3D12Core 10.0.22621.5415は公開PDBで解決され、4本のD3D background threadはいずれもcondition variableでidleだった。全thread stackに`ID3D12Fence`、`SetEventOnCompletion`、`LdrUnloadDll`、`FreeLibrary`はない。CUDA／NVIDIA UMDの通常wait threadは存在するが、mainが待つthread object `0x1D4C`のtargetではない。したがって、このsnapshotで直接確認できる停止点はGPU fenceやDLL loader lockではなく、NGX D3D12 shutdown中のNVIDIA telemetry worker joinである。

過去の`omni.fabric.plugin.dll+0xD6960` crashとは異なり、今回はExceptionStreamがなく同offsetもcaptured instruction pointerに現れない。同一原因を示す証拠とは扱わない。

## 判定

### 観測事実

- exact Phase 6DY qualified stageでもshutdown後のprocess残留を再現した。
- stage内容、rotation、6DZ serializationは条件Aの必要条件ではない。
- runnerが別PIDを待っていたのではなく、残っていたprocessは実体path確認済みKitだった。
- GPU/graphics plugin shutdownが`gpu.foundation.plugin`で進まなくなった。
- crash、device lost、TDRではなくhangである。

### 強い推定

main threadのwait handleとtarget threadをdump内HandleDataから対応付けられた。したがって、processはCPU spinや一般的なrenderer frame待ちではなく、GPU foundationからNGX D3D12 shutdownへ入り、NVIDIA telemetry workerの終了を同期的に待つ状態にある可能性が高い。D3D12 background threadやGPU fenceがmain blockerである証拠はない。

### 未確認

- GUID名telemetry pipeが利用可能にならない、または所定時間内に戻らない理由
- multi-GPU状態、NVIDIA telemetry service状態、NGX shutdown順序のどれが上流triggerか
- 同じ条件が毎回hangするかという再現率
- 6DZ outer orchestration固有差とregenerated axis stage固有差

## Safe stop

条件Aでhangしたため、指示どおり条件B、C、Phase 6DY 3-run stability controlを開始しない。Phase 6DUとrotationの再開条件も満たさない。保存dumpの解析でwait境界はtelemetry worker joinまで絞れたが、上流triggerは未確認である。追加証拠が必要なら、別途承認した60〜90秒のfile-mode WPR/ETWを`shutdown_requested`前後だけ取得する。CPU sample、CSwitch/ReadyThread、thread lifetime、file/named-pipe I/O、image load/unload、D3D12、DXGI、DxgKrnl、QPC相関のPhase markerを含める。現在の`wpr -providers`でNVIDIA/Telemetry providerは見つからなかったため、将来のcapture時に列挙できた場合だけ追加する。同じhang条件の自動再試行は行わない。

このPhaseは内部lifecycle診断で、映像上の新機能はないため新しいデモ動画を作らず、latest demo pointerも変更しない。

## 回帰

Release buildは`9.41 s`で合格した。Phase 6DY lifecycle contractは`6 / 6`、Phase 6DZ rotation/ROI contractは`5 / 5`、Phase 6EA診断contractは`6 / 6`で合格した。標準suiteは8 process・`78 / 78`件・`380.1 s`で合格し、Flow collider対象testもその正式suite内で合格した。日誌は336 local reference、JSON 179、SVG 145、欠落・replacement character 0だった。

補助的な単独Flow testのdirect Kit launcherは、sandboxからAppData test reporterへ書けず120秒でtimeoutしたため正式結果から除外し、対象Kitをpath確認後に停止した。自動retryは行っていない。正式suiteは実環境権限で正常完了している。Production codeとapp compositionを変更していないためPhase 0 RTXとPhase 3は実行していない。

WinDbg follow-up後はPhase 6EA targeted contract `6 / 6`、標準suite 8 process・`78 / 78`件・`354.2 s`に合格した。日誌は336 local reference、JSON 179、SVG 145、欠落・replacement character 0である。接続可能なBrowserがなかったため実レンダリング確認はできず、静的参照、JSON、SVG、UTF-8検査で代替した。

## Phase 6EB: 既知residualの監視運用

Phase 6EAでstack境界が特定できたため、この現象を全機能検証の永久blockerにはしない。ただし正常終了へ読み替えない。runnerは`shutdown_requested`後に最大60秒待ち、その間のexit 0を`normal_exit`とする。60秒後もpath確認済みの対象`kit.exe`だけが残る場合、CDBの非侵襲attachで全threadの短いstackを取得し、`gpu_foundation_plugin!carbOnPluginShutdown`、NGX D3D12 shutdown、Telemetry uninitialize、Telemetry Bridgeの`WaitNamedPipeW`がそろう場合だけ既知signatureとする。CDB、symbol cache、生stack logはGit管理外で、反復ごとのfull dumpは作らない。

既知signatureでも、probe完了、public result保存、timeline stop、stage close、renderer drain、`shutdown_requested`、production hash不変、fatal／dump／Windows exception／`0xC0000005`／device lost／TDR／CUDA illegal address／upload attempt 0がすべて必要である。さらに診断前と停止直前にPID、実行path、process start timeを再確認し、外側runnerからだけ終了させ、PID消滅を確認する。合格表現は次の3軸に固定する。

```text
functional_status: pass
lifecycle_status: known_ngx_shutdown_residual
performance_sample_accepted: false
```

これはnormal exitではなく、shutdown時間、normal-exit率、性能母集団から除外する。outcomeには最後のapplication marker、`shutdown_complete_reached`、`os_process_normal_exit`を別々に記録し、`shutdown_complete`到達をexit 0へ読み替えない。signature不一致、証拠不足、完了gate不足、PID/path/start-time未確認、Windows exception、未知module／fault offset、dump、停止失敗は`unknown_shutdown_failure`としてfail closedにする。入力JSONの欠落、型不一致、破損も明示的なunknown結果にする。アプリ内部の`os._exit()`やkillは使わない。

軽量CDBはPhase 6EAの共通安全helperへ隔離し、atomic output lock、45秒timeout、Private Bytes 512 MiB上限、process-tree cleanupを適用する。stdout/stderrは直接Git外ファイルへredirectし、stack tokenはstreaming検索する。WCT 10秒、Phase 6EA診断全体360秒、dump 16 GiB上限、`.partial` commit、existing dump read-onlyなど既存のPhase 6EA契約は変更しない。CDB helperがtimeout、memory超過、起動失敗した場合は既知signatureとは認めず、helper失敗を理由に対象Kitを停止しない。full dumpは同signatureの通常反復では作らず、新signature、例外、または追加承認された再調査だけの候補とする。

今後の各Kit processでは総数、normal exit、known residual、unknown failure、native crash、device lost/TDRを条件・driver・Kit build別に累積する。ハードウェア変更後の既存統制runをhistoryとして数えると、Phase 6DW 14件、6DY 8件、6DZ control、6EA direct controlの計24件中、normal exit 22、full dumpでsignature確認済み1、軽量signature導入前で遡及分類しない残留1である。既知signature率は`1 / 24 = 4.17%`だが、これは新schemaで得たrateではなく歴史baselineである。

再調査triggerは、新signatureまたは新module/offset、result保存またはstage close前のhang、既知residual 2回連続、policy分類済み20 process以上で5%超、fatal／Fabric access violation／Windows exception／TDR／device lost、安全なPID特定・停止不能、interactive productionでの反復、driver／Kit更新後の悪化である。それまではWPR/ETW、DLSS以外を含むNGX内部、telemetry serviceの追加調査を開始しない。distribution前には長時間soakを別途必要とし、この運用を「完全に正常」「完全に安全」と表現しない。

Phase 6EBのfixtureはnormal、既知NGX、未知signature、shutdown marker欠落、functional gate失敗、Windows exception、未知module/offset、dump、timeout、残留停止失敗、入力破損、複数runの既知・未知混在を24/24で確認した。既存正常runnerの最終`kit_only`実processは1.423秒、exit 0、`normal_exit`、性能母集団accepted、fatal/dump/upload 0である。既知hang条件は再実行せず、保存済みWinDbg summaryだけをsignature定義の根拠にした。Phase 6EA resource safety 7/7・静的契約6/6、標準suite 8 process・78/78件・302.2秒、日誌338 reference／JSON 180／SVG 146の静的検査も合格した。Production app SHA-256は`94162F82...F02A`で前後一致した。

### Phase 6ECで検出したexception matcherの再開blocker

Phase 6ECのexact Phase 6DY controlはprobe完了、`shutdown_complete`、OS exit 0、fatal/dump/upload 0だったが、GPU inventoryの`Sub System Id : 0xC75C1462`が一般的な`0xC[0-9A-F]{7}`patternに一致し、`windows_exception_present=true`となった。現logで一致したのはこの1行だけであり、観測上はPCI subsystem identifierである。ただしPhase 6ECは本policyを変更しないため、結果は`unknown_shutdown_failure`のまま保持し、同条件を再実行していない。

再開前の別Phaseでは、Windows exceptionを明示的文脈、Crash Reporter、exit code、access violation等で検出しつつ、hardware identifierをnegative fixtureで除外する必要がある。この修正がないままlog levelを下げて証拠行を隠す回避は採用しない。既知NGX signature判定、full-dump抑制、PID/path/start-time、Phase 6EA resource guardは変更対象ではない。

### Phase 6ED correction

上記blockerはPhase 6EDでpolicy evidence抽出だけを修正した。任意の裸`0xC........`をpositiveにせず、exception code／Unhandled exception／process exit code／access violationの明示的文脈を要求する。`0xC0000005`もRTX 2070 subsystem ID、Device/Vendor/Bus ID、UUID、PCI、driver/firmware、address/hash/color/bitmask値ならnegativeとする。走査は`File.ReadLines()`であり、log全体をメモリへ保持しない。

空logはreadableなnegative evidence。欠落／read不能logは`windows_exception_present=false`でもevidence unavailableなので`no_windows_exception=false`となり、引き続きunknownへfail closedする。実例外だけがfault module/offsetを`unparsed`にする。既存24件を含む31/31 contractとPhase 6EC Aのread-only offline再分類13/13が合格した。保存runはnormal exitへ評価可能になったが、Phase 6EC A/B/C自体はまだ再実行していない。
