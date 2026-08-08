# Changelog

- Added Phase 6CX quit-limit qualification: Kit's `quitAfter=900` is an application-update frame cap, and a warm recheck auto-quits before the renderer timeline probe can publish its report.
- Superseded the Phase 6CT STOP baseline and the Phase 6CU-CW causal contrasts; the same production app remains PLAY after the viewport frame and retry with a 30,000-frame cap, both with the normal cache and a newly isolated application shader cache.
- Raised the renderer diagnostic safety cap to 30,000 frames for Phase 6CQ, 6CR, 6CS, 6CU, 6CV, and 6CW while keeping production configuration and the unresolved Resident/Flow visual-continuity qualifications unchanged.
- Added Phase 6CW public root-identity isolation: an isolated derived app named `campfire.simulator` matches the production public app identity, selected settings, important extension IDs, and non-sensitive option-name set but remains PLAY after the viewport frame and retry.
- Kept production unchanged and narrowed the repeated STOP boundary beyond app filename/name to root load origin, config stack, or startup lifecycle not exposed by the matched public identity.
- Added Phase 6CV serialized root-configuration isolation: six Editor-rooted variants covering static settings, generated version lock, package/template metadata, and extension search paths all remain PLAY after the first viewport frame and retry at fixed 1280x720.
- Kept the production app unchanged and narrowed the repeated STOP boundary to production root-app identity or lifecycle outside the serialized `.kit` declarations; continuity and Flow-field checkpoint qualifications remain false.
- Added Phase 6CU derived-app initialization isolation: four Editor-rooted variants covering head/tail declarations, Campfire's direct dependency set and order, and the Extensions Manager dependency all remain PLAY after the first viewport frame and retry at fixed 1280x720.
- Kept the production app unchanged and narrowed the repeated STOP boundary to production root-app initialization, including static declaration application, the generated version lock, package metadata, or root lifecycle.
- Added Phase 6CT application-boundary isolation: a matched editor-base extension set remains PLAY at fixed 1280x720, while matching all 15 non-sensitive runtime-settings differences in the Campfire app still reproduces STOP on both the first and retry playback.
- Kept the `fillViewport=true` workaround unadopted and narrowed the remaining boundary to application initialization order, viewport creation timing, or internal state outside the settings allowlist.
- Added Phase 6CS offline scene and application-boundary isolation: Flow, PhysX, Phase 3 content, Resident ownership, headless mode, FlowUsd alone, the inactive Campfire extension, async renderer init, and fixed viewport mode alone are not sufficient for the repeated post-frame timeline STOP.
- Measured `fillViewport=true` as a Campfire-app workaround that preserves PLAY after the first viewport frame, but did not adopt it because it replaces deterministic 1280x720 capture with UI-sized rendering; production and continuity qualifications remain unchanged.
- Added Phase 6CQ renderer/Hydra boundary isolation: the normal Resident interactive lifecycle remains PLAY to 0.8 s and advances revision 0 to 3 before the first completed viewport frame, then reproduces STOP at 0.0 s immediately after that frame.
- Confirmed that neither a capture callback nor ongoing viewport updates are required for the STOP and that disabling each public StageUpdate node—or all five together—does not remove it; the first completed frame's attachment state remains under investigation.
- Added Phase 6CR plain-stage isolation: the same saved Point/Flow/PhysX stage reproduces the post-viewport-frame STOP without composing the Resident backend, USD adapter, Point sidecar, session, or owner.
- Added Phase 6CP StageUpdate boundary isolation: normal and benchmark apps expose the same five enabled nodes, and the plain stage, composed Resident owner, and renderer-disabled extension interactive lifecycle all remain PLAY with zero STOP events.
- Confirmed the interactive Resident owner actually advances Point revision from 0 to 4; the unresolved PLAY→STOP is therefore currently confined to the RTX capture qualification path, while renderer-enabled production continuity remains unqualified.
- Added Phase 6CO as a default-off negative timeline-boundary audit: explicit stage/session range, auto-update, looping, and `Timeline.commit()` still reproduce PLAY→STOP twice at 0.0 s in the normal Resident Point owner path, while an isolated stage probe remains playing.
- Replaced late-only continuity evidence with a Phase 6CO video that actually spans the layout boundary: 10 RTX frames before the 40 mm edit and 50 immediately after it, with Point/log alignment held within about 1.86 nm and Flow solver-field continuity still unqualified.
- Corrected the Phase 6CM and 6CN development-log captions: both older clips contain only revisions 651–710 after recovery and do not visually prove the revision 300→301 boundary measured by telemetry.
- Added Phase 6CN atomic stopped-layout publication, authoring predeclared `pointPositions` and `layoutRevision` in one rollback-capable transaction without advancing the Resident snapshot revision; the former 40 mm exposure fell to about 1.9 nm.
- Kept Phase 6CN explicitly partial: its real Flow/RTX run records PLAY immediately followed by STOP and does not qualify timeline, Flow solver-field, stage-recovery, or seamless visual continuity.
- Reclassified the visible Phase 6CJ–6CL log jumps and flame resets as an unresolved continuity defect; their consumer, revision, command, and observer results remain valid, but seamless Flow/visual recovery is no longer claimed.
- Added a default-off Phase 6CM frame-aligned continuity diagnostic for PhysX log origins, 360-point group centroids, Resident revision/tick, timeline state, and Flow active blocks; it measured a 40.000 mm pre-publication gap, numerical alignment after revision 301, and zero playing timeline samples while keeping seamless continuity explicitly unqualified.
- Added the Phase 6CL default-off transform observer, filtering real USD notices by stopped log xform, coalescing 13 rapid edit requests into two owner-thread commands, and advancing layout revision only once for the final supported transform.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-08-04

### Added

