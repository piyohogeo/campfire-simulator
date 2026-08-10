# Phase V3T-L: lightweight RTX preset performance and visual gate

## 結論

production既定値は変更しない。候補は`DLSS Balanced + /rtx/rtpt/maxBounces=2`、性能不足時のfallback候補は同じ構成のDLSS Performanceである。ただしproduction相当Flow＋volumeでは各`45.412 FPS`／`47.858 FPS`で、visible counterの58 FPS near-present gateを満たさない。AO変更は保留する。RTX MinimalはFlow active-block gateに失敗し、production候補ではない。

## 測定契約

- baseline: `cb96b2a`、Kit 110.2、Flow 110.0.0、RTX 3090、1280×720、Power Limit 210 W（60%）
- 既存visible viewportの公開`ViewportAPI.frame_info`／`fps`だけを使用
- RTX readyは8回連続の`frame_number`増加後とし、その後warmupを実施
- 追加RenderProduct／HydraTexture、性能区間のcapture／encode、測定中のstage topology／material／asset変更なし
- 設定はKit同梱UI sourceでpathを確認し、warmup後の実効値再読取一致を必須化
- frame timeは`1000 / 平均visible FPS`。raw frame latencyやdisplay-present FPSではない

## 個別preflight

production相当Flow＋volumeのAuto baselineは`23.193 FPS`だった。DLSS Balanced `40.579`、Performance `44.517`、`/rtx/rtpt/maxBounces=2` `30.688 FPS`に改善した。cache、direct／dome sample 1、translucency OFF、SSS OFF、specular／refraction最小は`23.028..23.287 FPS`で明確な改善がなかったため複合presetから除いた。

RTX Minimalは`60.081 FPS`だったが、実V3シナリオでFlow active blockが生成されず既存gateに失敗した。Flow、emission、shadow、V3 textureのproduction互換性が成立しないため診断専用である。

## AO OFF native crash

AO OFF runはKit起動9秒後、`rtx.scenedb`がscene acceleration structureを生成した直後にnative crashした。Crash Reporter dumpはGit外の`artifacts/phasev3tl-crash-20260810-132830/`へ退避し、zip SHA-256は`5C0034D424BFDF9148595BAC034FE5EDB0CDEAE1D6FA0ABCD91F91AC47F3D5C4`である。

MINIDUMP ExceptionStreamから`0xC0000005` read、対象`0x20`、thread `41644`、fault RIP `omni.fabric.plugin.dll+0xD6960`を確認した。Python tracebackのMainThreadはidleだった。RSP上には`usdrt.hydra.fabric_scene_delegate.plugin.dll`の候補アドレスが複数あるが、WinDbg／CDB／DumpChkとprivate symbolsがないため正式なnative unwindではない。AO OFF、Flow volume、設定適用時期、RTX初期化raceのどれが原因かは未確定である。同条件の連続再実行はせず、AO変更を候補から外した。

runnerは`[crash] A crash has occurred`を即時fatalにし、Crash Reporter／dumpログとnative nonzero exitをcrash分類する。crash runと中断したretryは正式母集団へ含めない。

## 複合preset正式結果

| scene | V3T-K Auto | Candidate Balanced | Candidate Performance |
|---|---:|---:|---:|
| ground＋stones、ライトなし | 57.471 FPS / 17.40 ms | 116.647 / 8.57 | 116.674 / 8.57 |
| ground＋stones＋ライト | 54.939 / 18.20 | 116.661 / 8.57 | 116.708 / 8.57 |
| Cylinder 20本 | 46.017 / 21.73 | 116.720 / 8.57 | 116.697 / 8.57 |
| V3 Mesh＋固定texture | 45.536 / 21.96 | 116.753 / 8.56 | 116.764 / 8.56 |
| Flow simulation＋volume | 24.517 / 40.79 | 45.412 / 22.02 | 47.858 / 20.90 |

30/30 processがnormal exit、fatal／stage-ID／crash 0、Power Limit 210 Wだった。静的sceneは59 Hz present loopを越えるvisible render counterを示すが、display-present FPSとは表現しない。Flow sceneは両候補とも58 FPS gate未達である。

## 視覚gate

実V3燃焼で固定cameraおよびvisual-only camera orbit＋薪崩落を別processで撮影した。Balanced／Performanceとも薪・石の輪郭、接地、shadow、V3表面と高温emission、炎煙を維持した。Performanceは炎煙の時間的細部がわずかに平滑化されるためfallback-onlyが妥当で、常時既定にはしない。動画は性能母集団外である。

## 判断

- Balancedは画質側の基本候補だが、production Flowで性能gate未達なので採用gateは未成立
- Performanceへの切替条件はBalancedが操作上不足し、Performanceの視覚劣化を許容できる場合。ただし本実測でも58 FPS未達
- Max Bounces 2は明確な寄与があり候補へ残す
- AOはnative crashの原因境界を絞るまで変更しない
- 100% Power Limit比較は未実行。代表条件、温度／停止条件、復元手順を提示し、明示承認後にのみ実行する
- production code／既定値、wood authority、Flow入力、Emitter、collision、rigid layout、checkpoint、serialization、V3既定OFFは不変

最終回帰はRelease build、Phase 0 RTX、標準suite 8/8 process・77/77 test、V3T-C 6/6 processが合格した。V3T-Cは全runでdry／wet authority SHA-256一致、mass balance error 0、Resident revision 1200、wood-owned Flow inputとactive block peak 138..318を確認した。正式30 processのKit logは対象fatal token 0である。

機械可読値は`docs/devlog/assets/phasev3tl/lightweight_rtx_report.json`、`lightweight_rtx_samples.json`、`regression_report.json`に保存する。

## 後続判断

本Phaseの58 FPS gateと各測定値は当時の比較判定として保持する。Phase V3T-Nで今後の通常運用予算を45 FPS／22.222 ms目標、30 FPS／33.333 ms最低ラインへ定義したが、本結果を遡って合格へ読み替えない。
