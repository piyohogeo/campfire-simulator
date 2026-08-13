# Phase 6FP pre-readback allocation calibration

Phase 6FOの`15,127,232,512 bytes` Kit Private Bytes safe stopを遡及変更せず、readback前の診断構成と通常のFlow/Kit起動高水位を分離するdefault-off校正を行った。契約`campfire.phase6fp.pre-readback-allocation-contract.v1`（SHA-256 `3ED07008...5A55F45`）は14 GiB Kit、16 GiB unique tree、各512 MiB runner/diagnostic、physical/commit各8 GiB floorを維持する。S93/S100、production、Point payload、Flow設定、CollisionProxy、V3は変更していない。

## 事前に確定した境界

Phase 6FNのreadbackなし基準は、すでに修正版4本fixture、`allow_self_center`、offset `-0.0125 m`、1,344/1,440 active Points、payload SHA-256 `0D3B074B...B876C389`を使うS93である。したがって「S93 stage/Point追加」は物理差を作らず、同一性を検査するzero-delta controlとして固定した。

`SpatialNeighborhoodCollector`のconstructorは26頂点Mesh、変換行列、public member名、空のcacheを保持するだけである。near-Meshのindex/world/local/signed-distance配列はpublic NanoVDB gridのorigin、basis、shapeが得られた後、`_geometry_for_grid()`で初めて遅延生成される。readback前にはそのgrid metadataが存在しないため、Phase 6FPは架空のfield bodyを割り当てず、dtype/ownership planと`logical_bytes=0`を記録した。capture準備もdisabled manifestだけで、capture call、frame schedule、pixel bufferは0である。

## 凍結matrixとsafe stop

forward、reverse、interleavedの24 processを事前固定した。startup prerequisiteだけに置換枠2を許し、resource、stage close、例外は置換しない。各processはreadback 0、frame 60/96、同じstartup順序、同じpayloadである。

| attempt | condition | Kit peak bytes | GiB | frame 60/96 blocks | stage close s | lifecycle |
|---|---|---:|---:|---:|---:|---|
| 01 | C0 baseline | 14,826,885,120 | 13.809 | 688 / 948 | 2.612 | normal exit |
| 02 | C1 collector object | 14,869,184,512 | 13.848 | 688 / 948 | 12.565 | normal exit |
| 03 | C2 spatial metadata | 14,930,382,848 | 13.905 | 688 / 948 | 5.138 | normal exit |
| 04 | C3 channel metadata | 14,866,845,696 | 13.846 | 688 / 948 | 2.035 | normal exit |
| 05 | C4 buffer plan | 14,890,889,216 | 13.868 | 688 / 948 | 43.722 | normal exit |
| 06 | C5 capture prep | 14,840,684,544 | 13.821 | 688 / 948 | 156.452 | normal exit |
| 07 | C6 S93 identity | 14,898,229,248 | 13.875 | 688 / 948 | 9.382 | normal exit |
| 08 | C7 6FO-equivalent | 14,871,994,368 | 13.851 | 688 / 948 | 2.338 | normal exit |
| 09 | C7 6FO-equivalent | 14,894,997,504 | 13.872 | 688 / 948 | 2.893 | normal exit |
| 10 | C6 S93 identity | 14,583,508,992 | 13.582 | 688 / 948 | 6.335 | normal exit |
| 11 | C5 capture prep | 14,869,659,648 | 13.848 | 688 / 948 | 180.007 | timeout / exact cleanup |

attempt11は`stage_close_request_before`で180秒timeoutした。Flow/provider/collector参照の解放は完了済みだった。CDBはmodule取得に成功したが、all-thread stackは45秒timeoutしnative framesを取得できなかった。detach recoveryは完了し、outer guardは起動時に観測したKit、conhost、telemetry transmitterだけを停止した。known NGX 5-token signatureは不一致で、lock ownerは不明である。最終Kit/CDB/GPU helper残留は0、fatal/dump/automatic uploadは0である。この非置換lifecycle failureで正式母集団は10/24に安全停止し、残り13 processは開始していない。

## 判定

確認済みの正常10 runではactive blockが完全一致しながら、Kit peakが`14,583,508,992～14,930,382,848 bytes`（13.582～13.905 GiB、range `346,873,856 bytes`）変動した。C7の2 runはいずれも14 GiB未満で、旧Phase 6FOの15,127,232,512 bytesを再現しなかった。診断要素の論理allocationはreadback前0 byteで、追加要素に追従する単調・再現可能なCPU/GPU増加も観測されなかった。RTX 3090 dedicated memory peakは7,066～7,145 MiB、shared memoryはbounded public telemetryから取得不能で推定していない。unique tree最大は15,093,272,576 bytes、minimum physical/commit headroomは81,296,306,176/100,617,502,720 bytesだった。

従って、現時点の最有力説明は4本Flow/RTX/Kit allocator/cacheのrun間高水位変動であり、Phase 6FO固有のcollector、metadata、NumPy buffer、capture準備の事前allocationではない。ただし各条件3 runを満たしていないため「完全特定」とはしない。14 GiBまでの最小正常余白は102,002,688 bytes（97.277 MiB）しかなく、旧6FOは94,846,976 bytes超過した。14 GiBを維持したまま6FOを再開できる安全余裕は示せていない。

## 継続条件

Phase 6FOは自動再開しない。再開には、(1) readbackなしstage-close問題を別lifecycle境界として扱い、正常終了を損なわないこと、(2) 新しい空rootで未完の3-run分布を完了すること、(3) 14 GiBを超える通常高水位を許容するなら新しい独立contractで上限候補を事前qualificationすること、が必要である。16 GiBは候補に留まり、このPhaseでは採用していない。数値測定と動画のprocess分離は、capture call 0でも同じ高水位だったため14 GiB問題の主対策にはならない。S93/S100のscalar/velocity/flux、比較動画、production統合は未実行である。

## 回帰

Release buildは8.08秒、Phase 0 RTXはpass、Phase 3はdry/wet mass-balance error 0、authority SHAを維持し、Flow active blocks final/peakは214/306だった。focused Phase 6Fは131/131、標準suiteは8 process・78/78（339.7秒）で合格した。production app SHA-256は`94162F82...F02A`で不変。内部診断のみで画面差がないため動画とlatest demoは変更していない。