- Added the Phase 6CL stage-rebind-aware transform notice observer and queue coalescing counters, with running/non-transform filtering and a 14-gate real Flow/RTX qualification video.
- Added the Phase 6CK bounded FIFO and compact Resident Point control window, with owner-thread-only USD execution, structured accepted/rejected results, explicit shutdown discard, and a 13-gate real Flow/RTX qualification video.
- Added the Phase 6CJ explicit qualification path for PLAY-time stopped layout refresh, monotonic layout revision, current-layout recovery factory sharing, normal-owner stage lifecycle observation, and real Flow/RTX continuation after consumer replacement.
- Added the Phase 6CI default-off normal application composition, including complete offline schema authoring before context connection, extension-owned timeline/update lifecycle, primary and Point consumer pre-authoring, and a reproducible 10-gate real-Kit/Flow capture.
- Added the Phase 6CG production-but-unactivated Resident Point module, extracting the generic native surface producer, immutable byte payload, and transactional Point sidecar from benchmark ownership, enforcing pre-authored Flow schema and geometry/ABI validation, and proving byte-exact extraction plus full stage-recovery continuation in real Flow 110.
- Added the Phase 6CF default-off owner-thread stage recovery orchestrator, driving the qualified close/drain/attach lifecycle from real Kit events, retaining pending work across injected consumer-factory failure, retrying the exact immutable payload, and continuing Flow without live structural resync or production activation.
- Added the Phase 6CE default-off replacement-stage recovery path, validating stopped owner-thread consumer handoff, exact pending payload retry across Kit `close_stage_async`/`attach_stage_async`, revision-seeded primary and Point reconstruction, post-attach Flow recovery, and clean shutdown without pending discard.
- Added the Phase 6CD default-off session-owned Point sidecar, coupling its immutable 7,200-point payload to the existing Resident pending/retry lifecycle, rolling it back when primary snapshot publication fails, restricting layout replacement to stopped owner state, failing closed on stage replacement, and recording a real 60-frame Flow/RTX capture.
- Added the Phase 6CC default-off Resident-native surface-array producer, separating static 7,200-point layout from dynamic fuel/temperature/smoke channels, preserving immutable snapshot revisions, and qualifying the single Point Emitter through Flow 110 core simulation and RTX rendering without activating the production path.
- Added the Phase 6CB default-off, preset-independent Flow 110 Point Emitter qualification, proving a fresh pre-connected stage with individual layer, relationship, material, timeline, viewport, core simulation, sparse-field, array-equivalence, revision, notice, and no-live-resync gates from 16 through 7,200 points.
- Added the Phase 6CA production-but-unactivated `ResidentApplicationSession` owner with explicit states, owner-thread enforcement, downstream immutable-snapshot pending/retry, fail-closed normal shutdown, explicit forced discard, pure lifecycle coverage, and real Kit/native failure-recovery gates.
- Added the Phase 6BZ isolated owner-thread Resident checkpoint session, qualifying a non-terminal clone-stage save barrier, failure-safe continuation, and exact uninterrupted-versus-restored next-revision equivalence while deferring production UI and automatic persistence.
- Added the Phase 6BY isolated Resident checkpoint package spike with a versioned two-entry manifest/USDA format, atomic replacement, corruption and revision-consistency rejection, exact model-state validation, and revision-continuous Kit/MSVC restore while leaving production auto-resume disabled.
- Added the Phase 6BX default-off Resident lifecycle recovery gate, explicit same-stage revision/tick resume seeds, three-consumer resume validation, native rollback, downstream immutable-snapshot replay/retry, idempotent shutdown, and revision-continuous restart coverage.
- Added the Phase 6BW post-ChangeBlock shared-SoA adoption re-evaluation, rerunning all 16 proxy/ABI/lifecycle gates and deferring production adoption because the current 1,200-step Resident hot path already performs zero numeric re-imports.
- Added the Phase 6BV four-configuration emitter availability matrix, safely measuring one and twenty Point emitters at 7,200 points, retaining the qualified two-log Sphere reference, and refusing an end-to-end ranking while Point and NanoVDB consumers remain unavailable.
- Added the Phase 6BU fixed-Flow native API availability audit, confirming 19 public `IFlowUsd` members but no external NanoVDB consumer-write boundary, and made the Phase 6BT runner release its persistent context before exit and report safe unqualified outcomes without treating them as execution failures.
- Added the Phase 6BR–6BT fixed-Flow NanoVDB buffer/consumer probes, identifying four float channels plus packed RGBA8 and safely rejecting five unqualified public USD consumer arrangements without changing production.
- Added the Phase 6BP/BQ default-off fixed-Flow runtime probes, rejecting unsafe live PointCloud structural mutation, recording the native binding contract, and measuring persistent point-to-NanoVDB generation from 360 to 7,200 points without changing production.
- Added the Phase 6BO default-off emitter transport scalability audit, confirming aggregate Point and NanoVDB schemas in the fixed Flow SDK, measuring 360–7,200 Point payloads with source/copy/Set/notice separation, rejecting per-surface-point Prims, and leaving real Flow ingestion/rasterization as explicit follow-up work.
- Added the Phase 6BN trackless real-Flow adoption audit, balanced native-producer comparison, exact-output gates, explicit historical-runner opt-outs, and a browser-readable adoption report.
- Added the Phase 6BM default-off real-Flow `Sdf.ChangeBlock` resident publication candidate, revision-gated notice telemetry, same-block immutable rollback coverage, balanced native-producer measurements, and a browser-readable qualification report.
- Added the Phase 6BL local-Kit `Sdf.ChangeBlock` contract prototype, proving 19-to-1 USD notice coalescing, revision-consistent publication, explicit same-block snapshot replay, and a revision-gated in-memory timing reduction while leaving production unchanged.
- Added Phase 6BK default-off lightweight USD tail profiling, correlating 236 commits per run with Flow/render load without adding USD reads; real-Kit results attribute a median 83.0% of p95 publication time to `UsdAttribute.Set` while preserving exact authoritative outputs.
- Added the Phase 6BJ default-off production resident-native Phase 3 lifecycle path, connecting 1,200 native wood steps through immutable snapshots to the existing USD adapter with exact authoritative outputs; functional gates pass while USD tail-performance adoption remains deferred.
- Added the Phase 6BI direct resident-native output connection to the existing immutable `ResidentPublishedSnapshot` schema, with exact field-order, copy, revision, failure-isolation, lifecycle, and 4 ms performance gates while keeping production disabled.
- Added the Phase 6BH default-off immutable-shadow USD Set-skip candidate, retaining mandatory revision writes and full failure replay while passing the 4 ms gate in all three paired real-Kit runs.
- Added the Phase 6BG default-off lightweight resident USD commit trial with transactional bootstrap, revision-last publication, failure-only immutable snapshot replay, fail-closed recovery, and three paired real-Kit measurements.
- Added the Phase 6BF opt-in USD prim/attribute handle-cache trial, preserving actual authored old-value reads and transactional rollback while recording a repeatable but insufficient p95 improvement from 4.4762 ms to 4.1751 ms.
- Added the Phase 6BE opt-in redundant USD Set audit with USD-stored-value classification, per-attribute changed/unchanged counts and Set timings, three-run exact-output gates, and evidence that no-op skipping alone is insufficient for the 4 ms transaction target.
- Added Phase 6BD opt-in transactional USD profiling, separating snapshot construction from adapter publication and measuring prim lookup, payload preparation, attribute lookup, rollback-journal capture, `UsdAttribute.Set`, commit, and unattributed overhead across three paired real-Kit runs; production publication behavior remains unchanged.
- Added the isolated Phase 6BC-S shared NumPy/C++ SoA authority research spike with generation-checked Python cell proxies, edit leases, fail-fast step exclusion, exact rollback/schema gates, ABI validation, and three-run performance evidence; production and USD publication remain unchanged.
- Added the Phase 6BC default-off Kit resident snapshot adapter with owner-thread lifecycle enforcement, transactional USD rollback, one-revision Flow/visual/support publication, exact baseline-output gates, and real RTX 3090 timing evidence.
- Added the Phase 6BB resident backend lifecycle trial covering fresh Python-view export, revision-conflict rejection, transactional edit/native rollback, structural candidate rebuild, exact serialization, and idempotent shutdown export.
- Added the Phase 6BA headless native 5 Hz / 12-frame scheduler contract, immutable three-consumer revision fan-out, Python-reference tolerance gates, and structural-dirty safe stop.
- Added the Phase 6AZ explicit resident revision/dirty ownership trial, exact one-log state import, structural rebuild classification, and a documented rejection of unmarked direct writes in native mode.
- Added the Phase 6AY resident native publication boundary for 11 immutable app/Flow/support outputs per log, exact Python-contract comparison, and a measured rejection of full public-state scanning as an automatic fallback.
- Added the Phase 6AX resident three-pathway Arrhenius complete-step candidate, bounded secondary-tar branch coverage, tolerance-based lockstep evidence, and a 4 ms performance report.
- Added the Phase 6AW resident piecewise-complete wood-step candidate, including evaporation, pyrolysis, char oxidation, phase finalization, step outputs, cumulative products, exact ignition-history comparison, and a 4 ms performance gate.
- Added the Phase 6AV resident immutable-conduction-topology kernel, exact 62,400-edge comparison, pairwise energy-conservation gate, and next-reaction-boundary report.
- Added the Phase 6AU MSVC native contiguous-state boundary probe, exact 20-log Kit-Python comparison, per-step object-roundtrip rejection, and resident-SoA qualification report.
- Added the Phase 6AT error-budgeted whole-log approximate-sleep trial, three tolerance candidates, exact-step accuracy references, moving-heat performance gates, and native-path decision report.
- Added the Phase 6AS app-equivalent scheduler contract trial, immutable multi-consumer output revisions, fixed latency audit, and moving-heat activity test that rejects exact dormancy as stable capacity control.
- Added the Phase 6AR deterministic 5 Hz/12-frame wood scheduler trial, exact whole-log dormant gate, activity-ratio timing matrix, synchronous-state equivalence checks, and compact development-log video trigger.
- Added the Phase 6AQ Kit-Python scaling benchmark for 2, 5, 10, and 20 simultaneously active logs, exact per-log state gates, 4 ms budget analysis, and a compact development-log video trigger.
- Added the Phase 6AP two-depth re-profile of the adopted slotted-cell path, exact-output gates, current-hotspot report, and compact development-log video trigger.
- Added and adopted Phase 6AO slotted authoritative wood-cell storage after an exact-output, alternating three-pair end-to-end gate, while retaining mutable public fields and the serialized schema.
- Added the Phase 6AN post-inline two-depth re-profile, exact-output gates, current-hotspot report, and compact development-log video trigger.
- Added the Phase 6AM inline homogeneous sensible heat-capacity path, mutable-state fallback and exception tests, alternating three-pair adoption gate, browser-readable report, and a new real-run development-log video.
- Added the Phase 6AL two-depth re-profile of the adopted Phase 6AK path, exact-output gates, current-hotspot report, and compact development-log video trigger.
- Added the Phase 6AK step-local homogeneous heat-capacity path, public-state fallback tests, alternating three-pair adoption gate, and browser-readable report with a compact video trigger.
- Added the Phase 6AJ two-depth adopted-path re-profile, with separate three-run broad and per-cell timing sets, exact-output gates, and a browser-readable candidate report.
- Added the Phase 6AI constant-model heat-capacity fast path, mutable-state and fallback tests, alternating three-pair adoption gate, and browser-readable report with a compact video trigger.
- Added the Phase 6AH opt-in per-operation sensible-heat profile, three-run invariant gate, and browser-readable candidate-selection report.
- Added an opt-in deterministic Phase 3 viewport-frame capture and ffmpeg H.264 encoding path, with a real 1280×720 burn-scenario video embedded in the browser-readable development log.
- Added reusable compact development-log video triggers and an accessible shared playback modal with focus restoration, Escape/backdrop close behavior, and direct-file fallback.

