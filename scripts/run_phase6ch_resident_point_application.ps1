param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.benchmark.kit"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$benchmark = Join-Path $PSScriptRoot "benchmark_resident_point_application.py"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_point_application.py"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) { throw "Application is not built." }
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
$developerPath = $environmentLines | Where-Object { $_ -cmatch '^PATH=' } | Select-Object -First 1
if (-not $developerPath) { throw "Visual Studio developer PATH was not returned." }
$env:PATH = $developerPath.Substring($developerPath.IndexOf("=") + 1)

if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6ch" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$buildDir = Join-Path $OutputDir "native-build"
$output = Join-Path $OutputDir "resident_point_application_raw.json"
$videoFrames = Join-Path $OutputDir "video_frames"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& cmake.exe -S $nativeSource -B $buildDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $buildDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $buildDir "campfire_wood_native.dll"

& $kit @(
    $app,
    "--no-window",
    "--/app/quitAfter=1200",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/exts/campfire.app/residentPointApplicationEnabled=true",
    "--/phase6ch/nativeLibrary=$nativeDll",
    "--/phase6ch/output=$output",
    "--/phase6ch/videoFrames=$videoFrames",
    "--/rtx/flow/enabled=true",
    "--exec",
    $benchmark
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Phase 6CH failed: $output" }
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_application_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_application_report.svg"
$poster = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_application_frame.png"
$video = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_application.mp4"
& $kitPython $analyzer --raw $output --report $report --svg $svg --poster $poster --frames $videoFrames
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ffmpeg = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if (-not $ffmpeg) { throw "ffmpeg.exe is required to encode the Phase 6CH video." }
& $ffmpeg.Source -y -framerate 10 -i (Join-Path $videoFrames "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6CH qualified: gates={0}, points={1}, active blocks={2}" -f @($result.gates.PSObject.Properties).Count, $result.scope.point_count, $result.flow.active_blocks_peak)
