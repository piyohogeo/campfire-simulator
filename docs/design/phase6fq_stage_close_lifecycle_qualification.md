# Phase 6FQ stage-close lifecycle qualification

Phase 6FP attempt11の`readback=0`、`C5_capture_prep`条件は、Flow測定を完了した後、既存の8 renderer update、Flow/provider/collector参照解放を経て`close_stage_async()`を要求し、180.007436秒でtimeoutした。この結果、Phase 6FPのmemory calibrationとnative lifecycleを分離する。Phase 6FPのartifact、safe stop、14 GiB判定は変更しない。

## Frozen contract

`campfire.phase6fq.stage-close-lifecycle-contract.v1`は、修正版4本fixture、S93の1,344/1,440 Point、frame 60/96、readback 0、capture call 0を固定する。14 GiB Kit、16 GiB unique tree、runner/diagnostic各512 MiB、physical/commit各8 GiB floor、stage close 180秒、bounded CDB、exact process identity cleanupもPhase 6FPから継承する。production、S93/S100比較、Point payload、Flow、CollisionProxy、V3、物理閾値は変更しない。

比較はPhase 6FN相当baseline、C5直前のlevel 4、C5 disabled metadata、bounded capture manifest、active viewportの追加aliasだけを持つprovider準備、pre-close drain 0/8、Flow/provider/collectorのrelease-before/after-closeである。provider準備は既に取得済みのpublic active viewportへの追加Python参照に限定し、capture API、pixel buffer、動画生成を呼ばない。各条件2 run、最大3 runとし、順序を正順・逆順に固定した。同じunknown stage-close timeout、resource failure、fatal、dump、upload、device lost、TDR、cleanup residualは置換せず直ちに停止する。startup prerequisiteだけは最大1 replacementを許す。

## Marker and interpretation boundary

既存のPhase 6FO probe、case runner、Phase 6EJ/6EL guard、CDB helper、shutdown classifierを直接再利用する。新しい分岐はcapture準備状態と参照解放順だけで、timeline stop、renderer drain、`close_stage_async()`、post-close update、app closeの処理本体は共有される。capture関連object、Flow、provider/readback/collectorの作成・解放、stage close、USD detach、extension shutdown、OS exit、cleanupを逐次markerへ保存する。

timeout時はmodule一覧、all-thread stack、detachをbounded fileへ直接出力する。CDB timeoutやprivate symbol不足を既知NGXへ読み替えず、既存5-token signatureがすべて実stackに現れた場合だけknown候補とする。正常だが長いcloseと180秒timeoutを区別し、少数runで再現しない場合は無期限に反復しない。

Phase 6FQが全slotで正常終了した場合だけ、次の独立PhaseでPhase 6FN baseline、C7 Phase 6FO-equivalent、readback予定直前のno-readback条件を各3 run取得し、14 GiBと16 GiB候補を事前qualificationする。Phase 6FOはそのresource契約まで完了しない限り再開しない。