- Added the Phase 6AG adopted-path internal re-profile, Phase 6Y comparison, exact-output gates, and browser-readable current hotspot report.

- Added the Phase 6AF runtime-topology mutability audit, explicit opt-in snapshot trial, alternating-pair benchmark, and browser-readable rejection report.

- Omniverse Kit Base Editorを基盤とするCampfire Simulatorアプリ。
- 決定的なPhase 0固定シーン生成とUSD書き出し。
- 固定カメラのヘッドレス画像キャプチャとJSON要約。
- シーン構造・再生成性を確認する拡張テスト。
- Phase 0を一括実行するPowerShell検証スクリプト。
- 実画面、実測値、検証結果、既知の問題を掲載する静的Web版開発日記。
- NVIDIA Flow 110.0.0によるPhase 1火炎シーン、移動Sphere Emitter、静的薪コライダー。
- Flow active block、end-to-end更新時間、NanoVDB CPU読み戻し、GPU利用を記録するヘッドレス検証。
- Phase 1の固定フレーム比較キャプチャと判断ゲートを掲載する開発日記エントリ。
- 永続ID、SI寸法、密度・質量、剛体・衝突・減衰を持つPhase 2の動的薪モデル。
- 5本目の薪を追加・持ち上げ・リセットできる最小GUIと、同じ操作を使うヘッドレス経路。
- 固定60 Hzで落下・静止・石囲い内への積層・Emitter追従・Flow稼働を判定するPhase 2検証。
- 落下中と積層後の実画面、物理タイミング、既知の同期コストを掲載するPhase 2開発日記。
- 1本1,152セルの熱伝導、水分蒸発、区分線形熱分解、炭化、炭酸化を扱うPhase 3木材モデル。
- 乾量基準含水率、version付きUSD状態保存、質量保存メトリクス、木材由来Flow燃料入力。
- 乾燥薪と湿潤薪を240秒比較し、CSV・JSON・固定キャプチャを検査するPhase 3ヘッドレスシナリオ。
- 着火遅延、質量収支、性能超過を実測値とともに掲載するPhase 3開発日記。
- 接触・向き・隙間・上方開口・風から酸素係数を求めるPhase 4通気近似。
- 密積みと井桁組みの着火・ガス放出比較、USD注釈、ヘッドレス画像検証。
- 軸断面ごとの残存支持率、炭の低強度近似、局所熱流束、支持喪失判定。
- 事前分割薪のFixedJoint解除、残存質量・コライダー更新、PhysX崩落、通気回復後の再燃検証。
- Phase 5の崩落前後キャプチャ、JSON要約、PowerShell受け入れスクリプト、Web開発日記。
- NISTIR 7094 Table 2の5層合板データを固定したPhase 6A校正参照と、等価クーポン・決定的36候補探索。
- 観測・初期・校正値を比較するUSD棒グラフ、SVGレポート、候補CSV、Phase 6ヘッドレス受け入れスクリプト。
- 合板の係数選択から隔離したNIST OSB外部材料ホールドアウトと、再調整なしの比較SVG・受け入れ判定。
- NISTIR 7094 Appendix Aの合板反復試験をSAMP.1/2選定・SAMP.3検証へ固定分割した、同一材料内の再調整なしホールドアウト評価。
- 公称12.7 mm、0.1 m角、5等厚層、片面加熱を明示し、観測初期質量を保持するPhase 6D平板試験片モデルと層温度SVG。
- 出典付き一次Arrhenius係数を使うPhase 6E見かけ反応と、温度依存速度曲線SVG。
- 同じ未反応木材に競合するガス・タール・チャーの3一次反応、経路別質量・収率追跡、共通倍率16候補探索を行うPhase 6Fモデル。
- NISTIR 4916の材料表に基づく合板・OSB別の熱伝導率と比熱、観測質量由来密度の維持、未解決接着界面を記録するPhase 6G材料プロファイル。
- USDA Wood Handbookの乾燥木材比熱式を材料別基準値へ正規化し、出典範囲280–420 Kへ固定するPhase 6H温度依存比熱モデル。
- NIST Model IIIの係数と固定1秒シナリオで、一次タールを二次ガスと残存タールへ質量保存的に再分類するPhase 6I診断モデル。
- Borosonらの一次実験範囲0.9–2.2秒・773–1073 Kで二次タール生成物分配を比較し、係数選定から隔離するPhase 6J滞留時間感度評価とSVGレポート。
- 完全なSI入力を要求する一次元Darcy気相輸送計算器、合板固有の欠測5入力、滞留時間を保留するPhase 6K結合ゲートとSVGレポート。
- 各層の乾燥木材消費率から未収縮の質量等価熱分解深さを求め、物理炭化層厚さと収縮係数を未確定のまま分離するPhase 6L診断とSVGレポート。
- 34.7 kW/m²・600秒のカバ合板炭化深さ実測を非採点で並べ、10条件中3条件だけの一致から物理厚さへの転用を拒否するPhase 6M外部比較可能性ゲートとSVGレポート。
- 35/70 kW/m²、4中断時刻、3反復の24条件で、厚さ変位・光学/300 °C前線・5層識別情報・質量履歴・不確かさを要求するPhase 6N測定契約、CSV受け入れゲート、SVGレポート。
- 初期面基準座標、DAQ時刻同期、24個のRun ID、質量・温度・表面・イベントの生データテンプレート、3外部承認を要求するPhase 6O実験実施計画とSVGレポート。
- 最初のRun IDへ空のmanifest・生データファイル・証拠ディレクトリを安全に生成し、計測値なし・実行未承認・取込み不可を検証するPhase 6Pオフラインrun-package dry runとSVGレポート。
- 実行情報9項目・外部証拠3件・責任研究室レビュー4項目を空欄で引き渡し、全入力後もリポジトリによる実行許可を拒否するPhase 6Qハンドオフ契約とSVGレポート。
- 物理式・格子・時間刻みを変えず、スカラー熱流束、熱伝導スナップショット、単一走査メトリクス、Flow入力再利用でCPU木材更新を短縮するPhase 6R性能改善、単体ベンチ、比較SVG。
- 起動、CPU木材、集計、Flow写像、Emitter USD、薪表示USD、Kit／Flow更新、画像保存、最終出力を排他的に測り、2 runの中央値と範囲を示すPhase 6S時間内訳レポート。
- CPU木材stepを8つの排他的区間へ分けるオプトイン計測、状態SHA-256不変条件、3 run中央値、相判定・定数比熱ホットパス改善を示すPhase 6T内部プロファイルとSVGレポート。
- 顕熱更新・状態確定をPython AoS、NumPy変換／常駐、Warp CUDA転送／常駐で比較し、毎step転送を含むGPU案を棄却するPhase 6U配列バックエンド境界ベンチマークとSVGレポート。
- coverage付き通常39件とcoverageなしNIST校正1件へ分離し、Kitの300秒上限内で標準40テストと生成API文書検査を復旧するPhase 6Vテスト構成とSVGレポート。
- 顕熱更新と状態確定だけをNumPy化する任意選択のPhase 6W全step経路、400 stepの完全同値ゲート、制御ベンチマーク、Phase 3出力比較、デバッガー混入時間の除外判断、SVGレポート。
- developer bundleをversion lockから除いたPhase 6X測定専用Kitアプリ、debug拡張実行時ゲート、成果物シーン隔離、交互順序2組のPython／NumPy end-to-end比較、Python既定確定レポート、coverageを保つ35＋4＋2件の標準テスト分割。
- debugger-free Phase 3で既定Python木材stepの8区間を3回測定し、顕熱更新を次の候補へ選ぶPhase 6Yオプトイン内部プロファイル、同値ゲート、JSON／SVGレポート。
- 顕熱ループ局所試作のprofile／非計測前後各3 runを分離し、内部5.45%短縮でもend-to-end悪化なら元コードへ戻すPhase 6Z採否ゲートとJSON／SVGレポート。
- 外部面積0の内部セルを境界熱計算から外すPhase 6AA早期分岐、debugger-free交互順序3組の採用ゲート、権威出力の完全一致検査、再現可能なJSON／SVGレポート。
- 乾燥／湿潤薪ごとの温度・質量clamp、相割当、相遷移を通常無効で集計し、性能値から分離するPhase 6AB状態分岐診断とJSON／SVGレポート。
- 温度・4質量の安全境界とNaN／負のゼロ処理を維持した比較分岐、profileと交互順序3組の採用ゲート、20.40%の木材step短縮を含むPhase 6AC。
- 相状態の下流依存監査、公開APIの逐次更新維持、Phase 3最終一回更新、完全な永続出力同値性、交互順序3組の採用ゲートを含むPhase 6AD。
- metrics下流フィールド監査、5値のhot-loop集計、完全な公開metricsと最終要約の維持、交互順序3組の採用ゲートを含むPhase 6AE。
- Thurner–Mannの公開A/E組をSI単位で固定したPhase 6E一次Arrhenius熱分解、48候補探索、温度–速度曲線SVG。

