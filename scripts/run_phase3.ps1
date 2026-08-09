param(
    [string]$OutputDir = "",
    [ValidateSet("python", "numpy")]
    [string]$ArrayBackend = "python",
    [switch]$ProfileWoodInternals,
    [switch]$ProfileSensibleHeat,
    [ValidateSet("original", "fast")]
    [string]$ConstantHeatCapacityPath = "fast",
    [ValidateSet("auto", "original", "fast")]
    [string]$HomogeneousHeatCapacityPath = "auto",
    [ValidateSet("auto", "original", "fast")]
    [string]$InlineHomogeneousSensibleHeatCapacityPath = "auto",
    [ValidateSet("dict", "slots")]
    [string]$CellStateStorage = "slots",
    [switch]$CollectWoodStateDiagnostics,
    [ValidateSet("original", "fast")]
    [string]$PythonSurfaceBoundaryPath = "fast",
    [ValidateSet("original", "fast")]
    [string]$PythonStateClampPath = "fast",
    [ValidateSet("eager", "deferred")]
    [string]$CellPhaseUpdates = "deferred",
    [ValidateSet("full", "compact")]
    [string]$RuntimeMetrics = "compact",
    [ValidateSet("dynamic", "precomputed")]
    [string]$RuntimeTopology = "dynamic",
    [switch]$CaptureVideo,
    [ValidateRange(1, 1200)]
    [int]$VideoFrameInterval = 20,
    [ValidateRange(1, 60)]
    [int]$VideoFps = 10,
    [switch]$ResidentSnapshotAdapter,
    [switch]$ResidentSnapshotTiming,
    [switch]$ResidentSnapshotHandleCache,
    [switch]$ResidentSnapshotLightweightCommit,
    [switch]$ResidentSnapshotSkipUnchanged,
    [switch]$ResidentSnapshotLightweightTailTiming,
    [switch]$ResidentSnapshotLightweightNoticeCoalescing,
    [switch]$ResidentSnapshotDisableLightweightNoticeCoalescing,
    [switch]$ResidentSnapshotLightweightNoticeTracking,
    [switch]$WoodVisualV0,
    [switch]$ResidentNativeBackend,
    [string]$ResidentNativeLibraryPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repoRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$useConstantHeatCapacityFastPath = $ConstantHeatCapacityPath -eq "fast"
$useHomogeneousHeatCapacityFastPath = if ($HomogeneousHeatCapacityPath -eq "auto") {
    $useConstantHeatCapacityFastPath
}
else {
    $HomogeneousHeatCapacityPath -eq "fast"
}
$useInlineHomogeneousSensibleHeatCapacityFastPath = if ($InlineHomogeneousSensibleHeatCapacityPath -eq "auto") {
    $useHomogeneousHeatCapacityFastPath
}
else {
    $InlineHomogeneousSensibleHeatCapacityPath -eq "fast"
}
$usePythonSurfaceBoundaryFastPath = $PythonSurfaceBoundaryPath -eq "fast"
$usePythonStateClampFastPath = $PythonStateClampPath -eq "fast"
$deferCellPhaseUpdates = $CellPhaseUpdates -eq "deferred"
$compactRuntimeMetrics = $RuntimeMetrics -eq "compact"
$precomputedRuntimeTopology = $RuntimeTopology -eq "precomputed"
$useSlottedWoodCellStorage = $CellStateStorage -eq "slots"
$useResidentSnapshotLightweightNoticeCoalescing = (
    $ResidentSnapshotLightweightCommit.IsPresent -and
    -not $ResidentSnapshotDisableLightweightNoticeCoalescing.IsPresent
)
if ($ResidentSnapshotLightweightNoticeCoalescing.IsPresent) {
    $useResidentSnapshotLightweightNoticeCoalescing = $true
}

if ($CollectWoodStateDiagnostics.IsPresent -and $deferCellPhaseUpdates) {
    throw "Wood state diagnostics require eager cell phase updates."
}
if ($ProfileSensibleHeat.IsPresent -and -not $ProfileWoodInternals.IsPresent) {
    throw "Sensible-heat timing requires -ProfileWoodInternals."
}
if ($ProfileSensibleHeat.IsPresent -and $ArrayBackend -ne "python") {
    throw "Sensible-heat timing requires the Python backend."
}
if ($useConstantHeatCapacityFastPath -and $ArrayBackend -ne "python") {
    throw "Constant heat-capacity fast path requires the Python backend."
}
if ($useHomogeneousHeatCapacityFastPath -and -not $useConstantHeatCapacityFastPath) {
    throw "Homogeneous heat-capacity fast path requires the constant-model fast path."
}
if ($useInlineHomogeneousSensibleHeatCapacityFastPath -and -not $useHomogeneousHeatCapacityFastPath) {
    throw "Inline homogeneous sensible heat-capacity fast path requires the homogeneous heat-capacity fast path."
}
if ($ProfileSensibleHeat.IsPresent -and -not $usePythonSurfaceBoundaryFastPath) {
    throw "Sensible-heat timing requires the fast surface path."
}
if ($ResidentSnapshotTiming.IsPresent -and -not $ResidentSnapshotAdapter.IsPresent) {
    throw "Resident snapshot timing requires -ResidentSnapshotAdapter."
}
if ($ResidentSnapshotHandleCache.IsPresent -and -not $ResidentSnapshotAdapter.IsPresent) {
    throw "Resident snapshot handle cache requires -ResidentSnapshotAdapter."
}
if ($ResidentSnapshotLightweightCommit.IsPresent -and -not (
    $ResidentSnapshotAdapter.IsPresent -and $ResidentSnapshotHandleCache.IsPresent
)) {
    throw "Resident snapshot lightweight commit requires the adapter and handle cache."
}
if ($ResidentSnapshotLightweightCommit.IsPresent -and $ResidentSnapshotTiming.IsPresent) {
    throw "Resident snapshot lightweight commit cannot use detailed transaction timing."
}
if ($ResidentSnapshotSkipUnchanged.IsPresent -and -not $ResidentSnapshotLightweightCommit.IsPresent) {
    throw "Resident snapshot unchanged-value skipping requires lightweight commit."
}
if ($ResidentSnapshotLightweightTailTiming.IsPresent -and -not $ResidentSnapshotLightweightCommit.IsPresent) {
    throw "Resident snapshot lightweight tail timing requires lightweight commit."
}
if ($ResidentSnapshotLightweightNoticeCoalescing.IsPresent -and -not $ResidentSnapshotLightweightCommit.IsPresent) {
    throw "Resident snapshot lightweight notice coalescing requires lightweight commit."
}
if ($ResidentSnapshotDisableLightweightNoticeCoalescing.IsPresent -and -not $ResidentSnapshotLightweightCommit.IsPresent) {
    throw "Disabling resident snapshot lightweight notice coalescing requires lightweight commit."
}
if ($ResidentSnapshotLightweightNoticeCoalescing.IsPresent -and $ResidentSnapshotDisableLightweightNoticeCoalescing.IsPresent) {
    throw "Resident snapshot lightweight notice coalescing cannot be both enabled and disabled."
}
if ($ResidentSnapshotLightweightNoticeTracking.IsPresent -and -not (
    $ResidentSnapshotLightweightCommit.IsPresent -and $ResidentSnapshotHandleCache.IsPresent
)) {
    throw "Resident snapshot lightweight notice tracking requires lightweight commit and handle cache."
}
if ($WoodVisualV0.IsPresent -and -not $ResidentSnapshotAdapter.IsPresent) {
    throw "Wood visual V0 requires -ResidentSnapshotAdapter."
}
if ($ResidentNativeBackend.IsPresent -and -not $ResidentSnapshotAdapter.IsPresent) {
    throw "Resident native backend requires the resident snapshot adapter."
}
if ($ResidentNativeBackend.IsPresent -and -not (Test-Path -LiteralPath $ResidentNativeLibraryPath)) {
    throw "Resident native backend library was not found: $ResidentNativeLibraryPath"
}
if ($ResidentNativeBackend.IsPresent -and (
    $ProfileWoodInternals.IsPresent -or
    $ProfileSensibleHeat.IsPresent -or
    $CollectWoodStateDiagnostics.IsPresent
)) {
    throw "Resident native backend cannot use Python wood instrumentation."
}

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "artifacts\phase3\latest"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$kitArgs = @(
    $app,
    "--no-window",
    "--/app/quitAfter=1200",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase3",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/exts/campfire.app/sceneOutputDir=$OutputDir",
    "--/exts/campfire.app/woodArrayBackend=$ArrayBackend",
    "--/exts/campfire.app/woodInternalTiming=$($ProfileWoodInternals.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/woodSensibleHeatTiming=$($ProfileSensibleHeat.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/pythonConstantHeatCapacityFastPath=$($useConstantHeatCapacityFastPath.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/pythonHomogeneousHeatCapacityFastPath=$($useHomogeneousHeatCapacityFastPath.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/pythonInlineHomogeneousSensibleHeatCapacityFastPath=$($useInlineHomogeneousSensibleHeatCapacityFastPath.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/pythonSlottedWoodCellStorage=$($useSlottedWoodCellStorage.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/woodStateDiagnostics=$($CollectWoodStateDiagnostics.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/pythonSurfaceBoundaryFastPath=$($usePythonSurfaceBoundaryFastPath.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/pythonStateClampFastPath=$($usePythonStateClampFastPath.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/deferCellPhaseUpdates=$($deferCellPhaseUpdates.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/compactRuntimeMetrics=$($compactRuntimeMetrics.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/precomputedRuntimeTopology=$($precomputedRuntimeTopology.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/captureVideoFrames=$($CaptureVideo.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/videoFrameIntervalSteps=$VideoFrameInterval",
    "--/exts/campfire.app/residentSnapshotAdapterEnabled=$($ResidentSnapshotAdapter.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentSnapshotTimingEnabled=$($ResidentSnapshotTiming.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentSnapshotHandleCacheEnabled=$($ResidentSnapshotHandleCache.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentSnapshotLightweightCommitEnabled=$($ResidentSnapshotLightweightCommit.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentSnapshotSkipUnchangedEnabled=$($ResidentSnapshotSkipUnchanged.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentSnapshotLightweightTailTimingEnabled=$($ResidentSnapshotLightweightTailTiming.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentSnapshotLightweightNoticeCoalescingEnabled=$($useResidentSnapshotLightweightNoticeCoalescing.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentSnapshotLightweightNoticeTrackingEnabled=$($ResidentSnapshotLightweightNoticeTracking.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/woodVisualV0Enabled=$($WoodVisualV0.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentNativeBackendEnabled=$($ResidentNativeBackend.IsPresent.ToString().ToLowerInvariant())",
    "--/exts/campfire.app/residentNativeLibraryPath=$ResidentNativeLibraryPath",
    "--/rtx/flow/enabled=true",
    "--/app/viewport/grid/enabled=false",
    "--/persistent/app/viewport/displayOptions=1152"
)

$runTimer = [System.Diagnostics.Stopwatch]::StartNew()
& $kit @kitArgs
$exitCode = $LASTEXITCODE
$runTimer.Stop()
if ($exitCode -ne 0) {
    throw "Phase 3 application failed with exit code $exitCode."
}

$summary = Join-Path $OutputDir "summary.json"
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Phase 3 summary was not produced: $summary"
}

