param(
    [string]$Scene = "",
    [string]$OutputDir = "",
    [string[]]$Cases = @("all_enabled", "PhysX", "OmniGraph", "OmniGraphAttach", "PhysXFabric", "FlowUsd"),
    [switch]$ReuseExisting
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$probe = Join-Path $PSScriptRoot "probe_resident_owner_stage_update.py"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if (-not $Scene) {
    $Scene = Join-Path $repositoryRoot "artifacts\phase3\phase6cn\scene\phase3_point_application.usda"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cp-owner"
}
$Scene = [System.IO.Path]::GetFullPath($Scene)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path -LiteralPath $Scene)) {
    throw "Phase 6CP input scene is missing: $Scene"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$nativeLibrary = Join-Path $repositoryRoot "artifacts\phase3\phase6co-resident\native-build\campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $nativeLibrary)) {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) { throw "Visual Studio locator was not found." }
    $visualStudioRoot = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -ne 0 -or -not $visualStudioRoot) { throw "A Visual Studio C++ x64 toolchain was not found." }
    $developerCommand = Join-Path $visualStudioRoot "Common7\Tools\VsDevCmd.bat"
    $environmentLines = & $env:ComSpec /d /s /c "`"$developerCommand`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    foreach ($line in $environmentLines) {
        $separator = $line.IndexOf("=")
        if ($separator -gt 0) { Set-Item -Path ("Env:" + $line.Substring(0, $separator)) -Value $line.Substring($separator + 1) }
    }
    $buildDir = Join-Path $OutputDir "native-build"
    & cmake.exe -S $nativeSource -B $buildDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & cmake.exe --build $buildDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $nativeLibrary = Join-Path $buildDir "campfire_wood_native.dll"
}

foreach ($caseName in $Cases) {
    if ($caseName -notin @("all_enabled", "PhysX", "OmniGraph", "OmniGraphAttach", "PhysXFabric", "FlowUsd")) {
        throw "Unsupported Phase 6CP case: $caseName"
    }
    $safeName = $caseName.ToLowerInvariant()
    $output = Join-Path $OutputDir ($safeName + ".json")
    if ($ReuseExisting -and (Test-Path -LiteralPath $output)) {
        $existing = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
        if ($existing.status -eq "ok" -and $existing.case -eq $caseName) {
            Write-Host ("Phase 6CP reusing {0}" -f $output)
            continue
        }
    }
    $disabledNode = if ($caseName -eq "all_enabled") { "" } else { $caseName }
    & $kit @(
        $app,
        "--no-window",
        "--/app/quitAfter=300",
        "--/app/settings/persistent=0",
        "--/app/settings/loadUserConfig=0",
        "--/exts/campfire.app/autoCreateScene=false",
        "--/phase6cp/scene=$Scene",
        "--/phase6cp/nativeLibrary=$nativeLibrary",
        "--/phase6cp/output=$output",
        "--/phase6cp/disabledNode=$disabledNode",
        "--/renderer/enabled=false",
        "--/rtx/flow/enabled=true",
        "--exec",
        $probe
    )
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$results = foreach ($caseName in $Cases) {
    $result = Get-Content -LiteralPath (Join-Path $OutputDir ($caseName.ToLowerInvariant() + ".json")) -Raw | ConvertFrom-Json
    [ordered]@{
        case = $caseName
        remained_playing = [bool]$result.timeline.remained_playing
        advanced_from_zero = [bool]$result.timeline.advanced_from_zero
        stop_event_count = [int]$result.timeline.stop_event_count
        disabled_node_restored = [bool]$result.scope.disabled_node_restored
    }
}
$summary = [ordered]@{
    schema_version = 1
    phase = "phase6cp"
    status = if (@($results | Where-Object { -not $_.disabled_node_restored }).Count -eq 0) { "ok" } else { "failed" }
    scene = $Scene
    results = @($results)
    production_changed = $false
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir "summary.json") -Encoding utf8
$results | ForEach-Object {
    Write-Host ("Phase 6CP owner {0}: play={1}, advanced={2}, stops={3}, restored={4}" -f $_.case, $_.remained_playing, $_.advanced_from_zero, $_.stop_event_count, $_.disabled_node_restored)
}