### Changed

- Standardized `Sdf.ChangeBlock` notice coalescing whenever the otherwise opt-in resident lightweight publication path is enabled, while keeping the global resident path off by default and retaining an explicit disable escape hatch.
- Added visible semantic Phase 6P–6AW headings to every recent development-log progress card so milestones remain identifiable outside link metadata and captions.
- Split the fixed-reference and full 180-second air-feedback regressions into dedicated non-coverage processes after two unchanged standard runs hit Kit's fixed 300-second coverage limit; retained collapse coverage, representative thermal/air coverage, all assertions, and all 41 tests.
- Enabled the Phase 6AM inline homogeneous sensible heat-capacity path after a 6.15% median two-log step improvement, 4.29% scenario improvement, 3/3 improving pairs, and exact authoritative outputs; per-cell temperature and mass reads remain uncached.
- Enabled the Phase 6AK step-local homogeneous heat-capacity path after a 13.15% median two-log step improvement, 9.95% scenario improvement, 3/3 improving pairs, and exact authoritative outputs; no coefficient is retained across steps.
- Split the wet-kindling coverage scenario into its own fixed-timeout process and stop it once both ignition events are observed, while retaining evaporation, ignition-order, mass-balance, finite-state, and non-negative-mass assertions; the standard suite remains 41/41 with coverage enabled.
- Enabled the Phase 6AI constant-model heat-capacity path in the standard Python application route after a 7.00% median two-log step improvement and exact authoritative-output checks; no heat-capacity values are cached.
- Split three long-running coverage scenarios into two dedicated Kit test processes after the primary group twice reached its fixed 300-second limit; all 41 checks and their coverage modes remain enabled.
- Moved real-wood, real-flame, laboratory-equipment testing and quantitative experimental calibration out of project scope; Phase 6N–6Q artifacts remain archived design history rather than completion gates.
- MVPのFlow結合方針を、木材状態を正とする一方向結合から開始する方針へ確定。
- アプリの既定シーンをPhase 2へ変更し、薪の権威位置からFlow Emitterを更新する構成へ拡張。
- アプリの既定シーンをPhase 3へ変更し、Flow入力の所有者を木材熱モデルへ移行。
- アプリの既定シーンをPhase 4の積層通気比較へ変更。
- アプリの既定シーンをPhase 5の拘束付き分割薪へ変更。
- アプリの既定シーンをPhase 6の校正結果比較へ変更。

