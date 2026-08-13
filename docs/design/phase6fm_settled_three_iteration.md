# Phase 6FM — settled post-release three-iteration qualification

Phase 6FKの単回qualificationとPhase 6FLの3/9 safe stopを凍結し、既存artifactを再分類・流用しない。Phase 6FMで変更する判定変数はbaselineの意味だけである。次iteration直前の`pre_operation`はFlow成長、allocator、cacheを含むtelemetryとして保存し、formal accumulation gateには用いない。ordered release、weak-reference確認、4秒以上、resource sample 8件以上、renderer update 60回以上を完了した独立`settling_end` markerだけをformal baselineにする。

R0 / R1 / R2を各3 process、`R0→R1→R2`、`R1→R2→R0`、`R2→R0→R1`で実行する。各processのoperationはframe 120 / 360 / 540の正確に3回。frame 620は`settling_end`だけを確定する非operation sentinelであり、4回目のcontrol/readbackではない。startup prerequisiteだけ最大2件を置換でき、総launchは11以下である。

material thresholdはPhase 6FKの41,398,016-byte fuel bufferと8 MiB同期粒度から`2 × 41,398,016 + 8 MiB = 91,184,640 bytes`に固定する。正式な階段状累積には、candidate settled値が2段連続増加し、R0を差し引いた2 stepとtotalがthresholdを超え、さらにcandidate fuel logical-byteの正の成長を差し引いても同じ条件が残り、同一conditionで2 sequence以上再現することをすべて要求する。active blocksは併記するが、固定費が大きいためbytes/blockをhard gateにしない。weak/pointer/marker違反はメモリ差に関係なく即時operation failureである。

R0はreadback禁止なのでpublic APIからfield element count/logical bytesを取得できない。推定値で埋めず、`unavailable_without_public_readback`としてnullを保存する。R1/R2は各operationの公開readback metadataを次のsettling-endへ引き継ぐ。このmetadataはFlow内部occupancyの主張ではない。

14 GiB Kit、16 GiB tree、runner/diagnostic 512 MiB、physical/commit floor 8 GiB、stage close 180秒、bounded CDB 30/45/30秒を維持する。4回以上、他channel、field保存、forced GC、private API、production、動画は対象外である。contract SHA-256は`9251855314FD710B6C3D1A36FF156DD6833166A7F37B216BE3F9CC09BE2CC5F5`。
