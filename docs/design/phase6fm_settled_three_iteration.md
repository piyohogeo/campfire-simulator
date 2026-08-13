# Phase 6FM — settled post-release three-iteration qualification

Phase 6FKの単回qualificationとPhase 6FLの3/9 safe stopを凍結し、既存artifactを再分類・流用しない。Phase 6FMで変更する判定変数はbaselineの意味だけである。次iteration直前の`pre_operation`はFlow成長、allocator、cacheを含むtelemetryとして保存し、formal accumulation gateには用いない。ordered release、weak-reference確認、4秒以上、resource sample 8件以上、renderer update 60回以上を完了した独立`settling_end` markerだけをformal baselineにする。

R0 / R1 / R2を各3 process、`R0→R1→R2`、`R1→R2→R0`、`R2→R0→R1`で実行する。各processのoperationはframe 120 / 360 / 540の正確に3回。frame 620は`settling_end`だけを確定する非operation sentinelであり、4回目のcontrol/readbackではない。startup prerequisiteだけ最大2件を置換でき、総launchは11以下である。

material thresholdはPhase 6FKの41,398,016-byte fuel bufferと8 MiB同期粒度から`2 × 41,398,016 + 8 MiB = 91,184,640 bytes`に固定する。正式な階段状累積には、candidate settled値が2段連続増加し、R0を差し引いた2 stepとtotalがthresholdを超え、さらにcandidate fuel logical-byteの正の成長を差し引いても同じ条件が残り、同一conditionで2 sequence以上再現することをすべて要求する。active blocksは併記するが、固定費が大きいためbytes/blockをhard gateにしない。weak/pointer/marker違反はメモリ差に関係なく即時operation failureである。

R0はreadback禁止なのでpublic APIからfield element count/logical bytesを取得できない。推定値で埋めず、`unavailable_without_public_readback`としてnullを保存する。R1/R2は各operationの公開readback metadataを次のsettling-endへ引き継ぐ。このmetadataはFlow内部occupancyの主張ではない。

14 GiB Kit、16 GiB tree、runner/diagnostic 512 MiB、physical/commit floor 8 GiB、stage close 180秒、bounded CDB 30/45/30秒を維持する。4回以上、他channel、field保存、forced GC、private API、production、動画は対象外である。contract SHA-256は`9251855314FD710B6C3D1A36FF156DD6833166A7F37B216BE3F9CC09BE2CC5F5`。

## Formal safe stop

新しいroot `artifacts/phase6fm-settled-three-iteration-1` は最初のslot `sequence01_position01_R0_control`だけを起動した。startupはframe 1で269 blocks、frame 120までに1,124 blocksへ成長した`representative_ingestion`で、Point 1,440 / active 1,344、revision 1、stage / payload / Flow / Emitter identityと供給量も一致した。readbackなしcontrol operationはframe 120 / 360 / 540で正確に3回、frame 620はoperationを行わないsentinelとして完了した。

独立`settling_end`の実測は次のとおりで、Phase 6FM固有の明示評価は3件とも合格した。

| iteration | frame | settling seconds | resource samples | renderer updates | Private Bytes | active blocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 360 | 15.923690 | 51 | 240 | 13,666,217,984 | 1,364 |
| 2 | 540 | 12.132670 | 39 | 180 | 13,699,375,104 | 1,539 |
| 3 | 620 | 5.515351 | 18 | 80 | 13,701,984,256 | 1,386 |

R0はpublic readbackを禁止しているため、field element count / logical bytesは3件ともnullで、sourceは`unavailable_without_public_readback`である。settled stepは+33,157,120 / +2,609,152 bytes、totalは+35,766,272 bytesで、91,184,640-byte material thresholdを下回った。ただしR1/R2と複数sequenceがないため、これはpaired qualificationではなくR0 partial telemetryだけである。

formal safe stopはPhase 6FL互換analyzerのlegacy settling lookupで発生した。互換層はiteration 3の終端を`sample_started(frame=620)`で検索したが、Phase 6FM contractはframe 620を非operation sentinelとし、`settling_end(frame=620, settling_iteration=3)`だけを要求する。このため互換層が`required_iteration_marker_missing`、`settling_resource_samples`、`settling_wall_time`を生成し、後段のexplicit evaluatorが3件すべて合格していてもclassificationが`operation_failure`のまま残った。synthetic preflightはexplicit evaluatorを検査したが、legacy classifierとの統合を実artifact形状で検査しておらず、この境界を捕捉できなかった。

この不整合はFlowやlifecycleの不成立ではない。attempt01はstage close 3.338974秒、extension shutdown、exit code 0、normal OS exit、exact cleanupまで完了した。Kit peak 14,475,513,856 bytes、tree peak 14,639,017,984 bytes、runner peak 150,720,512 bytes、diagnostic peak 16,896,000 bytesで、physical / commit floorも維持した。CDB、fatal、dump、automatic upload、device lost、TDR、residualは0だった。

それでも凍結contractはdiagnostic / harness failureを置換不能と定めているため、attempt01を置換・再分類・再実行せず、後続8 slotを開始しなかった。正式結果は1 launch、0/9 representative、startup replacement 0、three-readback / three-fuel-alias lifetime未qualifiedである。次の明示承認Phaseでは、新contract SHAを発行し、legacy operation integrityとexplicit settling classificationを分離したend-to-end fixtureをruntime前に必須化する。Phase 6FMのartifact、contract、safe-stop判定は変更しない。

## Regression

Release buildは8.33秒で合格した。Phase 0 RTXはRTX 3090 / CUDA 0で合格し、Phase 3はdry / wet mass-balance error 0、authority SHA-256 `0dec57f324fadbdb0c7f5908ac16fe9437d81726cfec047fda5c88f52e84be10` / `148585f8ea43ddda826db198be6a6c03c151ce2c857009e171a9c93cfd2b20c9`、Flow active blocks final / peak 231 / 359、peak fuel 1.0を維持した。focused Phase 6F / 6EA / 6EB / 6EL contractは167/167、標準suiteは8 process・78/78を348.9秒で合格した。日誌静的検査は445 references、269 IDs、221 JSON、177 SVG、2 ZIPを検査し、欠落・parse failure・duplicate IDは0。production SHA-256は`94162F82AF95D5ABB3798FCB5CA71F7821B7813FD8623D1387BC723288ADF02A`のまま、Kit / CDB / GPU-helper残留、新規dumpは0だった。画面上の変更がないため動画は生成せず、latest demo pointerを維持した。