### Notes

- 以下の項目は上流Kit App Templateの変更履歴。

## [110.2.0] - 2026-07-20

### Changed
- Updated to `Kit 110.2.0`
  - [Kit 110.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_2.html)
  - [Kit 110.2 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_2_highlights.html)

### Added
- Added a Testing Applications and Extensions guide (readme-assets/additional-docs/testing_apps_and_extensions.md)

### Fixed
- Hardened the USD Viewer messaging extension: a missing or empty `paths` payload is now a safe no-op, and exception details are no longer returned to the streaming client

## [110.1.2] - 2026-06-24

### Added

- Added the `omni.kit.renderer.ready` extension to the USD Viewer template
  - Emits an `RTX ready` log message once the renderer has finished initializing, making it easier to confirm shader compilation has completed when diagnosing streaming or shader caching issues

### Changed

- Updated to `Kit 110.1.2`
  - [Kit 110.1.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_2.html)

### Deprecated

- Deprecated the `-p` / `--package` option for `repo launch`; it will be removed in a future release. To run a packaged application, decompress the archive and launch the extracted application directly (see Packaging An Application)

### Removed

- Removed the Git LFS prerequisite from the setup instructions; Git LFS is no longer required to clone or use the repository
- Removed the Graphics Delivery Network (GDN) streaming option from the templates

