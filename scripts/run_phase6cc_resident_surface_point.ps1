param(
    [ValidateRange(20, 300)]
    [int]$Frames = 120,
    [ValidateRange(5, 100)]
    [int]$Warmup = 30,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$benchmark = Join-Path $PSScriptRoot "benchmark_resident_surface_point.py"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_surface_point.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built. Run .\repo.bat build first."
}
if ($Warmup -ge $Frames) { throw "Warmup must be smaller than Frames." }
if (-not (Test-Path -LiteralPath $vswhere)) { throw "Visual Studio locator was not found." }
$visualStudioRoot = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $visualStudioRoot) { throw "A Visual Studio C++ x64 toolchain was not found." }
$developerCommand = Join-Path $visualStudioRoot "Common7\Tools\VsDevCmd.bat"
$environmentLines = & $env:ComSpec /d /s /c "`"$developerCommand`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
foreach ($line in $environmentLines) {
    $separator = $line.IndexOf("=")
    if ($separator -gt 0) {
        Set-Item -Path ("Env:" + $line.Substring(0, $separator)) -Value $line.Substring($separator + 1)
    }
}
$developerPath = $environmentLines | Where-Object { $_ -cmatch '^PATH=' } | Select-Object -First 1
if (-not $developerPath) { throw "Visual Studio developer PATH was not returned." }
$env:PATH = $developerPath.Substring($developerPath.IndexOf("=") + 1)

if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cc" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$buildDir = Join-Path $OutputDir "native-build"
$output = Join-Path $OutputDir "resident_surface_point_raw.json"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& cmake.exe -S $nativeSource -B $buildDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $buildDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $buildDir "campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $nativeDll)) { throw "Native DLL was not produced." }

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=900",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phase6cc/nativeLibrary=$nativeDll",
    "--/phase6cc/output=$output",
    "--/phase6cc/frames=$Frames",
    "--/phase6cc/warmup=$Warmup",
    "--/rtx/flow/enabled=true",
    "--exec",
    $benchmark
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$result = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Phase 6CC failed: $output" }
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_surface_point_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_surface_point_report.svg"
$capture = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_surface_point_frame.png"
& $kitPython $analyzer --raw $output --report $report --svg $svg --capture $capture
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host (
    "Phase 6CC qualified: points={0}, active blocks={1}, native channels p95={2:N4} ms, dynamic publication p95={3:N4} ms" -f
    $result.scope.point_count,
    $result.flow.active_blocks_peak,
    $result.measurement.native_dynamic_channels.p95_ms,
    $result.measurement.dynamic_publication_total.p95_ms
)