$result = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
if ($result.status -ne "ok" -or $result.phase -ne "phase3") {
    throw "Phase 3 summary reported a failure or unexpected phase: $summary"
}
if ($result.scenario.wood_array_backend -ne $ArrayBackend) {
    throw "Phase 3 used an unexpected wood array backend."
}
if ([bool]$result.scenario.wood_internal_timing_enabled -ne $ProfileWoodInternals.IsPresent) {
    throw "Phase 3 used an unexpected wood internal timing setting."
}
if ([bool]$result.scenario.wood_sensible_heat_timing_enabled -ne $ProfileSensibleHeat.IsPresent) {
    throw "Phase 3 used an unexpected sensible-heat timing setting."
}
if ([bool]$result.scenario.python_constant_heat_capacity_fast_path -ne $useConstantHeatCapacityFastPath) {
    throw "Phase 3 used an unexpected constant heat-capacity setting."
}
if ([bool]$result.scenario.python_homogeneous_heat_capacity_fast_path -ne $useHomogeneousHeatCapacityFastPath) {
    throw "Phase 3 used an unexpected homogeneous heat-capacity setting."
}
if ([bool]$result.scenario.python_inline_homogeneous_sensible_heat_capacity_fast_path -ne $useInlineHomogeneousSensibleHeatCapacityFastPath) {
    throw "Phase 3 used an unexpected inline homogeneous sensible heat-capacity setting."
}
if ([bool]$result.scenario.python_slotted_wood_cell_storage -ne $useSlottedWoodCellStorage) {
    throw "Phase 3 used an unexpected wood-cell storage setting."
}
if ([bool]$result.scenario.wood_state_diagnostics_enabled -ne $CollectWoodStateDiagnostics.IsPresent) {
    throw "Phase 3 used an unexpected wood state-diagnostics setting."
}
if ($CollectWoodStateDiagnostics.IsPresent) {
    foreach ($name in @("dry", "wet")) {
        if ($result.scenario.wood_state_diagnostics.$name.cells_evaluated -ne 1382400) {
            throw "Phase 3 $name wood has an unexpected diagnostic cell count."
        }
    }
}
elseif (@($result.scenario.wood_state_diagnostics.PSObject.Properties).Count -ne 0) {
    throw "Phase 3 collected wood state diagnostics without an explicit request."
}
if ([bool]$result.scenario.python_surface_boundary_fast_path -ne $usePythonSurfaceBoundaryFastPath) {
    throw "Phase 3 used an unexpected Python surface-boundary setting."
}
if ([bool]$result.scenario.python_state_clamp_fast_path -ne $usePythonStateClampFastPath) {
    throw "Phase 3 used an unexpected Python state-clamp setting."
}
if ([bool]$result.scenario.deferred_cell_phase_updates -ne $deferCellPhaseUpdates) {
    throw "Phase 3 used an unexpected cell-phase update setting."
}
if ([bool]$result.scenario.compact_runtime_metrics -ne $compactRuntimeMetrics) {
    throw "Phase 3 used an unexpected runtime-metrics setting."
}
if ([bool]$result.scenario.precomputed_runtime_topology -ne $precomputedRuntimeTopology) {
    throw "Phase 3 used an unexpected runtime-topology setting."
}
$residentAdapter = $result.scenario.resident_snapshot_adapter
if ([bool]$residentAdapter.enabled -ne $ResidentSnapshotAdapter.IsPresent) {
    throw "Phase 3 used an unexpected resident snapshot-adapter setting."
}
if ([bool]$residentAdapter.transaction_timing_enabled -ne $ResidentSnapshotTiming.IsPresent) {
    throw "Phase 3 used an unexpected resident snapshot-timing setting."
}
if ([bool]$residentAdapter.handle_cache_enabled -ne $ResidentSnapshotHandleCache.IsPresent) {
    throw "Phase 3 used an unexpected resident snapshot handle-cache setting."
}
if ([bool]$residentAdapter.lightweight_commit_enabled -ne $ResidentSnapshotLightweightCommit.IsPresent) {
    throw "Phase 3 used an unexpected resident snapshot lightweight-commit setting."
}
if ([bool]$residentAdapter.skip_unchanged_derived_enabled -ne $ResidentSnapshotSkipUnchanged.IsPresent) {
    throw "Phase 3 used an unexpected resident snapshot unchanged-value setting."
}
if ([bool]$residentAdapter.lightweight_tail_timing_enabled -ne $ResidentSnapshotLightweightTailTiming.IsPresent) {
    throw "Phase 3 used an unexpected resident snapshot lightweight tail timing setting."
}
if ([bool]$residentAdapter.lightweight_notice_coalescing_enabled -ne $useResidentSnapshotLightweightNoticeCoalescing) {
    throw "Phase 3 used an unexpected resident snapshot lightweight notice-coalescing setting."
}
if ([bool]$residentAdapter.lightweight_notice_tracking_enabled -ne $ResidentSnapshotLightweightNoticeTracking.IsPresent) {
    throw "Phase 3 used an unexpected resident snapshot lightweight notice-tracking setting."
}
if ([bool]$residentAdapter.native_producer_connected -ne $ResidentNativeBackend.IsPresent) {
    throw "Phase 3 reported an unexpected native producer connection."
}
if ($ResidentSnapshotAdapter.IsPresent) {
    $expectedProducer = if ($ResidentNativeBackend.IsPresent) {
        "resident_native_backend"
    }
    else {
        "python_contract_bridge"
    }
    if ($residentAdapter.producer -ne $expectedProducer) {
        throw "Phase 3 used an unexpected resident snapshot producer."
    }
    if ([bool]$residentAdapter.native_backend.enabled -ne $ResidentNativeBackend.IsPresent) {
        throw "Phase 3 used an unexpected resident native backend setting."
    }
    if ($ResidentNativeBackend.IsPresent) {
        if ([bool]$residentAdapter.native_backend.status_after_close.active -or
            [bool]$residentAdapter.native_backend.status_after_close.already_closed -or
            $residentAdapter.native_backend.status_after_close.revision -ne 1200 -or
            $residentAdapter.native_backend.status_after_close.step_count -ne 1200 -or
            $residentAdapter.native_backend.status_after_close.export_count -ne 1) {
            throw "Resident native backend reported an unexpected lifecycle."
        }
    }
    if ([bool]$residentAdapter.status_after_timeline_stop.active) {
        throw "Resident snapshot adapter remained active after timeline stop."
    }
    if ($residentAdapter.status_after_timeline_stop.publish_count -le 0) {
        throw "Resident snapshot adapter published no revisions."
    }
    if ($residentAdapter.status_after_timeline_stop.revision -ne 1200 -or
        $residentAdapter.status_after_timeline_stop.publish_count -ne 240 -or
        $residentAdapter.status_after_timeline_stop.start_count -ne 1 -or
        $residentAdapter.status_after_timeline_stop.stop_count -ne 1) {
        throw "Resident snapshot adapter reported an unexpected lifecycle."
    }
    if (-not [bool]$residentAdapter.final_usd_state.revision_consistent) {
        throw "Resident snapshot consumers did not observe one final revision."
    }
    foreach ($consumer in @(
        $residentAdapter.final_usd_state.emitter,
        $residentAdapter.final_usd_state.logs.Log_00,
        $residentAdapter.final_usd_state.logs.Log_01
    )) {
        if ($consumer.revision -ne 1200) {
            throw "Resident snapshot consumer has an unexpected final revision."
        }
    }
    if ($ResidentSnapshotTiming.IsPresent) {
        if ($residentAdapter.transaction_profile.sample_count -ne 236 -or
            $residentAdapter.transaction_profile.status_counts.committed -ne 240 -or
            $residentAdapter.transaction_profile.status_counts.rolled_back -ne 0) {
            throw "Resident snapshot transaction profile is incomplete."
        }
        if ($residentAdapter.transaction_profile.counts.write_count.minimum -ne 19 -or
            $residentAdapter.transaction_profile.counts.write_count.maximum -ne 19) {
            throw "Resident snapshot transaction profile has an unexpected write count."
        }
    }
    elseif ($null -ne $residentAdapter.transaction_profile) {
        throw "Resident snapshot transaction profile appeared without an explicit request."
    }
    if ($ResidentSnapshotHandleCache.IsPresent) {
        $expectedAttributeCacheHits = if ($ResidentSnapshotSkipUnchanged.IsPresent) {
            $residentAdapter.status_after_timeline_stop.lightweight_write_count
        }
        else {
            4541
        }
        if (-not [bool]$residentAdapter.status_after_timeline_stop.handle_cache_enabled -or
            $residentAdapter.status_after_timeline_stop.cached_attribute_count -ne 19 -or
            $residentAdapter.status_after_timeline_stop.prim_cache_miss_count -ne 1 -or
            $residentAdapter.status_after_timeline_stop.prim_cache_hit_count -ne 239 -or
            $residentAdapter.status_after_timeline_stop.attribute_cache_miss_count -ne 19 -or
            $residentAdapter.status_after_timeline_stop.attribute_cache_hit_count -ne $expectedAttributeCacheHits) {
            throw "Resident snapshot handle cache did not reach its expected steady state."
        }
    }
    if ($ResidentSnapshotLightweightCommit.IsPresent) {
        if (-not [bool]$residentAdapter.status_after_timeline_stop.lightweight_commit_enabled -or
            [bool]$residentAdapter.status_after_timeline_stop.faulted -or
            $residentAdapter.status_after_timeline_stop.lightweight_commit_count -ne 239 -or
            $residentAdapter.status_after_timeline_stop.lightweight_failure_count -ne 0 -or
            $residentAdapter.status_after_timeline_stop.lightweight_recovery_count -ne 0) {
            throw "Resident snapshot lightweight commit did not preserve its expected lifecycle."
        }
        if ([bool]$residentAdapter.status_after_timeline_stop.lightweight_notice_coalescing_enabled -ne $useResidentSnapshotLightweightNoticeCoalescing) {
            throw "Resident snapshot lightweight commit used an unexpected notice-coalescing mode."
        }
        if ([bool]$residentAdapter.status_after_timeline_stop.lightweight_notice_tracking_enabled -ne $ResidentSnapshotLightweightNoticeTracking.IsPresent) {
            throw "Resident snapshot lightweight commit used an unexpected notice-tracking mode."
        }
        if ($ResidentSnapshotLightweightNoticeTracking.IsPresent) {
            $noticeStatus = $residentAdapter.status_after_timeline_stop
            if ($noticeStatus.lightweight_notice_publication_count -ne 239 -or
                $noticeStatus.lightweight_notice_accepted_revision_count -ne 239 -or
                $noticeStatus.lightweight_notice_count -ne (
                    $noticeStatus.lightweight_notice_accepted_revision_count +
                    $noticeStatus.lightweight_notice_rejected_count
                )) {
                throw "Resident snapshot notice tracking did not observe one accepted revision per publication."
            }
        }
    }
    if ($ResidentSnapshotSkipUnchanged.IsPresent) {
        $lightweightStatus = $residentAdapter.status_after_timeline_stop
        if (-not [bool]$lightweightStatus.skip_unchanged_derived_enabled -or
            $lightweightStatus.skipped_unchanged_write_count -le 0 -or
            ($lightweightStatus.lightweight_write_count + $lightweightStatus.skipped_unchanged_write_count) -ne (239 * 19)) {
            throw "Resident snapshot unchanged-value skipping did not cover every steady-state attribute."
        }
    }
    $woodVisual = $result.scenario.wood_visual_v0
    if ([bool]$woodVisual.enabled -ne $WoodVisualV0.IsPresent) {
        throw "Phase 3 used an unexpected wood visual V0 setting."
    }
    if ($WoodVisualV0.IsPresent) {
        if ($woodVisual.input -ne "ResidentPublishedSnapshot" -or
            [bool]$woodVisual.status_after_timeline_stop.active -or
            [bool]$woodVisual.status_after_timeline_stop.closed -or
            $woodVisual.status_after_timeline_stop.revision -ne 1200 -or
            $woodVisual.status_after_timeline_stop.publish_count -ne 240 -or
            $woodVisual.status_after_timeline_stop.failure_count -ne 0 -or
            $woodVisual.status_after_timeline_stop.recovery_count -ne 0 -or
            @($woodVisual.errors).Count -ne 0) {
            throw "Wood visual V0 did not preserve its expected lifecycle."
        }
        if ($woodVisual.publication_timing.sample_count -ne 239 -or
            $woodVisual.usd_set_count -le 0 -or
            $woodVisual.notice_count -ne 240) {
            throw "Wood visual V0 publication profile is incomplete."
        }
    }
    elseif ($null -ne $woodVisual.publication_timing -or
        $null -ne $woodVisual.status_after_timeline_stop -or
        $woodVisual.usd_set_count -ne 0 -or
        $woodVisual.notice_count -ne 0 -or
        @($woodVisual.errors).Count -ne 0) {
        throw "Wood visual V0 produced output while disabled."
    }
}
foreach ($name in @("dry", "wet")) {
    if ($result.scenario.zero_area_cell_count.$name -ne 792) {
        throw "Phase 3 $name wood has an unexpected zero-area cell count."
    }
}
if (-not $result.scenario.debugger_free) {
    $enabledDebugExtensions = @(
        $result.scenario.debug_extension_status.PSObject.Properties |
            Where-Object { $_.Value } |
            ForEach-Object { $_.Name }
    )
    throw "Phase 3 loaded forbidden debug extensions: $($enabledDebugExtensions -join ', ')"
}
if ($result.scenario.steps -ne 1200 -or $result.scenario.model_duration_seconds -ne 240) {
    throw "Phase 3 did not complete the expected 240 second model scenario."
}
if (-not $result.comparison.both_ignited -or -not $result.comparison.wet_ignition_delayed) {
    throw "Wet wood did not ignite after dry wood as required."
}
if ($result.comparison.wet_delay_seconds -le 0) {
    throw "Wet ignition delay was not positive."
}
foreach ($name in @("dry", "wet")) {
    $wood = $result.wood.$name
    if (-not $wood.all_values_finite -or -not $wood.non_negative_mass) {
        throw "Phase 3 $name wood produced invalid state values."
    }
    if ([math]::Abs($wood.mass_balance_error_kg) -gt 0.000001) {
        throw "Phase 3 $name wood violated mass conservation."
    }
    if ($wood.emitted_pyrolysis_gas_kg -le 0 -or $wood.char_mass_kg -le 0) {
        throw "Phase 3 $name wood produced no gas or char."
    }
}
if ($result.wood.wet.emitted_water_kg -le $result.wood.dry.emitted_water_kg) {
    throw "Wet wood did not evaporate more water than dry wood."
}
if ($result.flow.active_blocks_peak -le 0 -or $result.flow.peak_fuel_input -le 0) {
    throw "Wood-owned Flow input did not produce an active Flow simulation."
}
if (-not (Test-Path -LiteralPath $result.metrics_csv)) {
    throw "Phase 3 metrics CSV was not produced."
}
if ((Get-Content -LiteralPath $result.metrics_csv | Measure-Object).Count -ne 1201) {
    throw "Phase 3 metrics CSV does not contain 1200 data rows."
}
if ($result.images.Count -ne 2) {
    throw "Phase 3 must produce two fixed-step captures."
}
$expectedVideoFrameCount = if ($CaptureVideo.IsPresent) {
    [math]::Floor(1200 / $VideoFrameInterval)
}
else {
    0
}
if ([bool]$result.video_frames.enabled -ne $CaptureVideo.IsPresent) {
    throw "Phase 3 used an unexpected video-frame capture setting."
}
if ($result.video_frames.interval_steps -ne $VideoFrameInterval) {
    throw "Phase 3 used an unexpected video-frame interval."
}
if (@($result.video_frames.frames).Count -ne $expectedVideoFrameCount) {
    throw "Phase 3 produced an unexpected video-frame count."
}