## [110.1.1] - 2026-05-06

### Changed

- Updated to `Kit 110.1.1`
  - [Kit 110.1.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_1.html)
  - [Kit 110.1.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_1_highlights.html)
- `omni.kit.converter.cad` and `omni.kit.window.modifier.titlebar` cross dependency resolved for target platform check

## [110.1.0] - 2026-04-06

### Changed

- Updated to `Kit 110.1.0`
  - [Kit 110.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1.html)
  - [Kit 110.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_1_highlights.html)
- Templates are now **versioned packages** (`kit_core_templates`, `kit_sample_templates`) pulled as dependencies via packman, replacing the previous git-fetch and in-repo template model
  - Packages are declared in `tools/deps/repo-deps.packman.xml` and resolved into `_repo/deps/`
  - Template discovery uses `LocalTemplateCollection` pointing at package paths in `base_project/templates/templates.toml`
  - Existing workflows (`repo template new`, template selection UI) are unchanged
- Project directories now contain only your code and configuration; template content stays in `_repo/deps/` as external, versioned packages — giving a clear separation between your project files and template boilerplate

## [110.0.0] - 2026-03-05

### Changed

- Update to `Kit 110.0.0`
  - [Kit 110.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_0.html)
  - [Kit 110.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/110_0_highlights.html)
- Updated `stage_management.py` in `usd_viewer.messaging` extension template to make prims selectable in viewport and updated `omni.usd.StageEventType` to `ASSETS_LOADED` to fix camera exposure when resetting the camera in Web-Viewer-Sample front-end client.

## [109.0.3] - 2026-01-26

### Changed

- Update to `Kit 109.0.3`
  - [Kit 109.0.3 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_3.html)

## [109.0.2] - 2025-12-18

### Changed

- Updated to `Kit 109.0.2`
  - [Kit 109.0.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_2.html)

## [109.0.1] - 2025-12-04

### Added

- Kit added support for ARM64

### Changed

- Updated to `Kit 109.0.1`
  - [Kit 109.0.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_1.html)
  - [Kit 109.0.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_1_highlights.html)
- Tooling in tools/repoman was upstreamed to `repo_kit_tools`
- `repo package_container` replaces `repo package --container`
- `repo package` is now mapped to the `repo_package_app` tool in `repo_kit_tools`. It still uses the repo_package configuration in our repo.toml.
- Containerization files in tools/containers have been removed. They are now generated in an automated fashion during containerization by `repo package_container --app ${path_to_kit_file}`. You can generate and not containerize by running `repo package_container --app ${path_to_kit_file} --generate`
- Default image tag name changed from `kit-app-template:latest` to `appname:latest`. eg: `usd-viewer_nvcf:latest`
- Container `--name` updated to `--image-tag` supporting both image name and image tag `--image-tag [container_image_name:container_image_tag]`
- Updated required driver version `>=550.54.15` (Linux) or `>=551.78` (Windows).

### Deprecated

- tools/containers `entrypoint_memcached.sh.j2` now migrated to generated `entrypoint.sh`
- tools/containers `kit_args.txt` now migrated to generated `entrypoint.sh`
- tools/containers `Stream_sdk.txt` now migrated to generated `Dockerfile`

### Known Issue

- Basic C++ w/ Python Binding Extension test fails due to test environment configuration

## [109.0.0] - 2025-11-18

### Added

- Added new Livestream extensions `omni.kit.livestream.aov` and `omni.services.livestream.webrtc`

### Changed

- Updated to `Kit 109.0.0`
  - [Kit 109.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0.html)
  - [Kit 109.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0_highlights.html)
  - `useFabricSceneDelegate = true` removed. Fabric Scene Delegate (FSD) is now enabled by default in Kit 109.0. Applications no longer need to explicitly enable FSD in `.kit` configuration files.
  - `auto_load_usd` for USD Viewer now supports relative paths
  - Set custom orientations for `UsdLux 25.05` for Y-up and Z-up stages in USD Explorer template and set `inputs:normalize = true` on that template's distant light.

## [108.1.0] - 2025-10-06

### Added

- Added `omni.kit.primitive.mesh` extension to Kit Base Editor and USD Explorer Templates to enable Create Mesh in viewport by default
- Added `omni.hydra.usdrt_delegate` extension to Kit Base Editor as dep needed for `useFabricSceneDelegate=true`

### Changed

