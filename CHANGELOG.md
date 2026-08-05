# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-08-04

### Added

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
- Thurner–Mannの公開A/E組をSI単位で固定したPhase 6E一次Arrhenius熱分解、48候補探索、温度–速度曲線SVG。

### Changed

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

