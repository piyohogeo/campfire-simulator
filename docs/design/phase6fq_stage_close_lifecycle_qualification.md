# Phase 6FQ stage-close lifecycle qualification

Phase 6FP attempt11の`readback=0`、`C5_capture_prep`条件は、Flow測定を完了した後、既存の8 renderer update、Flow/provider/collector参照解放を経て`close_stage_async()`を要求し、180.007436秒でtimeoutした。この結果、Phase 6FPのmemory calibrationとnative lifecycleを分離する。Phase 6FPのartifact、safe stop、14 GiB判定は変更しない。

## Frozen contract

`campfire.phase6fq.stage-close-lifecycle-contract.v1`は、修正版4本fixture、S93の1,344/1,440 Point、frame 60/96、readback 0、capture call 0を固定する。14 GiB Kit、16 GiB unique tree、runner/diagnostic各512 MiB、physical/commit各8 GiB floor、stage close 180秒、bounded CDB、exact process identity cleanupもPhase 6FPから継承する。production、S93/S100比較、Point payload、Flow、CollisionProxy、V3、物理閾値は変更しない。

比較はPhase 6FN相当baseline、C5直前のlevel 4、C5 disabled metadata、bounded capture manifest、active viewportの追加aliasだけを持つprovider準備、pre-close drain 0/8、Flow/provider/collectorのrelease-before/after-closeである。provider準備は既に取得済みのpublic active viewportへの追加Python参照に限定し、capture API、pixel buffer、動画生成を呼ばない。各条件2 run、最大3 runとし、順序を正順・逆順に固定した。同じunknown stage-close timeout、resource failure、fatal、dump、upload、device lost、TDR、cleanup residualは置換せず直ちに停止する。startup prerequisiteだけは最大1 replacementを許す。

## Marker and interpretation boundary

既存のPhase 6FO probe、case runner、Phase 6EJ/6EL guard、CDB helper、shutdown classifierを直接再利用する。新しい分岐はcapture準備状態と参照解放順だけで、timeline stop、renderer drain、`close_stage_async()`、post-close update、app closeの処理本体は共有される。capture関連object、Flow、provider/readback/collectorの作成・解放、stage close、USD detach、extension shutdown、OS exit、cleanupを逐次markerへ保存する。

timeout時はmodule一覧、all-thread stack、detachをbounded fileへ直接出力する。CDB timeoutやprivate symbol不足を既知NGXへ読み替えず、既存5-token signatureがすべて実stackに現れた場合だけknown候補とする。正常だが長いcloseと180秒timeoutを区別し、少数runで再現しない場合は無期限に反復しない。

Phase 6FQが全slotで正常終了した場合だけ、次の独立PhaseでPhase 6FN baseline、C7 Phase 6FO-equivalent、readback予定直前のno-readback条件を各3 run取得し、14 GiBと16 GiB候補を事前qualificationする。Phase 6FOはそのresource契約まで完了しない限り再開しない。

## Runtime result: lifecycle safe stop

最初のrootは空文字の`ReadbackFrames`をPowerShell parameterへ渡したため、Kit起動前のparameter bindingで停止した。process残留とproduction接触は0であり、このharness不整合を独立修正してroot 2を最初から開始した。

root 2は18 slot中7 processを起動した。attempt01～06はすべてrepresentative startup、948 active blocks at frame 96、readback/capture call 0、stage close、extension shutdown、normal OS exit、residual 0を満たした。stage close時間は順に`35.7698631, 2.1987167, 2.8197243, 5.1710951, 2.1491088, 3.911707`秒だった。C5 disabled metadata、bounded manifest、追加active-viewport aliasはすべて正常終了し、capture準備に追従する再現可能な停止は確認されなかった。pre-close drainを0にしたattempt06も正常終了したが、1 sampleだけなのでdrain除去を安全な修正とはしない。

attempt07 `L6_c5_normal_drain_control`は、capture preparation `none`、8 renderer updates、release-before-closeという既存順序で、`stage_close_request_before`後に停止し、`stage_close_timeout`まで`180.023808`秒だった。最後のFlow場は948 blocks、readback/capture/pixel/videoは0である。これはPhase 6FP attempt11と同じlifecycle境界だが、capture準備なしでも発生したため、C5 metadataまたはcapture providerを必要条件から除外できた。release-after-closeのablationは後続停止により未実行であり、安全な終了順序はqualifiedしていない。

timeout時の診断はPID、creation time、full executable pathを確認し、Kit logの排他lockを記録して継続した。CDB module passは30.4008857秒でtimeoutし、CDB process自体は消滅したが、complete module list、all-thread stack、explicit detach markerは得られなかった。したがって既知NGX 5-token signatureは成立せず、module、offset、wait ownerは未確定である。full dumpと自動uploadは0。outer guardは起動時から観測したKit、conhost、telemetryの正確なPIDだけを停止し、remaining 0を確認した。

確認済み事実は、同じfixtureと物理入力でもstage closeが2.149～35.770秒で正常終了するrunと180秒timeoutするrunがあり、timeoutはreadback/capture preparationなしでも発生すること、timeout時もKit peak 14,668,775,424 bytes、tree peak 14,833,041,408 bytesでresource ceiling内だったことである。最有力の推定はFlow/RTX/Kit内の低頻度で非決定的なnative lifecycle障害だが、CDB stack不足のためmodule、lock、owner threadは断定しない。

Stage 1が全populationを完了しなかったため、memory ceilingのStage 2は開始していない。14 GiBはPhase 6FPで正常high-waterまで97.277 MiBしかなかった事実を維持するが、今回これをqualifiedまたは変更していない。16 GiBも採用しない。Phase 6FOはblockedのままであり、過去6FO artifactは正式比較へ再利用しない。自然再発時にcomplete module/all-thread stackを取得できる診断改善、または安全な一変数shutdown-order候補を別承認で検証する必要がある。

検証はRelease build（7.93秒）、Phase 0 RTX、Phase 3、focused Phase 6F `139/139`、標準suite `78/78`、devlog静的検査に合格した。Phase 3のdry/wet mass balance errorはともに0、authority SHA-256は`0dec57f3...be10`／`148585f8...20c9`、Flow final/peakは292/316 blocksだった。production app SHA-256は前後とも`94162F82...F02A`。最終Kit/CDB/nvidia-smi残留は0で、内部診断だけのため動画とlatest demo pointerは変更していない。
