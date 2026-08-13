# Phase 6FN — routed settled-baseline three-iteration qualification

Phase 6FL/6FM の contract、artifact、safe-stop は履歴として凍結し、Phase 6FM attempt01 は新しい正式母集団へ再利用しない。Phase 6FN の単一目的は、formal analyzer を独立責務へ分離し、実 artifact 形状の end-to-end preflight 後に、3 回の readback / fuel alias lifetime を settled baseline で評価することである。

## 判定層

- `phase_schema_routing`: formal metadata は `campfire.phase6fn.attempt-metadata.v1` / `phase6fn`、埋込み probe report は既存実装の `campfire.phase6fk.point-collision-run.v1` / `phase6fk` だけを受理する。Phase 6FL evaluator は historical diagnostic 専用で、formal 判定には使わない。
- `startup_prerequisite`: representative ingestion、fresh telemetry、正しい source と identity、payload SHA-256 を operation 前に確認する。この failure だけが最大2 launchまで置換可能である。
- `operation_integrity`: frame 120/360/540 の3 operation、condition別 call count、ordered release、frame 620 の非operation sentinelを検査する。settling時間やresource sample数は扱わない。
- `explicit_settling_integrity`: `settling_started` と `settling_end` だけを使い、iteration番号、開始/終了frame、4秒、8 outer samples、60 renderer updates、resource snapshotを判定する。iteration 3 の正式終端は `settling_end(frame=620, settling_iteration=3)` である。
- `pointer_alias_integrity`: R1/R2 の weak residual 0、R2 の正のbuilt-in pointer、一致、same object、shares memory、metadata一致、隣接CPU/GPU増分、ordered releaseを判定する。
- `paired_settled_accumulation`: 同じsequenceのR0を控除し、candidate field logical-byteの正の増加も控除したsettled stepだけを比較する。
- `absolute_resource_safety`、`lifecycle`、`cleanup`: resource、fatal/dump/upload、stage close、extension shutdown、OS exit、残留processを別々に判定する。

未知schema、raw/JSONL parse failure、analyzer/runner/probe failureはdiagnostic harness failureとしてfail closedにし、startup replacementへ送らない。legacy lookup warningがformal failureへ昇格する経路は持たない。

## runtime前契約

balanced order は `R0→R1→R2`、`R1→R2→R0`、`R2→R0→R1`。各conditionは3 process、各processはoperationをframe 120/360/540で正確に3回だけ実行する。frame 620はiteration 3のsettling終端であり、4回目のcontrol/readback/NumPy operationは禁止する。representative processは9、startup replacementは最大2、総launchは最大11である。

material thresholdは Phase 6FM と同じ91,184,640 bytes（fuel logical bytes 41,398,016 + marker粒度8 MiBを根拠とする）。candidate 2 stepが正、R0控除後の両stepがthreshold超過、3−1が2段分超過、field増加控除後も成立し、同じconditionで2 sequence以上再現した場合だけformal accumulation failureとする。pre-operation、slope、単独process、初回cache後plateau、R0にもある変動は単独failureにしない。

R2の9 iterationすべてで pointer/identity/shares-memory/shape/dtype/strides/size/nbytes一致、`np.asarray()`隣接CPU 8 MiB以内、GPU 8 MiB以内、weak residual 0を要求する。

安全上限は Kit 14 GiB、unique tree 16 GiB、runner/diagnostic各512 MiB、physical/commit headroom各8 GiB、stage close 180秒を維持する。native timeout時だけbounded CDB（module 30秒、all-thread stack 45秒、detach recovery 30秒）を使い、full dumpは自動取得しない。

## E2E preflight

Kit起動前に、probeと同じdirectory、raw JSON、resource/extension JSONL、runner evidence、guard summary、process resource traceを生成し、analyzer CLI全体へ通す。合格9-process populationに加え、iteration 3 settling欠落、iteration不一致、短時間、resource sample不足、update不足、frame 620 operation、call count、pointer欠落/0/不一致、weak residual、lifecycle、cleanup、resource ceiling、raw欠落/parse、未知routing、nonreplaceable failure後のlaunchを個別fixtureで検査する。全件合格し、contractとruntime implementation SHA-256が一致するまでformal Kit runを禁止する。

## 適用範囲

9 representative processが全層を通過した場合だけ、固定4本fixtureにおける同一process内public readback 3回、ordered release 3回、fuel zero-copy alias 3回、settled baselineでの操作固有階段状累積なし、normal shutdownをqualifiedとする。4回以上、毎frame、他channel、field永続化、長時間、production統合は未qualifiedのままで、次Phaseは自動開始しない。production、Flow、Point、CollisionProxy、V3、既定値は変更しない。