- Updated to `Kit 108.1.0`
  - [Kit 108.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_1.html)
  - [Kit 108.1 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_1_highlights.html)

### Deprecated

- Deprecated `omni.kit.ngsearch` extension, no longer available after Kit 108

## [108.0.0] - 2025-08-12

### Changed

- Updated to `Kit 108.0.0`
  - [Kit 108.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_0.html)
  - [Kit 108.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/108_0_highlights.html)
- Changed "Omniverse Cloud Streaming" application layer to "NVCF Streaming" to align underlying technology and use case.
- Updated streaming extensions to `omni.kit.livestream.app` and `omni.services.livestream.session` to support NVCF Streaming.
- Removed omni.services.transport.server.http.port overrides.  Aligned all template applications to use default ports.
- Updated repository documentation to reflect changes in streaming changes.
- Updated crash reporter settings to compress crash reports.
- Update Windows `omni.kit.window.modifier.titlebar` extension version 
- Update repo tooling to most recent versions
- Updated application icon images for Composer and Explorer templates
- Enabled testing for USD Viewer Template messaging extension

### Fixed

- Fix duplicate key `.kit` file issues related to `settings.app.exts`

## [107.3.0] - 2025-05-27

### Added

- Added `repo template modify` tooling enabling developers to add Template Layers to existing applications created with 107.3 or newer.

### Changed

- Updated to `Kit 107.3.0`
  - [Kit 107.3 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_3.html)
  - [Kit 107.3 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_3_highlights.html)
