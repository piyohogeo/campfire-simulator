param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$kitPython = Join-Path $releaseRoot "kit\python\python.exe"
$analyzer = Join-Path $PSScriptRoot "analyze_resident_point_continuity.py"
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

if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6cm" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$buildDir = Join-Path $OutputDir "native-build"
$sceneDir = Join-Path $OutputDir "scene"
$videoFrames = Join-Path $OutputDir "video_frames"
$raw = Join-Path $OutputDir "summary.json"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
New-Item -ItemType Directory -Path $sceneDir -Force | Out-Null

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
    "--/exts/campfire.app/autoCreateScene=true",
    "--/exts/campfire.app/phase=phase3",
    "--/exts/campfire.app/captureOnStartup=true",
    "--/exts/campfire.app/quitAfterCapture=true",
    "--/exts/campfire.app/outputDir=$OutputDir",
    "--/exts/campfire.app/sceneOutputDir=$sceneDir",
    "--/exts/campfire.app/residentPointApplicationEnabled=true",
    "--/exts/campfire.app/residentPointContinuityQualificationEnabled=true",
    "--/exts/campfire.app/residentNativeLibraryPath=$nativeDll",
    "--/rtx/flow/enabled=true"
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $raw -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Phase 6CM diagnostic failed: $raw" }
$report = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_continuity_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_continuity_report.svg"
$poster = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_continuity_frame.png"
$video = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_point_continuity.mp4"
& $kitPython $analyzer --raw $raw --report $report --svg $svg --poster $poster --frames $videoFrames
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ffmpeg = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if (-not $ffmpeg) { throw "ffmpeg.exe is required to encode the Phase 6CM video." }
& $ffmpeg.Source -y -framerate 10 -i (Join-Path $videoFrames "frame_%04d.png") -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart $video
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("Phase 6CM recorded: gates={0}, seamless continuity={1}, max alignment error={2} m" -f @($result.gates.PSObject.Properties).Count, $result.known_issue.seamless_visual_continuity_qualified, $result.known_issue.maximum_observed_alignment_error_m)
