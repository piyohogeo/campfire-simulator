# Phase 6FL — three-iteration readback / fuel-alias pilot

Phase 6FK（`b32cfcb`）の9/9単回qualificationは凍結し、そのsampleを流用しない。Phase 6FLは、同一processで低回数の操作を反復したとき、handleまたはalias解放後のsettled baselineが階段状に蓄積しないかだけを診断する。production、Flow、Point payload、CollisionProxy、V3、resource ceilingは変更しない。

## Runtime前に凍結する契約

- 条件: R0（同時刻control markerのみ）、R1（public readbackを1回取得して解放）、R2（readback後にfuelへ`np.asarray()`を1回だけ適用して順序どおり解放）。
- iteration: frame 120 / 360 / 540の正確に3回。frame 620は最終settling endを同期するreadbackなしsentinelであり、4回目のoperationではない。4回以上は未qualificationのまま残す。
- 母集団: 各条件3 representative process。順序はR0/R1/R2、R1/R2/R0、R2/R0/R1。
- startup prerequisiteだけ最大2 replacement、総launch最大11。operation開始後、pointer、weak reference、resource、lifecycle、fatal、cleanupの失敗は置換不能で即停止する。
- 各settling: timelineとFlowを動かしたまま4秒以上、outer resource sample 8件以上、renderer update 60回以上。iteration 1/2のsettling endは次iterationの`sample_started`、iteration 3は有限の追加観測終了markerで同期する。
- slopeやrolling slopeはtelemetryだけで、正式gateにはしない。

## 累積判定

Phase 6FKで観測したfuel logical bufferは41,398,016 bytes、同期markerの許容粒度は8 MiBである。material stepは`2 × 41,398,016 + 8 MiB = 91,184,640 bytes`と事前固定する。同じsequenceのR0 stepをR1/R2 stepから差し引いた値について、iteration 2−1と3−2がともにmaterial stepを超え、かつ3−1の差がその2倍を超える場合だけ、操作固有の二段の階段状累積として不合格にする。R0単独のFlow／allocator変動はtelemetryでありformal failureにしない。初回cache後のplateau、減少を含むR0相当の自然変動は受理する。process peak差は操作固有costには使わない。

R2の全9 iterationは、正のsource/converted pointer、同一pointer、同一Python object、`shares_memory=True`、shape/dtype/strides/size/nbytes一致、weak-reference残留0を要求する。absolute resource ceiling、正常stage close、extension shutdown、normal OS exit、残留process 0は従来どおりhard gateである。

## Prelaunch safe stop

最初のartifact rootはR0へ空文字の`-ReadbackFrames`を渡したため、PowerShell parameter bindingで停止した。Kit起動は0回、GPU/Flow operationも0回だった。旧analyzerはraw未生成のguard failureをstartup prerequisiteと誤分類し3 replacementを消費した。このrootとv1 contractは凍結し、正式母集団には使用しない。v2ではR0の空引数を省略し、raw未生成のdiagnostic process failureをnonreplaceable absolute safety failureとしてfail closedにする。

2番目のartifact rootは共有case runnerの凍結済み`ReportPhase` ValidateSetがPhase 6FKまでであるため、Phase 6FL labelをparameter bindingで拒否した。ここでもKit起動は0回、v2 contractとrootは凍結し、正式母集団へ流用しない。Phase 6FKのhash対象共有runnerは変更せず、v3外側runnerだけがembedded probe compatibility label `phase6fk`を渡す。正式なcontract、attempt metadata、集計schema、artifact phaseは`phase6fl`を維持する。

3番目のartifact rootのattempt01 R0は、3 control marker、全settling、stage close（2.362秒）、extension shutdown begin/end、OS exit 0、残留0まで完了した。しかしv3 analyzerがextension JSONLの既存キー`name`を`marker`としてのみ読んだため、`extension_shutdown_incomplete`と誤分類してfail closedした。rootとv3 contractは正式safe stopとして凍結し、後から正式合格へ変更しない。v4 analyzerは`name`を正規化して読み、修正確認は別のoffline診断出力へ保存する。

## Formal result: paired pre-operation safe stop

新しいformal root 4はsequence 1のR0 / R1 / R2を各1 process実行した。3 processともrepresentative startup、正確な3 operation、settling、stage close、extension shutdown、normal OS exit、cleanup residual 0を満たし、startup replacement、CDB、fatal、dump、upload、device lost、TDRは0だった。R2の3 iterationはすべてpositive equal pointer、same Python object、shared memory、weak residual 0で、`np.asarray()`隣接CPU増分は0 / -1,056,768 / -4,206,592 bytes、GPU増分は全件0だった。fuel shapeはFlow場の成長に伴い10,349,504 / 12,313,408 / 13,916,672要素、logical bytesは41,398,016 / 49,253,632 / 55,666,688だった。

一方、R0を差し引いたpre-operation baseline stepは、R1が210,575,360 / 111,161,344 bytes（total 321,736,704）、R2が169,799,680 / 108,544,000 bytes（total 278,343,680）だった。いずれも2 stepがmaterial threshold 91,184,640 bytesを超え、totalも182,369,280 bytesを超えたため、凍結済みpaired accumulation gateに不合格となった。R0 / R1 / R2のsettled paired stepは同じ二段累積を示さなかったが、formal resultを事後変更する根拠には使わない。後続sequence 2 / 3は開始せず、正式populationは3/9でsafe stopとした。3回のreadbackまたはfuel alias lifetimeはqualifiedではなく、4回以上とproduction統合も未qualifiedである。

stage closeはR0 / R1 / R2で2.272 / 2.473 / 2.660秒。Kit peakは14,778,347,520 bytes、14 GiB上限までの最小余裕は254,038,016 bytes、tree peakは14,941,483,008 bytesだった。全settlingは5.25秒以上・17 sample以上で、hard resource/lifecycle gateは合格した。次へ進むには、pre-operation baselineとsettled baselineのどちらを操作固有累積の正式根拠にするかを、今回の結果へ遡及しない新contractで事前定義する明示承認が必要である。

prelaunch root 1 / 2、analyzer false safe stopのroot 3、formal root 4はすべて別rootのまま凍結した。production、Phase 6FK、latest demo pointerは変更していない。内部resource診断だけで画面差がないため新動画は作成しない。

最終回帰はRelease build 7.85秒、Phase 0 RTX合格、Phase 3 25.923秒、focused Phase 6FA〜6FL / 6EA / 6EB / 6EL 156/156、標準8 process 78/78（346.9秒）、日誌静的検査に合格した。Phase 3はdry/wet mass-balance error 0、authority SHA-256 `0dec57f3...e84be10` / `148585f8...fd2b20c9`、Flow active blocks final/peak 271/356、peak fuel 1.0だった。production app SHA-256は`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`のまま、最終Kit/CDB/GPU-helper残留は0である。
