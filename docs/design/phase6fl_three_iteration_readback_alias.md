# Phase 6FL — three-iteration readback / fuel-alias pilot

Phase 6FK（`b32cfcb`）の9/9単回qualificationは凍結し、そのsampleを流用しない。Phase 6FLは、同一processで低回数の操作を反復したとき、handleまたはalias解放後のsettled baselineが階段状に蓄積しないかだけを診断する。production、Flow、Point payload、CollisionProxy、V3、resource ceilingは変更しない。

## Runtime前に凍結する契約

- 条件: R0（同時刻control markerのみ）、R1（public readbackを1回取得して解放）、R2（readback後にfuelへ`np.asarray()`を1回だけ適用して順序どおり解放）。
- iteration: frame 120 / 360 / 600の正確に3回。4回以上は未qualificationのまま残す。
- 母集団: 各条件3 representative process。順序はR0/R1/R2、R1/R2/R0、R2/R0/R1。
- startup prerequisiteだけ最大2 replacement、総launch最大11。operation開始後、pointer、weak reference、resource、lifecycle、fatal、cleanupの失敗は置換不能で即停止する。
- 各settling: timelineとFlowを動かしたまま4秒以上、outer resource sample 8件以上、renderer update 60回以上。iteration 1/2のsettling endは次iterationの`sample_started`、iteration 3は有限の追加観測終了markerで同期する。
- slopeやrolling slopeはtelemetryだけで、正式gateにはしない。

## 累積判定

Phase 6FKで観測したfuel logical bufferは41,398,016 bytes、同期markerの許容粒度は8 MiBである。material stepは`2 × 41,398,016 + 8 MiB = 91,184,640 bytes`と事前固定する。pre-operation baselineまたはsettling-end baselineについて、iteration 2−1と3−2がともにmaterial stepを超え、かつ3−1がその2倍を超える場合だけ、再現する二段の階段状累積として不合格にする。初回cache後のplateau、減少を含むR0相当の自然変動は受理する。R0とのprocess間比較はallocator／Flow変動のcontextであり、操作固有costには使わない。

R2の全9 iterationは、正のsource/converted pointer、同一pointer、同一Python object、`shares_memory=True`、shape/dtype/strides/size/nbytes一致、weak-reference残留0を要求する。absolute resource ceiling、正常stage close、extension shutdown、normal OS exit、残留process 0は従来どおりhard gateである。

## Prelaunch safe stop

最初のartifact rootはR0へ空文字の`-ReadbackFrames`を渡したため、PowerShell parameter bindingで停止した。Kit起動は0回、GPU/Flow operationも0回だった。旧analyzerはraw未生成のguard failureをstartup prerequisiteと誤分類し3 replacementを消費した。このrootとv1 contractは凍結し、正式母集団には使用しない。v2ではR0の空引数を省略し、raw未生成のdiagnostic process failureをnonreplaceable absolute safety failureとしてfail closedにする。

2番目のartifact rootは共有case runnerの凍結済み`ReportPhase` ValidateSetがPhase 6FKまでであるため、Phase 6FL labelをparameter bindingで拒否した。ここでもKit起動は0回、v2 contractとrootは凍結し、正式母集団へ流用しない。Phase 6FKのhash対象共有runnerは変更せず、v3外側runnerだけがembedded probe compatibility label `phase6fk`を渡す。正式なcontract、attempt metadata、集計schema、artifact phaseは`phase6fl`を維持する。

実測結果は正式run後に追記する。