$expectedTimingSamples = @{
    step_loop = 1180
    wood_model_step = 1180
    wood_metrics = 1180
    flow_source_mapping = 1180
    csv_row_build = 1180
    kit_flow_render_update = 236
    active_block_query = 236
    viewport_capture = 2
}
if ($ResidentSnapshotAdapter.IsPresent) {
    $expectedTimingSamples.resident_snapshot_usd = 236
    if ($null -ne $result.timing.segments.flow_emitter_usd -or
        $null -ne $result.timing.segments.wood_visual_usd) {
        throw "Resident snapshot mode unexpectedly measured legacy USD segments."
    }
}
else {
    $expectedTimingSamples.flow_emitter_usd = 236
    $expectedTimingSamples.wood_visual_usd = 118
    if ($null -ne $result.timing.segments.resident_snapshot_usd) {
        throw "Legacy Phase 3 unexpectedly measured the resident snapshot segment."
    }
}
foreach ($name in $expectedTimingSamples.Keys) {
    $segment = $result.timing.segments.$name
    if ($null -eq $segment -or $segment.sample_count -ne $expectedTimingSamples[$name]) {
        throw "Phase 3 timing segment has an unexpected sample count: $name"
    }
    foreach ($field in @("total_ms", "mean_ms", "p95_ms", "max_ms")) {
        $value = [double]$segment.$field
        if ([double]::IsNaN($value) -or [double]::IsInfinity($value) -or $value -lt 0) {
            throw "Phase 3 timing segment has an invalid $field value: $name"
        }
    }
}
if ($ProfileWoodInternals.IsPresent) {
    $expectedInternalSegments = @(
        "input_validation",
        "conduction",
        "sensible_heat",
        "evaporation",
        "pyrolysis",
        "char_oxidation",
        "state_finalize",
        "result_aggregation"
    )
    foreach ($name in $expectedInternalSegments) {
        $segment = $result.timing.wood_model_internal_segments.$name
        if ($null -eq $segment -or $segment.sample_count -ne 1180) {
            throw "Phase 3 wood internal segment has an unexpected sample count: $name"
        }
        foreach ($field in @("total_ms", "mean_ms", "p95_ms", "max_ms")) {
            $value = [double]$segment.$field
            if ([double]::IsNaN($value) -or [double]::IsInfinity($value) -or $value -lt 0) {
                throw "Phase 3 wood internal segment has an invalid $field value: $name"
            }
        }
    }
    if ($result.timing.wood_model_internal_total_mean_ms -le 0) {
        throw "Phase 3 wood internal timing total is invalid."
    }
}
elseif (@($result.timing.wood_model_internal_segments.PSObject.Properties).Count -ne 0) {
    throw "Phase 3 collected wood internal timings without an explicit request."
}
if ($ProfileSensibleHeat.IsPresent) {
    $expectedSensibleHeatSegments = @(
        "heat_capacity_evaluation",
        "interior_conduction_update",
        "surface_boundary_update",
        "loop_and_timer_overhead"
    )
    foreach ($name in $expectedSensibleHeatSegments) {
        $segment = $result.timing.wood_sensible_heat_segments.$name
        if ($null -eq $segment -or $segment.sample_count -ne 1180) {
            throw "Phase 3 sensible-heat segment has an unexpected sample count: $name"
        }
        foreach ($field in @("total_ms", "mean_ms", "p95_ms", "max_ms")) {
            $value = [double]$segment.$field
            if ([double]::IsNaN($value) -or [double]::IsInfinity($value) -or $value -lt 0) {
                throw "Phase 3 sensible-heat segment has an invalid $field value: $name"
            }
        }
    }
}
elseif (@($result.timing.wood_sensible_heat_segments.PSObject.Properties).Count -ne 0) {
    throw "Phase 3 collected sensible-heat timings without an explicit request."
}
if ($result.startup.extension_to_scenario_seconds -le 0) {
    throw "Phase 3 did not report extension-to-scenario startup time."
}
if ($result.timing.finalization.total_seconds -lt 0) {
    throw "Phase 3 reported invalid finalization time."
}