- Updated packman version to 7.29 to address customer issues with network restrictions [Issue #80](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/80)

## [107.2.0] - 2025-05-05

### Added

- Added tooltip information to the VSCode debug extensions to clarify usage.
- Added tooling checks for path whitespace and OneDrive paths to improve developer experience.

### Changed

- Updated to `Kit 107.2.0`
  - [Kit 107.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_2.html)
  - [Kit 107.2 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_2_highlights.html)
- Remove hard .git dependency from tooling
- Exclude `_repo` from packaging operations.

### Fixed

- Fixed nondeterministic tool loading behavior raised in [Issue #65](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/65)
- Addressed spelling errors raised in [Issue #63](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/63)
- Addressed default repository definition causing issues with bootstrapping thin packages from [Issue #70](https://github.com/NVIDIA-Omniverse/kit-app-template/issues/70)

## [107.0.3] - 2025-03-26

### Fixed

- Fixed issues with run time available registries by adding them directly to `.kit` templates
- Fixed issues with test time available registries by adding user.toml registry configurations

## [107.0.3] - 2025-03-20

### Added

- Added the ability select of application layers (streaming configurations) individually during templating
- Added a dedicated streaming configuration for NVCF based Omniverse Cloud (OVC) deployments
- Added C++ With Python Extension Template and Documentation
- Added streaming application creation and configuration documentation
- Added Developer Bundle extension by default to Base Editor, Composer, and Explorer templates
- Added an exclusion for Developer Bundle on streaming application layers

### Changed

- Updated to `Kit 107.0.3`
  - [Kit 107.0 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_0.html)
  - [Kit 107.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/107_0_highlights.html)
  - Updated repo tooling UX to clarify tool use and improve user experience
  - Changed previous Omniverse Cloud (OVC) streaming configuration to Omniverse Cloud Streaming (Legacy)
  - Updated to `Cad Converter 203.0.0` Release
    - [Cad Converter Release Notes](https://docs.omniverse.nvidia.com/extensions/latest/ext_cad-converter/release-notes.html)
  - Moved extension `type` declaration to the extension definition section within the templates.toml file
  - Removed `omni.usd.fileformat.sbasar` and `omni.kit.property.sbsar` extensions from the USD Composer Template kit file. The extensions will be available at a later date.

### Fixed

- Fixed Windows long path issues during `repo package`

## [106.5.0] - 2024-12-12

### Added

- Added `app.environment` name setting for all kit file templates

### Removed

- Removed `WALK_VISIBLE_PATH` from USD Explorer Setup Extension

### Changed

- Updated to `Kit 106.5.0`
  - [Kit 106.5 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_5.html)
  - [Kit 106.5 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_5_highlights.html)
- Updated Asset browser URLs
- Optimized OVC streaming file kit settings for OVC streaming deployments

### Fixed

- Updated Editor tutorial away from deprecated methods to use action based method for show/hide of menus

## [106.4.0] - 2024-11-18

### Added

- Added `stream_sdk.txt` to set timeout for stream SDK and updated container packaging to add it to container images
- Added `replay` to the `template new` tooling to allow for replaying app and extension creation to support automation
- Added companion tutorial section for using python pip packages

### Changed

- Updated to `Kit 106.4.0`
  - [Kit 106.4 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_4.html)
  - [Kit 106.4 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_4_highlights.html)
- Updated the `omni.kit.asset.browser` extension URLs to point to current asset libraries when not specified in Kit file
- Updated to `Cad Converter 202.0.0` Release
  - [Cad Converter Release Notes](https://docs.omniverse.nvidia.com/extensions/latest/ext_cad-converter/release-notes.html)

### Fixed

- Added missing notification of successful build `BUILD (RELEASE) SUCCEEDED` for Python only builds for Windows

## [106.3.0] - 2024-11-07

### Removed

- Removed the USD Viewer setup samples folder and the light_rigs folders from the USD Composer and USD Explorer setup templates. That data is now accessible from the `omni.usd_viewer.setup` and `omni.light_rigs` extension dependencies.

## [106.3.0] - 2024-11-04

### Added

- Built app containers support `NVDA_KIT_ARGS` and `NVDA_KIT_NUCLEUS` environment variables
  - `NVDA_KIT_ARGS` is passed directly into the kit executable
  - `NVDA_KIT_NUCLEUS` if set causes the container entrypoint to create an omniverse.toml configuration file with a single entry pointing at the provided nucleus server. This will also set the kit arg --/ovc/nucleus/server with the envvar value.
  - `repo launch --container` maps in these variables from the local environment as well
- Added `omni.kit.menu.common` to Kit Base Editor, USD Composer, and USD Explorer Template Kit files to enable Toggle Viewport Fullscreen and UI overlay with F7 and F11

### Changed

- Updated to `Kit 106.3.0`
  - [Kit 106.3 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_3.html)
  - [Kit 106.3 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_3_highlights.html)
- Updated build process to support auto-detection or user-specified host versions of `MSVC` and `WinSDK`, providing flexibility for Windows C++developers to leverage their existing installations. [Windows C++ Developer Configuration](readme-assets/additional-docs/windows_developer_configuration.md)
- Updated `omni.kit.usd_explorer.main.menubar` to version 1.0.38 so that it works correctly with `omni.kit.menu.common`
- Moved Light Rig binary data from kit-app-template repo to `omni.light_rigs` extension and added the extension to Kit Base Editor, USD Composer, and USD Explorer Template Kit files
- Moved USD Viewer sample assets from kit-app-template repo to `omni.usd_viewer.samples` extension and added the extension USD Viewer Template Kit file
- Moved Kit Service Template to bottom of Application list
- BUILD (RELEASE) SUCCEEDED message not supported for all build configurations

### Removed

- Removed Services dependencies from USD Composer Template that caused a firewall popup on first launch

## [106.2.0] - 2024-10-03

### Changed

- Updated to `Kit 106.2.0`
  - [Kit 106.2 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_2.html)
  - [Kit 106.2 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_2_highlights.html)
- Refactored Viewer Template default tests to avoid unnecessary dependencies

### Removed

- Unused `simulation` menu item from USD Composer Template

## [106.1.0] - 2024-09-18

### Added

- Support for containerization of streaming applications and services via `repo package --container`
- Support extension only builds via `repo build`
- Support the ability to launch created containers via `repo launch --container`
- repo_usd tooling dependency
- Support for USD Viewer Template to send scene loading state to client via messaging

### Changed

- Updated to `Kit 106.1.0`
  - [Kit 106.1 Early Access Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_1.html)
  - [Kit 106.1 Early Access Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_1_highlights.html)
- Aligned default testing for applications and extensions
- Update and align code formatting/style across templates

### Fixed

- Extra setup extensions appear in standard extension template menu
- "Could not find cgroup memory limit" error during build
- Fixed default manipulator pivot back to "bounding box base" in USD Explorer Template

## [106.0.3] - 2024-09-18

### Changed

- Updated to `Kit 106.0.3`
  - [Kit 106.0.3 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_3.html)

## [106.0.2] - 2024-07-29

### Added

- Support for local streaming configurations for UI based Applications
- Support for multiple setup extensions per application
- Ability to pass arguments to Kit via the `repo launch` tool
- USD Composer Application Template and Documentation
- USD Viewer Application Template and Documentation
- USD Composer Setup Extension and Documentation
- USD Viewer Setup Extension and Documentation
- Repository Issue Templates Bug/Question/Feature Request
- Omniverse Product-Specific Terms (PRODUCT_TERMS_OMNIVERSE)
- Support for type ordering in templates.toml
- Metrics Assembler to Kit Base Editor Template to support unit correct assets
- Support for automatic launch if only single `.kit` file is present in `source/apps`

### Changed

- Updated to `Kit 106.0.2`
  - [Kit 106.0.2 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_2.html)
  - [Kit 106.0.1 Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_1.html)
- Updated all relevant application templates READMEs to reflect the addition of local streaming configurations
- Updated .gitattributes to ensure LFS is used for all relevant file types
- Updated .gitignore to exclude streaming app event traces
- Updated .vscode/launch.json to better support debugging behavior
- Updated LICENSE to separate NVIDIA License from Omniverse Product-Specific Terms
- Updated top level README.md to reflect additional templates and improve documentation clarity
- Updated Developer Bundle extension availability and corresponding documentation
- Updated public extension registry to reflect current Kit 106 registry location
- Updated templates.toml to support multiple setup extensions and new templates

## [106.0.0] - 2024-06-07

### Added

- Kit Base Editor Application Template and Documentation
- USD Explorer Application Template and Documentation
- USD Explorer Setup Extension and Documentation
- Kit Service Template and Documentation
- Simple Python Extension Template and Documentation
- Simple C++ Extension Template and Documentation
- Python UI Extension Template and Documentation
- Template configuration file (templates.toml)
- Added local `repo launch` tool for launching applications and fat packages directly
- Added local `repo package` functionality to improve package naming
- Omniverse EULA acceptance to Kit App Template via tooling
- tasks.json for better VSCode support
- SECURITY.md for security policy
- Notice for data collection and use
- Early access Developer Bundle extensions
- Kit App Template related Developer Bundle documentation (developer_bundle_extensions.md)
- Kit App Template related repo tools documentation (kit_app_template_tooling_guide.md)
- Usage and troubleshooting documentation for Kit App Template (usage_and_troubleshooting.md)
- repo_tools.toml to configure local repo tools

### Changed

- Updated to `Kit 106.0.0`
  - [Kit 106.0 Beta Release Notes](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0.html)
  - [Kit 106.0 Release Highlights](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_highlights.html)
- Updated repo_kit_template tooling to support Applications and Extensions
- Updated repo_kit_template tooling to allow for application setup extensions
- Updated top level README.md to reflect updated tooling and templates
- Updated LICENSE.md to reflect updated tooling and templates
- Updated .gitattributes to reflect use of templates rather directly from source
- Added configuration to repo.toml to support new tools and templates

### Removed

- Top level build .bat/.sh scripts in favor of using `repo build` directly
- Predefined `define_app` declarations from `premake5.lua` in favor of developer defined applications
- Predefined source/apps in favor of templates for developers to build from