Add-Type -AssemblyName System.Drawing
foreach ($capture in $result.images) {
    if (-not (Test-Path -LiteralPath $capture.path)) {
        throw "Phase 3 capture was not produced: $($capture.path)"
    }
    if ($capture.capture_wall_seconds -le 0) {
        throw "Phase 3 capture did not report positive wall time."
    }
    $image = [System.Drawing.Image]::FromFile($capture.path)
    try {
        if ($image.Width -ne 1280 -or $image.Height -ne 720) {
            throw "Phase 3 PNG has an unexpected resolution: $($image.Width)x$($image.Height)"
        }
    }
    finally {
        $image.Dispose()
    }
}

if ($CaptureVideo.IsPresent) {
    $ffmpeg = Get-Command ffmpeg -ErrorAction Stop
    $videoPath = Join-Path $OutputDir "phase3_burn.mp4"
    $framePattern = Join-Path $OutputDir "video_frames\frame_%04d.png"
    $encodeTimer = [System.Diagnostics.Stopwatch]::StartNew()
    & $ffmpeg.Source -hide_banner -loglevel warning -y `
        -framerate $VideoFps -i $framePattern `
        -frames:v $expectedVideoFrameCount `
        -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p `
        -movflags +faststart -an $videoPath
    $ffmpegExitCode = $LASTEXITCODE
    $encodeTimer.Stop()
    if ($ffmpegExitCode -ne 0 -or -not (Test-Path -LiteralPath $videoPath)) {
        throw "Phase 3 video encoding failed with exit code $ffmpegExitCode."
    }
    $videoFile = Get-Item -LiteralPath $videoPath
    $videoSha256 = (Get-FileHash -LiteralPath $videoPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $result.video_frames | Add-Member -NotePropertyName video_path -NotePropertyValue $videoPath -Force
    $result.video_frames | Add-Member -NotePropertyName fps -NotePropertyValue $VideoFps -Force
    $result.video_frames | Add-Member -NotePropertyName duration_seconds -NotePropertyValue ([math]::Round($expectedVideoFrameCount / $VideoFps, 3)) -Force
    $result.video_frames | Add-Member -NotePropertyName encoded_bytes -NotePropertyValue $videoFile.Length -Force
    $result.video_frames | Add-Member -NotePropertyName encoded_sha256 -NotePropertyValue $videoSha256 -Force
    $result.video_frames | Add-Member -NotePropertyName encode_wall_seconds -NotePropertyValue ([math]::Round($encodeTimer.Elapsed.TotalSeconds, 3)) -Force
}

$runnerWallSeconds = [math]::Round($runTimer.Elapsed.TotalSeconds, 3)
$accountedRunnerSeconds = (
    [double]$result.startup.extension_to_scenario_seconds +
    [double]$result.scenario.simulation_wall_seconds +
    [double]$result.timing.finalization.total_seconds
)
$result | Add-Member -NotePropertyName runner_wall_seconds -NotePropertyValue $runnerWallSeconds -Force
$result | Add-Member -NotePropertyName runner_unattributed_seconds -NotePropertyValue ([math]::Round($runnerWallSeconds - $accountedRunnerSeconds, 4)) -Force
$json = $result | ConvertTo-Json -Depth 12
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($summary, $json + [Environment]::NewLine, $utf8NoBom)

Write-Host "Phase 3 validation succeeded: $OutputDir"
